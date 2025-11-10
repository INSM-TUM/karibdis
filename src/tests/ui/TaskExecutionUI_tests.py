
import time
import rdflib
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from rdflib import RDF, RDFS, Literal, XSD
from IPython.display import display
import pytest
import playwright.sync_api
from playwright.sync_api import expect
from karibdis.Application import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from rdflib import URIRef, BNode
import re
import os
import sys

sys.path.insert(0, os.path.abspath('') + '/src')


task = rdflib.term.URIRef('http://example.org/Task_1_1')
case = rdflib.term.URIRef('http://example.org/Case_1')

@pytest.fixture(scope="function")
def app_with_data():      
    app = JupyterApplication()
    app.system = KnowledgeGraphBPMS()
    pkg = app.system.pkg
    
    pkg.bind("log", "http://example.org/", override = True)
    activity_curie_list = [
        'log:Activity_CRP',
        'log:Activity_LacticAcid',
        'log:Activity_ER_Triage',
        'log:Activity_Leucocytes'
    ]
    for curie in activity_curie_list:
        activity = pkg.namespace_manager.expand_curie(curie)
        pkg.add((activity, RDF.type, BPO.Activity))
        pkg.add((activity, RDFS.label, Literal(curie.split(':', 1)[1])))

    activity_list = list(pkg.subjects(predicate=RDF.type, object=BPO.Activity))
    for type in [XSD.integer, XSD.float, XSD.string, XSD.boolean]:
        example_pv = URIRef(f'http://example.org/ProcessValue_{type.fragment}')
        pkg.add((example_pv , RDF.type, BPO.ProcessValue))
        pkg.add((example_pv, BPO.dataType, type))
        for activity in activity_list:
            pkg.add((activity, BPO.writesValue, example_pv))

    roles_curie_list = [':Doctor', ':Nurse', ':Admin']
    for curie in roles_curie_list:
        role_to_add = pkg.namespace_manager.expand_curie(curie)
        pkg.add((role_to_add, RDF.type, BPO.Role))

    role = pkg.namespace_manager.expand_curie(':ProcessValue_CRP_Role')
    pkg.add((role, RDF.type, BPO.ProcessValue))
    pkg.add((role, BPO.dataType, BPO.Role))
    next_activity = pkg.namespace_manager.expand_curie(':ProcessValue_CRP_NextActivity')
    pkg.add((next_activity, RDF.type, BPO.ProcessValue))
    pkg.add((next_activity, BPO.dataType, BPO.Activity))

    # attach the values to activities
    for activity in activity_list:
        pkg.add((activity, BPO.writesValue, role))
        pkg.add((activity, BPO.writesValue, next_activity))
       
    assert len(list(app.system.engine.open_decisions())) == 0, "Unexpected open decisions found"
    app.system.engine.open_new_case()
   
    activity = pkg.namespace_manager.expand_curie('log:Activity_CRP')
    pkg.add((task, BPO.instanceOf, activity))

    app.system.engine.deduce()
    assert len(list(app.system.engine.open_tasks())) == 1
    assert (task, RDF.type, BPO.Task) in pkg, "Task not found in knowledge graph"
    yield app
    


def test_default_run(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app  = app_with_data
    engine = app.system.engine
    pkg = app.system.pkg

    display(TaskExecutionUI(engine))
    
    activity = next(app.system.pkg.objects(task, BPO.instanceOf))
    
    page_session.get_by_role("button", name="Reload Tasks").click()
    page_session.get_by_role("button", name="Submit").click()

    wait_for_task(engine, 0, timeout=0.5)
    assert next(engine.open_tasks(), None) is None
    
    attributes = list(pkg.objects(subject=activity, predicate=BPO.writesValue))
    case_objs = []
    for attr in attributes:
        case_objs += list(pkg.objects(case, attr))
        
    assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"

    for obj in case_objs:
        if isinstance(obj, Literal):
            if isinstance(obj.toPython(), int):
                assert obj.toPython() == 0, "Default int value is not 0"
            elif isinstance(obj.toPython(), float):
                assert obj.toPython() == 0.0, "Default float value is not 0.0"
            elif isinstance(obj.toPython(), str):
                assert obj.toPython() == "", "Default string value is not ''"
            elif isinstance(obj.toPython(), bool):
                assert obj.toPython() == False, "Default boolean value is not False"
            elif isinstance(obj, (URIRef, BNode)) and ((obj, RDF.type, BPO.Role) in pkg):
                expected_role = pkg.namespace_manager.expand_curie(':Doctor')
                assert obj == expected_role, "Expected role to be :Doctor"
            elif isinstance(obj, (URIRef, BNode)) and ((obj, RDF.type, BPO.Activity) in pkg):
                expected_activity = pkg.namespace_manager.expand_curie('log:Activity_CRP')
                assert obj == expected_activity, "Expected activity to be log:Activity_CRP"
                
def test_expected_run(app_with_data, solara_test, page_session: playwright.sync_api.Page) -> None:
    app = app_with_data
    pkg = app.system.pkg
    
    display(TaskExecutionUI(app.system.engine))
 
    activity = next(pkg.objects(task, BPO.instanceOf))

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
    
    for obj in case_objs:
        if isinstance(obj, Literal):
            val = obj.toPython()
            if isinstance(val, bool):
                assert val == True, f"Expected boolean value to be True, got {val}"
            elif isinstance(val, int):
                assert val == 100, f"Expected int value to be 100, got {val}"
            elif isinstance(val, float):
                assert val == 55.55, f"Expected float value to be 55.55, got {val}"
            elif isinstance(val, str):
                assert val == "Test", f"Expected string value to be 'Test', got {val}"
            elif isinstance(obj, (URIRef, BNode)) and ((obj, RDF.type, BPO.Role) in pkg):
                expected_role = pkg.namespace_manager.expand_curie(':Admin')
                assert obj == expected_role, f"Expected role to be :Admin, got {obj}"
            elif isinstance(obj, (URIRef, BNode)) and ((obj, RDF.type, BPO.Activity) in pkg):
                expected_activity = pkg.namespace_manager.expand_curie('log:Activity_LacticAcid')
                assert obj == expected_activity, f"Expected activity to be log:Activity_LacticAcid, got {obj}"

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

def wait_for_decision(engine, expected_count, timeout=5.0, poll_interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            decisions = list(engine.open_decisions())
        except RuntimeError:
            time.sleep(poll_interval)
            continue
        if len(decisions) == expected_count:
            return True
        time.sleep(poll_interval)
    raise AssertionError(f"open_decisions count not {expected_count} after timeout")