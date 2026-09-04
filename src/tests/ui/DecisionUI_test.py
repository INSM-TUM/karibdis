import string

import reacton

from IPython.display import display
from playwright.sync_api import Page, expect
from rdflib import RDF, URIRef

from karibdis.KGProcessEngine import KGProcessEngine
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.ui.DecisionUI import DecisionBody
from karibdis.ui.ui_util import BusyOverlay, use_busy
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from .ui_test_utils import wait_for


@reacton.component
def BusyScope(render_content):
    """Minimal stand-in for the busy scope SelectionMenu provides in the real UI."""
    is_busy, be_busy_with = use_busy()
    return BusyOverlay(is_busy, render_content, be_busy_with=be_busy_with)


def test_select_right_option(solara_test, page_session: Page):
    engine = KGProcessEngine(ProcessKnowledgeGraph())
    for letter in list(string.ascii_uppercase)[:5]:
        engine.pkg.add((URIRef(f'http://example.org/Activity_{letter}'), RDF.type, BPO.Activity))
    engine.open_new_case()
    engine.deduce() # Creates new task
    decision = next(engine.open_decisions())
    display(BusyScope(lambda: DecisionBody(engine, decision, lambda: None)))
    second_option = page_session.get_by_text('Activity').nth(2) # Take the third of five options
    activity = second_option.inner_text().split(' ')[0]
    second_botton = page_session.locator(f'button:below(:text("{activity}"))').first # Take the button below that option
    second_botton.click() 
    print(f'Selected activity: {activity}')
    def assert_correct_option_selected():
        assert (decision.bindings['task'], BPO.instanceOf, engine.pkg.namespace_manager.expand_curie(activity)) in engine.pkg

    wait_for(assert_correct_option_selected)

    