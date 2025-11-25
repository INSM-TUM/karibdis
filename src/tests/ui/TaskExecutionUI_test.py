import time
import rdflib
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from rdflib import RDF, RDFS, Literal, XSD, URIRef
from IPython.display import display
import pytest
import playwright.sync_api
from playwright.sync_api import expect
from karibdis.Application import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from rdflib import URIRef, BNode

task = rdflib.term.URIRef('http://example.org/Task_1_1')
task_1_2 = rdflib.term.URIRef('http://example.org/Task_1_2')
task_activity = rdflib.term.URIRef('http://example.org/Activity_CRP')
case = rdflib.term.URIRef('http://example.org/Case_1')
task_2 = rdflib.term.URIRef('http://example.org/Task_2_1')
case_2 = rdflib.term.URIRef('http://example.org/Case_2')
    
@pytest.fixture(scope="function")
def app_with_data(request):
    
    if hasattr(request, 'param'):
        config = request.param
    else:
        config = {
            "activity_pvs": [XSD.integer, XSD.float, XSD.string, XSD.boolean, BPO.Role, BPO.Activity]
        }
    
    app = JupyterApplication()
    app.system = KnowledgeGraphBPMS()
    pkg = app.system.pkg
    activity_pvs = config.get("activity_pvs", [])
    
    
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
    for type in [XSD.integer, XSD.float, XSD.string, XSD.boolean, BPO.Role, BPO.Activity]:
        example_pv = _pv_for(type, pkg)
        pkg.add((example_pv , RDF.type, BPO.ProcessValue))
        pkg.add((example_pv, BPO.dataType, type))
        for activity in activity_list:
            if type in activity_pvs:
                pkg.add((activity, BPO.writesValue, example_pv))

    roles_curie_list = [':Doctor', ':Nurse', ':Admin']
    for curie in roles_curie_list:
        role_to_add = pkg.namespace_manager.expand_curie(curie)
        pkg.add((role_to_add, RDF.type, BPO.Role))
        pkg.add((role_to_add, RDFS.label, Literal(curie.split(':', 1)[1])))

    assert len(list(app.system.engine.open_decisions())) == 0, "Unexpected open decisions found"
    app.system.engine.open_new_case()
   
    pkg.add((task, BPO.instanceOf, task_activity))

    app.system.engine.deduce()
    assert len(list(app.system.engine.open_tasks())) == 1
    assert (task, RDF.type, BPO.Task) in pkg, "Task not found in knowledge graph"
    yield app


def test_default_run(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app  = app_with_data
    engine = app.system.engine
    pkg = app.system.pkg

    display(TaskExecutionUI(engine))
    
    page_session.get_by_role("button", name="Reload Tasks").click()
    page_session.get_by_role("button", name="Submit").click()

    _wait_for_task(engine, 0)
    assert next(engine.open_tasks(), None) is None
        
    assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"

    expected_defaults = {
        XSD.integer: 0,
        XSD.float: 0.0,
        XSD.string: "",
        XSD.boolean: False,
        BPO.Role: 'http://infs.cit.tum.de/karibdis/baseontology/Doctor',
        BPO.Activity: 'http://example.org/Activity_CRP'}
    
    for dtype, expected_value in expected_defaults.items():
        actual_value = pkg.value(subject=case, predicate= _pv_for(dtype, pkg)).toPython()
        assert actual_value == expected_value, f"Expected {expected_value} ({type(expected_value).__name__}) for data type {dtype}, got {actual_value} ({type(actual_value).__name__})"


def test_expected_run(app_with_data, solara_test, page_session: playwright.sync_api.Page) -> None:
    app = app_with_data
    pkg = app.system.pkg
    
    display(TaskExecutionUI(app.system.engine))
 
    test_values = {
        XSD.boolean: True,
        XSD.integer: 100,
        XSD.float: 55.55,
        XSD.string: "Test",
        BPO.Role: URIRef('http://infs.cit.tum.de/karibdis/baseontology/Admin'),
        BPO.Activity: URIRef('http://example.org/Activity_LacticAcid')   
    }

    page_session.get_by_role("button", name="Reload Tasks").click()
    
    page_session.locator('input:right-of(:text("ProcessValue_integer"))').first.fill(str(test_values[XSD.integer]))
    page_session.locator('input:right-of(:text("ProcessValue_float"))').first.fill(str(test_values[XSD.float]))
    page_session.locator('input:right-of(:text("ProcessValue_string"))').first.fill(test_values[XSD.string])
    page_session.locator(':right-of(:text("ProcessValue_boolean"))').get_by_role("checkbox").first.check()
    page_session.locator('select:right-of(:text("ProcessValue_Role"))').first.select_option(pkg.label(test_values[BPO.Role]))
    page_session.locator('select:right-of(:text("ProcessValue_Activity"))').first.select_option(pkg.label(test_values[BPO.Activity]))
    
    page_session.get_by_role("button", name="Submit").click()
    _wait_for_task(app.system.engine, 0)
   
    assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"
    
    for dtype, expected_value in test_values.items():
        if dtype in [BPO.Role, BPO.Activity]:
            expected_value = str(expected_value)
        actual_value = pkg.value(subject=case, predicate= _pv_for(dtype, pkg)).toPython()
        assert actual_value == expected_value, f"Expected {expected_value} ({type(expected_value).__name__}) for data type {dtype}, got {actual_value} ({type(actual_value).__name__})"

# TESTS FOR MULTIPLE TASKS

def test_multiple_tasks_displayed_and_one_task_completed(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app = app_with_data
    pkg = app.system.pkg
    engine = app.system.engine

    # Open a new case and assign activity to second task
    engine.open_new_case()
    _assign_activity_to_task(pkg, engine, task_2, 'log:Activity_LacticAcid')

    _wait_for_task(engine, 2)

    display(TaskExecutionUI(engine))
    page_session.get_by_role("button", name="Reload Tasks").click()

    expect(page_session.get_by_role("button").get_by_text("Task_1_1")).to_be_visible()
    expect(page_session.get_by_role("button").get_by_text("Task_2_1")).to_be_visible()

    # Submit second task
    page_session.get_by_text("Task_2_1").first.click()
    page_session.get_by_role("button", name="Submit").click()

    _wait_for_task(engine, 1)

    assert (task_2, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"
    assert (task, BPO.completedAt, None) not in pkg, "Wrong task was completed"

def test_only_open_tasks_displayed(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app = app_with_data
    pkg = app.system.pkg
    engine = app.system.engine

    # create a second case and attach its task to an activity
    engine.open_new_case()
    _assign_activity_to_task(pkg, engine, task_2, 'log:Activity_Leucocytes')
    _wait_for_task(engine, 2)
    
    # create a third case with no active tasks
    engine.open_new_case()
    case_3 = URIRef('http://example.org/Case_3')
    task_3 = URIRef('http://example.org/Task_3_1')
    
    # assert that the new case and task exist in the knowledge graph
    assert (task_3, RDF.type, BPO.Task) in pkg
    assert (case_3, RDF.type, BPO.Case) in pkg

    # mark first task as completed
    pkg.add((task, BPO.completedAt, Literal('2020-01-01T00:00:00', datatype=XSD.dateTime)))

    display(TaskExecutionUI(engine))
    _wait_for_task(engine, 1)
    page_session.get_by_role("button", name="Reload Tasks").click()

    # check that closed task is not visible
    expect(page_session.get_by_role("button").get_by_text("Task_1_1")).not_to_be_visible()
    expect(page_session.get_by_role("button").get_by_text("Task_2_1")).to_be_visible()
    # check that task with no activity assigned is not visible
    expect(page_session.get_by_role("button").get_by_text("Task_3_1")).not_to_be_visible()

def test_values_attached_to_correct_case_and_task(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app = app_with_data
    pkg = app.system.pkg
    engine = app.system.engine

    # create a second case and its task
    engine.open_new_case()
    _assign_activity_to_task(pkg, engine, task_2, 'log:Activity_LacticAcid')
    _wait_for_task(engine, 2)

    display(TaskExecutionUI(engine))
    page_session.get_by_role("button", name="Reload Tasks").click()

    # Select the second task and set a specific integer value
    page_session.get_by_text("Task_2_1").first.click()
    page_session.locator('input:right-of(:text("ProcessValue_integer"))').first.fill('20')
    page_session.get_by_role("button", name="Submit").click()
    _wait_for_task(engine, 1)

    # The submitted case should have the integer value 20
    val_submtted = pkg.value(subject=case_2, predicate=_pv_for(XSD.integer, pkg))
    assert val_submtted is not None and val_submtted.toPython() == 20

    # The first case should still have no integer value assigned
    val_orig = pkg.value(subject=case, predicate=_pv_for(XSD.integer, pkg))
    assert val_orig is None
    
def test_load_existing_values_into_ui(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app = app_with_data
    pkg = app.system.pkg
    
    display(TaskExecutionUI(app.system.engine))
 
    test_values = {
        XSD.boolean: True,
        XSD.integer: 100,
        XSD.float: 55.55,
        XSD.string: "Test",
        BPO.Role: URIRef('http://infs.cit.tum.de/karibdis/baseontology/Admin'),
        BPO.Activity: URIRef('http://example.org/Activity_LacticAcid')   
    }
    
    page_session.get_by_role("button", name="Reload Tasks").click()
    
    page_session.locator('input:right-of(:text("ProcessValue_integer"))').first.fill(str(test_values[XSD.integer]))
    page_session.locator('input:right-of(:text("ProcessValue_float"))').first.fill(str(test_values[XSD.float]))
    page_session.locator('input:right-of(:text("ProcessValue_string"))').first.fill(test_values[XSD.string])
    page_session.locator(':right-of(:text("ProcessValue_boolean"))').get_by_role("checkbox").first.check()
    page_session.locator('select:right-of(:text("ProcessValue_Role"))').first.select_option(pkg.label(test_values[BPO.Role]))
    page_session.locator('select:right-of(:text("ProcessValue_Activity"))').first.select_option(pkg.label(test_values[BPO.Activity]))
    
    page_session.get_by_role("button", name="Submit").click()
    _wait_for_task(app.system.engine, 0)
    
    _assign_activity_to_task(pkg, app.system.engine, task_1_2, 'log:Activity_CRP')
    _wait_for_task(app.system.engine, 1)
    page_session.get_by_role("button", name="Reload Tasks").click()
    page_session.get_by_text("Task_1_2").first.click()
    
    # verify that the previously submitted values are loaded into the UI
    expect(page_session.locator('input:right-of(:text("ProcessValue_integer"))').first).to_have_value(str(test_values[XSD.integer]))
    expect(page_session.locator('input:right-of(:text("ProcessValue_float"))').first).to_have_value(str(test_values[XSD.float]))
    expect(page_session.locator('input:right-of(:text("ProcessValue_string"))').first).to_have_value(test_values[XSD.string])
    expect(page_session.locator(':right-of(:text("ProcessValue_boolean"))').get_by_role("checkbox").first).to_be_checked()
    expect(page_session.locator('select:right-of(:text("ProcessValue_Role"))').first).to_have_value(pkg.label(test_values[BPO.Role]))
    expect(page_session.locator('select:right-of(:text("ProcessValue_Activity"))').first).to_have_value(pkg.label(test_values[BPO.Activity]))

@pytest.mark.parametrize("app_with_data", [{"activity_pvs": [XSD.integer, BPO.Role]}], indirect=True)    
def test_add_process_value(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app = app_with_data
    pkg = app.system.pkg
    engine = app.system.engine
    
    display(TaskExecutionUI(engine))
    page_session.get_by_role("button", name="Reload Tasks").click()
    
    # Initially only activity-linked ProcessValues should be visible (integer and Role)
    expect(page_session.get_by_text("ProcessValue_integer")).to_be_visible()
    expect(page_session.get_by_text("ProcessValue_Role")).to_be_visible()
    expect(page_session.get_by_text("ProcessValue_string")).not_to_be_visible()
    expect(page_session.get_by_text("ProcessValue_float")).not_to_be_visible()
    
    page_session.get_by_role("button", name="Add new ProcessValue").click()
    expect(page_session.get_by_text("Add a new ProcessValue to this case")).to_be_visible()
    
    page_session.locator('select:below(:text("Add a new ProcessValue to this case"))').first.select_option("log:ProcessValue_string")
    page_session.get_by_role("button", name="Create").click()
    
    expect(page_session.get_by_text("Add a new ProcessValue to this case")).not_to_be_visible()
    expect(page_session.get_by_text("ProcessValue_string")).to_be_visible()
    
    page_session.get_by_role("button", name="Add new ProcessValue").click()
    page_session.locator('select:below(:text("Add a new ProcessValue to this case"))').first.select_option("log:ProcessValue_float")
    page_session.get_by_role("button", name="Create").click()
    
    expect(page_session.get_by_text("ProcessValue_float")).to_be_visible()
    
    # Fill in values for the newly added ProcessValues
    page_session.locator('input:right-of(:text("ProcessValue_string"))').first.fill("Added String")
    page_session.locator('input:right-of(:text("ProcessValue_float"))').first.fill("99.99")
    page_session.get_by_role("button", name="Submit").click()
    _wait_for_task(engine, 0)
    
    # Verify the added ProcessValues have correct values in the knowledge graph
    string_pv = _pv_for(XSD.string, pkg)
    float_pv = _pv_for(XSD.float, pkg)
    
    string_value = pkg.value(subject=case, predicate=string_pv)
    float_value = pkg.value(subject=case, predicate=float_pv)
    
    assert string_value is not None and string_value.toPython() == "Added String"
    assert float_value is not None and float_value.toPython() == 99.99
    
    # Verify the task is completed
    assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"

@pytest.mark.parametrize("app_with_data", [{"activity_pvs": [XSD.integer, BPO.Role]}], indirect=True)
def test_add_process_value_persistence_across_tasks(app_with_data, solara_test, page_session: playwright.sync_api.Page):
    app = app_with_data
    pkg = app.system.pkg
    engine = app.system.engine
    
    display(TaskExecutionUI(engine))
    page_session.get_by_role("button", name="Reload Tasks").click()
    
    # Add ProcessValue_string for the first task
    page_session.get_by_role("button", name="Add new ProcessValue").click()
    page_session.locator('select:below(:text("Add a new ProcessValue to this case"))').first.select_option("log:ProcessValue_string")
    page_session.get_by_role("button", name="Create").click()
    
    expect(page_session.get_by_text("ProcessValue_string")).to_be_visible()
    page_session.locator('input:right-of(:text("ProcessValue_string"))').first.fill("First Task Value")
    page_session.get_by_role("button", name="Submit").click()
    _wait_for_task(engine, 0)
    
    # Create a second task for the same case
    _assign_activity_to_task(pkg, engine, task_1_2, 'log:Activity_CRP')
    _wait_for_task(engine, 1)
    
    page_session.get_by_role("button", name="Reload Tasks").click()
    expect(page_session.get_by_text("Task_1_2").first).to_be_visible()
    
    # Verify ProcessValue_string is not visible initially
    expect(page_session.get_by_text("ProcessValue_string")).not_to_be_visible()
    
    # Add ProcessValue_string again for the second task
    page_session.get_by_role("button", name="Add new ProcessValue").click()
    page_session.locator('select:below(:text("Add a new ProcessValue to this case"))').first.select_option("log:ProcessValue_string")
    page_session.get_by_role("button", name="Create").click()
    
    # Verify it now appears and shows the existing value from the case
    expect(page_session.get_by_text("ProcessValue_string")).to_be_visible()
    expect(page_session.locator('input:right-of(:text("ProcessValue_string"))').first).to_have_value("First Task Value")
    
# HELPER FUNCTIONS

def _wait_for_task(engine, expected_count, timeout=5.0, poll_interval=0.05):
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
    raise AssertionError(f"open_tasks count not {expected_count} after timeout, current count: {len(tasks)}")

def _pv_for(dtype, pkg):
    # attach the last part of the dtype URI (after the last '/')
    if dtype == BPO.Role:
         return pkg.namespace_manager.expand_curie('log:ProcessValue_Role')
    elif dtype == BPO.Activity:
         return pkg.namespace_manager.expand_curie('log:ProcessValue_Activity')
    
    name = dtype.fragment
    return URIRef(f'http://example.org/ProcessValue_{name}')

def _assign_activity_to_task(pkg, engine, task_uri, activity_curie):
    # assign activity to undecided task
    activity = pkg.namespace_manager.expand_curie(activity_curie)
    pkg.add((task_uri, BPO.instanceOf, activity))