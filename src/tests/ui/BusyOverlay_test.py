import string
import threading
import time
from types import SimpleNamespace

import pytest
import reacton
import reacton.ipywidgets as w
from IPython.display import display
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PWTimeout
from rdflib import RDF, URIRef

from karibdis.KGProcessEngine import Decision, KGProcessEngine
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from karibdis.KnowledgeImporter import TextualImporter
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.ui.DecisionUI import DecisionUI
from karibdis.ui.GraphExplorationUI import GraphExplorationUI
from karibdis.ui.KnowledgeModelingUI import KnowledgeModelingUI
from karibdis.ui.TaskExecutionUI import TaskExecutionUI
from karibdis.ui.ui_util import BusyExempt, BusyScope, use_busy
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO


GATE_TIMEOUT = 10.0
START_BUTTON = 'Start work'
EXEMPT_BUTTON = 'Always clickable'


def spinners(page: Page):
    return page.locator('.v-progress-circular:visible')

@reacton.component
def WorkerBody(work, with_exempt=False):
    """Routes `work` through whichever busy scope encloses it, like every real view does."""
    _, be_busy_with = use_busy()
    with w.VBox() as main:
        w.Button(description=START_BUTTON, on_click=lambda: be_busy_with(work))
        if with_exempt:
            BusyExempt(lambda: w.Button(description=EXEMPT_BUTTON, on_click=lambda: None))
    return main


@reacton.component
def ScopedWorker(work, with_exempt=False):
    """The intended usage: a BusyScope wrapping a body that calls use_busy()."""
    with w.VBox() as main:
        BusyScope(lambda: WorkerBody(work, with_exempt))
    return main


def test_no_spinner_before_any_work_starts(solara_test, page_session: Page):
    gate = threading.Event()
    display(ScopedWorker(lambda: gate.wait(GATE_TIMEOUT)))

    expect(page_session.get_by_role('button', name=START_BUTTON)).to_be_visible()
    expect(spinners(page_session)).to_have_count(0)


def test_spinner_shows_while_work_runs_and_clears_when_it_finishes(solara_test, page_session: Page):
    gate = threading.Event()
    display(ScopedWorker(lambda: gate.wait(GATE_TIMEOUT)))

    page_session.get_by_role('button', name=START_BUTTON).click()
    expect(spinners(page_session)).to_have_count(1)

    gate.set()
    expect(spinners(page_session)).to_have_count(0)


def test_input_is_blocked_while_work_runs(solara_test, page_session: Page):
    gate = threading.Event()
    display(ScopedWorker(lambda: gate.wait(GATE_TIMEOUT)))

    page_session.get_by_role('button', name=START_BUTTON).click()
    expect(spinners(page_session)).to_have_count(1)

    # The scope blocks via pointer-events, not disabled=, so assert the click cannot land.
    with pytest.raises(PWTimeout):
        page_session.get_by_role('button', name=START_BUTTON).click(timeout=1200)

    gate.set()
    expect(spinners(page_session)).to_have_count(0)


def test_busy_state_clears_when_the_work_raises(solara_test, page_session: Page):
    gate = threading.Event()

    def failing_work():
        gate.wait(GATE_TIMEOUT)
        raise RuntimeError('work failed')

    display(ScopedWorker(failing_work))

    page_session.get_by_role('button', name=START_BUTTON).click()
    expect(spinners(page_session)).to_have_count(1)

    gate.set()
    expect(spinners(page_session)).to_have_count(0)
    page_session.get_by_role('button', name=START_BUTTON).click(timeout=2000)


def test_exempt_content_stays_clickable_while_the_scope_is_blocked(solara_test, page_session: Page):
    gate = threading.Event()
    display(ScopedWorker(lambda: gate.wait(GATE_TIMEOUT), with_exempt=True))

    page_session.get_by_role('button', name=START_BUTTON).click()
    expect(spinners(page_session)).to_have_count(1)

    page_session.get_by_role('button', name=EXEMPT_BUTTON).click(timeout=2000)

    gate.set()
    expect(spinners(page_session)).to_have_count(0)


def test_work_runs_inline_when_no_scope_encloses_the_component(solara_test, page_session: Page):
    done = threading.Event()
    display(WorkerBody(done.set))

    page_session.get_by_role('button', name=START_BUTTON).click()

    assert done.wait(5.0), 'work should still run without an enclosing BusyScope'
    expect(spinners(page_session)).to_have_count(0)


def _slow_down(monkeypatch, cls, method, seconds, when=lambda self: True):
    """Patches the class rather than an instance: open_decisions() rebuilds its Decision
    objects on every call, so an instance patched here is never the one the UI uses.
    `when` narrows the slowdown to the objects a test cares about."""
    original = getattr(cls, method)

    def slowed(self, *args, **kwargs):
        if when(self):
            time.sleep(seconds)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cls, method, slowed)


def _decision_label(engine, decision):
    return str(engine.pkg.label(decision.bindings.get('task')))


def _two_decisions_slow_first(monkeypatch, slow_seconds):
    engine = KGProcessEngine(ProcessKnowledgeGraph())
    for letter in string.ascii_uppercase[:3]:
        engine.pkg.add((URIRef(f'http://example.org/Activity_{letter}'), RDF.type, BPO.Activity))
    engine.open_new_case()
    engine.open_new_case()
    engine.deduce()
    slow, fast = list(engine.open_decisions())

    _slow_down(monkeypatch, Decision, 'get_top_k_results', slow_seconds,
               when=lambda decision: decision.bindings == slow.bindings)
    return engine, slow, fast


def _engine_with_open_tasks(n_cases=2):
    system = KnowledgeGraphBPMS()
    pkg, engine = system.pkg, system.engine
    pkg.add((URIRef('http://example.org/Activity_CRP'), RDF.type, BPO.Activity))
    for _ in range(n_cases):
        engine.open_new_case()
    engine.deduce()
    for decision in list(engine.open_decisions()):
        engine.handle_decision(decision, decision.get_options()[0])
    engine.deduce()
    assert len(list(engine.open_tasks())) == n_cases
    return engine


def test_overlay_appears_during_slow_op_and_clears_after(
    solara_test, page_session: Page, monkeypatch
):
    engine, _, _ = _two_decisions_slow_first(monkeypatch, slow_seconds=0.5)
    display(DecisionUI(engine))

    expect(spinners(page_session)).to_be_visible()
    expect(spinners(page_session)).not_to_be_visible(timeout=5000)


def test_overlay_is_scoped_to_the_currently_selected_item(
    solara_test, page_session: Page, monkeypatch
):
    engine, slow, fast = _two_decisions_slow_first(monkeypatch, slow_seconds=3.0)
    display(DecisionUI(engine))

    expect(spinners(page_session)).to_have_count(1)

    page_session.get_by_text(_decision_label(engine, fast)).first.click()
    expect(spinners(page_session)).to_have_count(0)

    page_session.get_by_text(_decision_label(engine, slow)).first.click()
    expect(spinners(page_session)).to_have_count(1)


def test_other_decisions_stay_selectable_while_one_is_busy(
    solara_test, page_session: Page, monkeypatch
):
    engine, _, fast = _two_decisions_slow_first(monkeypatch, slow_seconds=3.0)
    display(DecisionUI(engine))

    page_session.get_by_text(_decision_label(engine, fast)).first.click(timeout=2000)
    page_session.get_by_role('button', name='Reload Decisions').click(timeout=2000)


def test_task_execution_locks_other_tasks_during_submit(
    solara_test, page_session: Page, monkeypatch
):
    engine = _engine_with_open_tasks(n_cases=2)
    _slow_down(monkeypatch, KGProcessEngine, 'complete_task', 4.0)

    display(TaskExecutionUI(engine))
    page_session.get_by_role('button', name='Submit').click()

    # The lock blocks via pointer-events, not disabled=, so assert the click cannot land.
    with pytest.raises(PWTimeout):
        page_session.get_by_role('button').get_by_text('Task_2_1').click(timeout=1200)
    with pytest.raises(PWTimeout):
        page_session.get_by_role('button', name='Reload Tasks').click(timeout=1200)


def test_cancel_stays_clickable_while_the_import_view_is_blocked(
    solara_test, page_session: Page, monkeypatch
):
    system = KnowledgeGraphBPMS()
    # The view builds a ChatOpenAI client just to construct the importer, which needs an
    # API key that CI has no business holding. Nothing here ever calls the model.
    monkeypatch.setattr('karibdis.KnowledgeImporter.langchain_openai',
                        SimpleNamespace(ChatOpenAI=lambda **kwargs: None))
    monkeypatch.setattr(TextualImporter, 'import_content_from_statement',
                        lambda self, text: time.sleep(4.0))

    display(KnowledgeModelingUI(system.pkg))
    page_session.get_by_role('button', name='Text').click()
    page_session.get_by_role('button', name='Load Entities').click()

    with pytest.raises(PWTimeout):
        page_session.get_by_role('button', name='Load Rules').click(timeout=1200)

    page_session.get_by_role('button', name='Cancel Knowledge Import').click(timeout=3000)
    expect(page_session.get_by_role('button', name='Event Log')).to_be_visible()


def test_graph_exploration_blocks_whole_tab_while_query_runs(
    solara_test, page_session: Page, monkeypatch
):
    pkg = ProcessKnowledgeGraph()
    _slow_down(monkeypatch, ProcessKnowledgeGraph, 'query', 3.0)

    display(GraphExplorationUI(pkg))
    expect(spinners(page_session)).to_be_visible()

    with pytest.raises(PWTimeout):
        page_session.get_by_role('button', name='Reload Graph').click(timeout=1200)

    expect(spinners(page_session)).not_to_be_visible(timeout=10000)
