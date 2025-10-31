import time
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from karibdis.KnowledgeImporter import OnlineEventImporter
from rdflib import RDF, RDFS, OWL, Namespace, Literal, XSD
import reacton
import reacton.ipywidgets as w
from IPython.display import display
import pytest
import playwright.sync_api
from playwright.sync_api import expect
import re
import os
import sys

sys.path.insert(0, os.path.abspath('') + '/src')
from karibdis.Application import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS

@pytest.fixture(scope="function")
def app_with_data():      
    app = JupyterApplication()
    app.system = KnowledgeGraphBPMS()
    pkg = app.system.pkg

    # load an example log (adjust path or parameterize if needed)
    example_domains = os.path.abspath(importlib.resources.files('karibdis').joinpath('../../example_domains'))
    log = pm4py.read_xes(os.path.join(example_domains, 'sepsis/Sepsis Cases - Event Log.xes'))
    case_attributes = list(log.groupby('case:concept:name').agg('nunique').max().where(lambda x: x == 1).dropna().index)
    event_interface = OnlineEventImporter(pkg, case_attributes=case_attributes, ignore_columns={'lifecycle:transition'})

    data = log[log['case:concept:name'] == 'B'][0:5]
    for _, event in data.iterrows():
        event_interface.translate_event(event)
    event_interface.load()

    # add process value types and example entity options (same as in your test)
    an_int = pkg.namespace_manager.expand_curie('log:ProcessValue_CRP_Integer')
    pkg.add((an_int, RDF.type, BPO.ProcessValue))
    pkg.add((an_int, BPO.dataType, XSD.integer))

    a_float = pkg.namespace_manager.expand_curie('log:ProcessValue_CRP_Float')
    pkg.add((a_float, RDF.type, BPO.ProcessValue))
    pkg.add((a_float, BPO.dataType, XSD.float))

    a_string = pkg.namespace_manager.expand_curie('log:ProcessValue_CRP_String')
    pkg.add((a_string, RDF.type, BPO.ProcessValue))
    pkg.add((a_string, BPO.dataType, XSD.string))

    a_bool = pkg.namespace_manager.expand_curie('log:ProcessValue_CRP_Boolean')
    pkg.add((a_bool, RDF.type, BPO.ProcessValue))
    pkg.add((a_bool, BPO.dataType, XSD.boolean))

    role = pkg.namespace_manager.expand_curie(':ProcessValue_CRP_Role')
    pkg.add((role, RDF.type, BPO.ProcessValue))
    pkg.add((role, BPO.dataType, BPO.Role))

    next_activity = pkg.namespace_manager.expand_curie(':ProcessValue_CRP_NextActivity')
    pkg.add((next_activity, RDF.type, BPO.ProcessValue))
    pkg.add((next_activity, BPO.dataType, BPO.Activity))

    doctor = pkg.namespace_manager.expand_curie(':Doctor')
    pkg.add((doctor, RDF.type, BPO.Role))
    nurse = pkg.namespace_manager.expand_curie(':Nurse')
    pkg.add((nurse, RDF.type, BPO.Role))
    admin = pkg.namespace_manager.expand_curie(':Admin')
    pkg.add((admin, RDF.type, BPO.Role))

    # attach the values to activities
    for activity in list(pkg.subjects(predicate=RDF.type, object=BPO.Activity)):
        pkg.add((activity, BPO.writesValue, an_int))
        pkg.add((activity, BPO.writesValue, a_float))
        pkg.add((activity, BPO.writesValue, a_string))
        pkg.add((activity, BPO.writesValue, a_bool))
        pkg.add((activity, BPO.writesValue, role))
        pkg.add((activity, BPO.writesValue, next_activity))
        
    task = pkg.namespace_manager.expand_curie('log:Task_B_6')
    
    activity = pkg.namespace_manager.expand_curie('log:Activity_CRP')
    pkg.add((task, BPO.instanceOf, activity))    

    app.system.engine.deduce()

    assert (task, RDF.type, BPO.Task) in pkg, "Task_B_6 not found in knowledge graph"
    yield app
    
    try:
        app.system.pkg.remove((None, None, None))
    except Exception:
        pass
   

def test_default_run(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app  = app_with_data
    engine = app.system.engine
    pkg = app.system.pkg

    display(TaskExecutionUI(engine))
    
    assert len(list(engine.open_tasks())) == 1
    task,case = next(engine.open_tasks())
    activity = next(app.system.pkg.objects(task, BPO.instanceOf))
    # page_session.get_by_text("Task Selection", exact=True).click()
    page_session.get_by_role("button", name="Reload Tasks").click()
    page_session.get_by_role("button", name="Submit").click()

    wait_for_task(engine, 0, timeout=0.5)
    assert next(engine.open_tasks(), None) is None
    
    attributes = list(pkg.objects(subject=activity, predicate=BPO.writesValue))
    case_objs = []
    for attr in attributes:
        case_objs += list(pkg.objects(case, attr))
        
    assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"

    assert any(isinstance(o, Literal) and isinstance(o.toPython(), int) and (o.toPython() == 0) for o in case_objs), "Int 0 not found in activity related case process values"
    assert any(isinstance(o, Literal) and isinstance(o.toPython(), float) and (o.toPython() == 0.0) for o in case_objs), "Float 0.0 not found in activity related case process values"
    assert any(isinstance(o, Literal) and isinstance(o.toPython(), str) and (o.toPython() == "") for o in case_objs), "String '' not found in activity related case process values"
    assert any(isinstance(o, Literal) and isinstance(o.toPython(), bool) and (o.toPython() == False) for o in case_objs), "Boolean False not found in activity related case process values"


def test_expected_run(app_with_data, solara_test, page_session: playwright.sync_api.Page) -> None:
    app = app_with_data
    pkg = app.system.pkg
    display(TaskExecutionUI(app.system.engine))
    
    task,case = next(app.system.engine.open_tasks())
    activity = next(pkg.objects(task, BPO.instanceOf))
    
    for pv in pkg.objects(activity, BPO.writesValue):
        has_pv_type = any(
            ((val, RDF.type, pv) in pkg) or (val == pv)
            for _, _, val in pkg.triples((case, None, None))
        )
        assert not has_pv_type, f"Case already has process value of type {pv}"

    page_session.get_by_role("button", name="Reload Tasks").click()
    
    page_session.get_by_role("spinbutton", name="null").first.click()
    page_session.get_by_role("spinbutton", name="null").first.fill("100")
    page_session.get_by_role("spinbutton", name="null").nth(1).click()
    page_session.get_by_role("spinbutton", name="null").nth(1).fill("55.55")
    page_session.get_by_role("textbox").click()
    page_session.get_by_role("textbox").fill("Test")
    page_session.get_by_role("checkbox").check()
    page_session.get_by_role("combobox").first.select_option(":Admin")
    page_session.get_by_role("combobox").nth(1).select_option("log:Activity_LacticAcid")
    
    page_session.get_by_role("button", name="Submit").click()
    wait_for_task(app.system.engine, 0, timeout=2.0)
   
    assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"
   
    attributes = list(pkg.objects(subject=activity, predicate=BPO.writesValue))
    case_objs = []
    for attr in attributes:
        case_objs += list(pkg.objects(case, attr))

    assert any(isinstance(o, Literal) and isinstance(o.toPython(), int) and (o.toPython() == 100) for o in case_objs), "Int 100 not found in activity related case process values"
    assert any(isinstance(o, Literal) and isinstance(o.toPython(), float) and (o.toPython() == 55.55) for o in case_objs), "Float 55.55 not found in activity related case process values"
    assert any(isinstance(o, Literal) and isinstance(o.toPython(), str) and (o.toPython() == "Test") for o in case_objs), "String 'Test' not found in activity related case process values"
    assert any(isinstance(o, Literal) and isinstance(o.toPython(), bool) and (o.toPython() == True) for o in case_objs), "Boolean True not found in activity related case process values"

    admin = pkg.namespace_manager.expand_curie(":Admin")
    assert any(o == admin for o in case_objs), "Selected role not attached to case"

    selected_activity = pkg.namespace_manager.expand_curie("log:Activity_LacticAcid")
    assert any(o == selected_activity for o in case_objs), "Selected activity not attached to case"
    
def wait_for_task(engine, expected_count, timeout=5.0, poll_interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            tasks = list(engine.open_tasks())
        except RuntimeError:
            time.sleep(poll_interval)
            continue
        if len(tasks) == expected_count:
            return True
        time.sleep(poll_interval)
    raise AssertionError(f"open_tasks count not {expected_count} after timeout")

# def incorrect_run(playwright: Playwright) -> None:
#     browser = playwright.chromium.launch(headless=False)
#     context = browser.new_context()
#     page = context.new_page()
#     page.goto("http://localhost:8866/voila/render/playwright_tests.ipynb?")
#     page.get_by_text("Process Execution").click()
#     page.locator("div").filter(has_text=re.compile(r"^log:Activity_ER%20Triage \(0\)Confirm$")).get_by_role("button").click()
#     page.locator("#tab-key-1-7").get_by_text("Task Selection").click()
#     page.get_by_role("button", name="Reload Tasks").click()
#     page.get_by_role("spinbutton", name="null").first.click()
#     page.get_by_role("spinbutton", name="null").first.fill("test1")
#     page.get_by_role("spinbutton", name="null").nth(1).click()
#     page.get_by_role("spinbutton", name="null").nth(1).fill("test2")
#     page.get_by_role("button", name="Submit").click()
   


