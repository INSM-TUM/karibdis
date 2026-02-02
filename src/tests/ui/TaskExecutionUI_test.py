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

medical_role = URIRef('http://example.org/MedicalRole')
doctor_role = URIRef('http://example.org/DoctorRole')
nurse_role = URIRef('http://example.org/NurseRole')
        
senior_doctor = URIRef('http://example.org/SeniorDoctor')
junior_nurse = URIRef('http://example.org/JuniorNurse')
medical_technician = URIRef('http://example.org/MedicalTechnician')

pv_role = URIRef('http://example.org/ProcessValue_Role')
pv_activity = URIRef('http://example.org/ProcessValue_Activity')

basic_test_values = {
        XSD.boolean: True,
        XSD.integer: 100,
        XSD.float: 55.55,
        XSD.string: "Test",
        BPO.Role: URIRef('http://infs.cit.tum.de/karibdis/baseontology/Admin'),
        BPO.Activity: URIRef('http://example.org/Activity_LacticAcid')   
    }
    
@pytest.fixture(scope="function")
def system_test_data_subclasses(request, system_test_data):
    """Fixture to add subclass hierarchies on demand."""
    pkg, engine = system_test_data
    
    if not hasattr(request, 'param'):
        return pkg, engine
    
    subclass_config = request.param
    
    if subclass_config == "medical_roles":
        # Medical role hierarchy
        for role in [medical_role, doctor_role, nurse_role]:
            pkg.add((role, RDF.type, RDFS.Class))
            if role != medical_role:
                pkg.add((role, RDFS.subClassOf, medical_role))
            else:
                pkg.add((role, RDFS.subClassOf, BPO.Role))
            pkg.add((role, RDFS.label, Literal(role.split('/')[-1])))
        
        # Create instances
        pkg.add((medical_technician, RDF.type, medical_role))
        pkg.add((medical_technician, RDFS.label, Literal('Medical Technician')))
        
        pkg.add((senior_doctor, RDF.type, doctor_role))
        pkg.add((senior_doctor, RDFS.label, Literal('Senior Doctor')))
        
        pkg.add((junior_nurse, RDF.type, nurse_role))
        pkg.add((junior_nurse, RDFS.label, Literal('Junior Nurse')))
        
    return pkg, engine

@pytest.fixture(scope="function")
def system_test_data(request):
    
    if hasattr(request, 'param'):
        config = request.param
    else:
        config = {}
    
    system = KnowledgeGraphBPMS()
    pkg = system.pkg
    engine = system.engine
    activity_pvs = config.get("activity_pvs", [XSD.integer, XSD.float, XSD.string, XSD.boolean, BPO.Role, BPO.Activity])
    
    
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
        example_pv = _pv_for(type)
        pkg.add((example_pv , RDF.type, BPO.ProcessValue))
        pkg.add((example_pv, BPO.dataType, type))
        if type in activity_pvs:
            for activity in activity_list:
                pkg.add((activity, BPO.writesValue, example_pv))

    roles_curie_list = [':Doctor', ':Nurse', ':Admin']
    for curie in roles_curie_list:
        role_to_add = pkg.namespace_manager.expand_curie(curie)
        pkg.add((role_to_add, RDF.type, BPO.Role))
        pkg.add((role_to_add, RDFS.label, Literal(curie.split(':', 1)[1])))

    assert len(list(engine.open_decisions())) == 0, "Unexpected open decisions found"
    engine.open_new_case()
   
    pkg.add((task, BPO.instanceOf, task_activity))

    engine.deduce()
    assert len(list(engine.open_tasks())) == 1
    assert (task, RDF.type, BPO.Task) in pkg, "Task not found in knowledge graph"
    yield pkg, engine


class TestBasicTaskExecution:
    """Test cases for basic task execution functionality."""
    
    def test_default_run(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test submitting a task with default values."""
        pkg, engine = system_test_data
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
            actual_value = pkg.value(subject=case, predicate= _pv_for(dtype)).toPython()
            assert actual_value == expected_value, f"Expected {expected_value} ({type(expected_value).__name__}) for data type {dtype}, got {actual_value} ({type(actual_value).__name__})"

    def test_expected_run(self, system_test_data, solara_test, page_session: playwright.sync_api.Page) -> None:
        """Test submitting a task with specific values."""
        pkg, engine = system_test_data  
        display(TaskExecutionUI(engine))
        
        page_session.get_by_role("button", name="Reload Tasks").click()
        
        page_session.locator('input:right-of(:text("ProcessValue_integer"))').first.fill(str(basic_test_values[XSD.integer]))
        page_session.locator('input:right-of(:text("ProcessValue_float"))').first.fill(str(basic_test_values[XSD.float]))
        page_session.locator('input:right-of(:text("ProcessValue_string"))').first.fill(basic_test_values[XSD.string])
        page_session.locator(':right-of(:text("ProcessValue_boolean"))').get_by_role("checkbox").first.check()
        page_session.locator('select:right-of(:text("ProcessValue_Role"))').first.select_option(pkg.label(basic_test_values[BPO.Role]))
        page_session.locator('select:right-of(:text("ProcessValue_Activity"))').first.select_option(pkg.label(basic_test_values[BPO.Activity]))
        
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)
       
        assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"
        
        for dtype, expected_value in basic_test_values.items():
            if dtype in [BPO.Role, BPO.Activity]:
                expected_value = str(expected_value)
            actual_value = pkg.value(subject=case, predicate= _pv_for(dtype)).toPython()
            assert actual_value == expected_value, f"Expected {expected_value} ({type(expected_value).__name__}) for data type {dtype}, got {actual_value} ({type(actual_value).__name__})"
            
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    @pytest.mark.parametrize("system_test_data_subclasses", ["medical_roles"], indirect=True)
    def test_select_subclass_instances_as_entity_pvs(self, system_test_data_subclasses, solara_test, page_session: playwright.sync_api.Page):
        """Test selecting subclass instances as process value entities."""
        pkg, engine = system_test_data_subclasses
        
        display(TaskExecutionUI(engine))
        
        page_session.get_by_role("button", name="Reload Tasks").click()
        expect(page_session.get_by_text("ProcessValue_Role")).to_be_visible()
        role_dropdown = page_session.locator('select:right-of(:text("ProcessValue_Role"))').first
        expect(role_dropdown).to_be_visible()
        role_dropdown.click()
        
        # Verify that subclass instances appear in the dropdown
        expect(role_dropdown).to_contain_text('Senior Doctor')
        expect(role_dropdown).to_contain_text('Junior Nurse')
        expect(role_dropdown).to_contain_text('Medical Technician')
        
        # Test selecting a subclass instance
        role_dropdown.select_option('Senior Doctor')
        
        # Verify the selection
        expect(role_dropdown).to_have_value('Senior Doctor')
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)
        
        # Verify the subclass instance was assigned to the case
        role_pv = _pv_for(BPO.Role)
        assigned_role = pkg.value(subject=case, predicate=role_pv)
        
        assert assigned_role == senior_doctor, f"Expected {senior_doctor}, got {assigned_role}"
        assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"


class TestMultipleTaskHandling:
    """Test cases for handling multiple tasks and task visibility."""
    
    def test_multiple_tasks_displayed_and_one_task_completed(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test that multiple tasks are displayed and specific tasks can be completed."""
        pkg, engine = system_test_data

        # Open a new case and assign activity to second task
        engine.open_new_case()
        _assign_activity_to_task(pkg, task_2, 'log:Activity_LacticAcid')

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

    def test_only_open_tasks_displayed(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test that only open tasks are displayed, not completed or inactive ones."""
        pkg, engine = system_test_data

        # create a second case and attach its task to an activity
        engine.open_new_case()
        _assign_activity_to_task(pkg, task_2, 'log:Activity_Leucocytes')
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

    def test_values_attached_to_correct_case_and_task(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test that process values are attached to the correct case when multiple tasks exist."""
        pkg, engine = system_test_data

        # create a second case and its task
        engine.open_new_case()
        _assign_activity_to_task(pkg, task_2, 'log:Activity_LacticAcid')
        _wait_for_task(engine, 2)

        display(TaskExecutionUI(engine))
        page_session.get_by_role("button", name="Reload Tasks").click()

        # Select the second task and set a specific integer value
        page_session.get_by_text("Task_2_1").first.click()
        page_session.locator('input:right-of(:text("ProcessValue_integer"))').first.fill('20')
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 1)

        # The submitted case should have the integer value 20
        val_submtted = pkg.value(subject=case_2, predicate=_pv_for(XSD.integer))
        assert val_submtted is not None and val_submtted.toPython() == 20

        # The first case should still have no integer value assigned
        val_orig = pkg.value(subject=case, predicate=_pv_for(XSD.integer))
        assert val_orig is None


class TestValuePersistence:
    """Test cases for process value persistence and loading."""
    
    def test_load_existing_values_into_ui(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test that previously submitted values are loaded when switching between tasks."""
        pkg, engine = system_test_data
        
        display(TaskExecutionUI(engine))
        
        page_session.get_by_role("button", name="Reload Tasks").click()
        
        page_session.locator('input:right-of(:text("ProcessValue_integer"))').first.fill(str(basic_test_values[XSD.integer]))
        page_session.locator('input:right-of(:text("ProcessValue_float"))').first.fill(str(basic_test_values[XSD.float]))
        page_session.locator('input:right-of(:text("ProcessValue_string"))').first.fill(basic_test_values[XSD.string])
        page_session.locator(':right-of(:text("ProcessValue_boolean"))').get_by_role("checkbox").first.check()
        page_session.locator('select:right-of(:text("ProcessValue_Role"))').first.select_option(pkg.label(basic_test_values[BPO.Role]))
        page_session.locator('select:right-of(:text("ProcessValue_Activity"))').first.select_option(pkg.label(basic_test_values[BPO.Activity]))
        
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)
        
        _assign_activity_to_task(pkg, task_1_2, 'log:Activity_CRP')
        _wait_for_task(engine, 1)
        page_session.get_by_role("button", name="Reload Tasks").click()
        page_session.get_by_text("Task_1_2").first.click()
        
        # verify that the previously submitted values are loaded into the UI
        expect(page_session.locator('input:right-of(:text("ProcessValue_integer"))').first).to_have_value(str(basic_test_values[XSD.integer]))
        expect(page_session.locator('input:right-of(:text("ProcessValue_float"))').first).to_have_value(str(basic_test_values[XSD.float]))
        expect(page_session.locator('input:right-of(:text("ProcessValue_string"))').first).to_have_value(basic_test_values[XSD.string])
        expect(page_session.locator(':right-of(:text("ProcessValue_boolean"))').get_by_role("checkbox").first).to_be_checked()
        expect(page_session.locator('select:right-of(:text("ProcessValue_Role"))').first).to_have_value(pkg.label(basic_test_values[BPO.Role]))
        expect(page_session.locator('select:right-of(:text("ProcessValue_Activity"))').first).to_have_value(pkg.label(basic_test_values[BPO.Activity]))


class TestProcessValueManagement:
    """Test cases for adding and managing process values."""
    
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.integer, BPO.Role]}], indirect=True)
    def test_add_process_value(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test adding new process values to a task dynamically."""
        pkg, engine = system_test_data
        
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
        assert pkg.value(subject=case, predicate=_pv_for(XSD.string)).toPython() == "Added String"
        assert pkg.value(subject=case, predicate=_pv_for(XSD.float)).toPython() == 99.99
        
        # Verify the task is completed
        assert (task, BPO.completedAt, None) in pkg, "Task not marked as completed in knowledge graph"

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.integer, BPO.Role]}], indirect=True)
    def test_add_process_value_persistence_across_tasks(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Test that dynamically added process values persist across tasks within the same case."""
        pkg, engine = system_test_data
        
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
        _assign_activity_to_task(pkg, task_1_2, 'log:Activity_CRP')
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



# ===== HELPER FUNCTIONS =====

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

def _pv_for(dtype):
    # attach the last part of the dtype URI (after the last '/')
    if dtype == BPO.Role:
         return pv_role
    elif dtype == BPO.Activity:
         return pv_activity
    name = dtype.fragment
    return URIRef(f'http://example.org/ProcessValue_{name}')

def _assign_activity_to_task(pkg, task_uri, activity_curie):
    # assign activity to undecided task
    activity = pkg.namespace_manager.expand_curie(activity_curie)
    pkg.add((task_uri, BPO.instanceOf, activity))