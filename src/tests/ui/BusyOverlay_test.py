import string
import time

import pytest
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
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO


SPINNER = ".v-progress-circular:visible"


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

    original = Decision.get_top_k_results
    def slowed(self, *args, **kwargs):
        if self.bindings == slow.bindings:
            time.sleep(slow_seconds)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Decision, 'get_top_k_results', slowed)
    return engine, slow, fast


def _engine_with_open_tasks(n_cases=2):
    system = KnowledgeGraphBPMS()
    pkg, engine = system.pkg, system.engine
    activity = URIRef('http://example.org/Activity_CRP')
    pkg.add((activity, RDF.type, BPO.Activity))
    for _ in range(n_cases):
        engine.open_new_case()
    engine.deduce()
    for decision in list(engine.open_decisions()):
        pkg.add((decision.bindings.get('task'), BPO.instanceOf, activity))
    engine.deduce()
    assert len(list(engine.open_tasks())) == n_cases
    return engine


def _slow_down(monkeypatch, cls, method, seconds):
    original = getattr(cls, method)
    def slowed(self, *args, **kwargs):
        time.sleep(seconds)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(cls, method, slowed)


def test_overlay_appears_during_slow_op_and_clears_after(
    solara_test, page_session: Page, monkeypatch
):
    engine, _, _ = _two_decisions_slow_first(monkeypatch, slow_seconds=0.5)
    display(DecisionUI(engine))

    expect(page_session.locator(SPINNER)).to_be_visible()
    expect(page_session.locator(SPINNER)).not_to_be_visible(timeout=5000)


def test_overlay_is_scoped_to_the_currently_selected_item(
    solara_test, page_session: Page, monkeypatch
):
    engine, slow, fast = _two_decisions_slow_first(monkeypatch, slow_seconds=3.0)
    display(DecisionUI(engine))

    expect(page_session.locator(SPINNER)).to_have_count(1)

    page_session.get_by_text(_decision_label(engine, fast)).first.click()
    expect(page_session.locator(SPINNER)).to_have_count(0)

    page_session.get_by_text(_decision_label(engine, slow)).first.click()
    expect(page_session.locator(SPINNER)).to_have_count(1)


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
    expect(page_session.locator(SPINNER)).to_be_visible()

    with pytest.raises(PWTimeout):
        page_session.get_by_role('button', name='Reload Graph').click(timeout=1200)

    expect(page_session.locator(SPINNER)).not_to_be_visible(timeout=10000)
