import string

from IPython.display import display
from playwright.sync_api import Page, expect

from karibdis.KGProcessEngine import KGProcessEngine
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from karibdis.Application import *

from .ui_test_utils import wait_for


def test_select_right_option(solara_test, page_session: Page):
    engine = KGProcessEngine(ProcessKnowledgeGraph())
    for letter in list(string.ascii_uppercase)[:5]:
        engine.pkg.add((URIRef(f'http://example.org/Activity_{letter}'), RDF.type, BPO.Activity))
    engine.open_new_case()
    engine.deduce() # Creates new task
    decision = next(engine.open_decisions())
    display(DecisionBody(engine, decision, lambda : None))
    second_option = page_session.get_by_text('Activity').nth(2) # Take the third of five options
    activity = second_option.inner_text().split(' ')[0]
    second_botton = page_session.locator(f'button:below(:text("{activity}"))').first # Take the button below that option
    second_botton.click() 
    print(f'Selected activity: {activity}')
    def assert_correct_option_selected():
        assert (decision.subject, BPO.instanceOf, engine.pkg.namespace_manager.expand_curie(activity)) in engine.pkg

    wait_for(assert_correct_option_selected)

    