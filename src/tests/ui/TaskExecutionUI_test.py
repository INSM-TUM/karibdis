import time

import playwright.sync_api
import pytest
from IPython.display import display
from playwright.sync_api import expect
from rdflib import RDF, RDFS, Literal, URIRef, XSD
from rdflib.namespace import OWL

from karibdis.Application import TaskExecutionUI
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO


# -------------------- Static test data --------------------

TASK_1 = URIRef("http://example.org/Task_1_1")
TASK_1_2 = URIRef("http://example.org/Task_1_2")
TASK_2 = URIRef("http://example.org/Task_2_1")

CASE_1 = URIRef("http://example.org/Case_1")
CASE_2 = URIRef("http://example.org/Case_2")

TASK_ACTIVITY = URIRef("http://example.org/Activity_CRP")

pv_role = URIRef("http://example.org/ProcessValue_Role")
pv_activity = URIRef("http://example.org/ProcessValue_Activity")

medical_role = URIRef("http://example.org/MedicalRole")
doctor_role = URIRef("http://example.org/DoctorRole")
nurse_role = URIRef("http://example.org/NurseRole")

senior_doctor = URIRef("http://example.org/SeniorDoctor")
junior_nurse = URIRef("http://example.org/JuniorNurse")
medical_technician = URIRef("http://example.org/MedicalTechnician")

ADD_VALUE_BUTTON = "Add a new value"
RELOAD_TASKS_BUTTON = "Reload Tasks"


basic_test_values = {
    XSD.boolean: True,
    XSD.integer: 100,
    XSD.float: 55.55,
    XSD.string: "Test",
    BPO.Role: URIRef("http://infs.cit.tum.de/karibdis/baseontology/Admin"),
    BPO.Activity: URIRef("http://example.org/Activity_LacticAcid"),
}


# -------------------- Fixtures --------------------


@pytest.fixture(scope="function")
def system_test_data(request):
    if hasattr(request, "param"):
        config = request.param
    else:
        config = {}

    system = KnowledgeGraphBPMS()
    pkg = system.pkg
    engine = system.engine
    activity_pvs = config.get(
        "activity_pvs",
        [XSD.integer, XSD.float, XSD.string, XSD.boolean, BPO.Role, BPO.Activity],
    )

    pkg.bind("log", "http://example.org/", override=True)
    activity_curie_list = [
        "log:Activity_CRP",
        "log:Activity_LacticAcid",
        "log:Activity_ER_Triage",
        "log:Activity_Leucocytes",
    ]
    for curie in activity_curie_list:
        activity = pkg.namespace_manager.expand_curie(curie)
        pkg.add((activity, RDF.type, BPO.Activity))
        pkg.add((activity, RDFS.label, Literal(curie.split(":", 1)[1])))

    activity_list = list(pkg.subjects(predicate=RDF.type, object=BPO.Activity))
    for dtype in [XSD.integer, XSD.float, XSD.string, XSD.boolean, BPO.Role, BPO.Activity]:
        example_pv = _pv_for(dtype)
        pkg.add((example_pv, RDF.type, BPO.ProcessValue))
        pkg.add((example_pv, BPO.dataType, dtype))
        if dtype in activity_pvs:
            for activity in activity_list:
                pkg.add((activity, BPO.writesValue, example_pv))

    roles_curie_list = [":Doctor", ":Nurse", ":Admin"]
    for curie in roles_curie_list:
        role_to_add = pkg.namespace_manager.expand_curie(curie)
        pkg.add((role_to_add, RDF.type, BPO.Role))
        pkg.add((role_to_add, RDFS.label, Literal(curie.split(":", 1)[1])))

    assert len(list(engine.open_decisions())) == 0, "Unexpected open decisions found"
    engine.open_new_case()

    pkg.add((TASK_1, BPO.instanceOf, TASK_ACTIVITY))

    engine.deduce()
    assert len(list(engine.open_tasks())) == 1
    assert (TASK_1, RDF.type, BPO.Task) in pkg, "Task not found in knowledge graph"
    yield pkg, engine


@pytest.fixture(scope="function")
def system_test_data_subclasses(request, system_test_data):
    """Add subclass hierarchies for entity PV option expansion."""
    pkg, engine = system_test_data

    if not hasattr(request, "param"):
        return pkg, engine

    if request.param == "medical_roles":
        # Medical role hierarchy
        for role in [medical_role, doctor_role, nurse_role]:
            pkg.add((role, RDF.type, RDFS.Class))
            if role != medical_role:
                pkg.add((role, RDFS.subClassOf, medical_role))
            else:
                pkg.add((role, RDFS.subClassOf, BPO.Role))
            pkg.add((role, RDFS.label, Literal(role.split("/")[-1])))

        # Instances
        pkg.add((medical_technician, RDF.type, medical_role))
        pkg.add((medical_technician, RDFS.label, Literal("Medical Technician")))

        pkg.add((senior_doctor, RDF.type, doctor_role))
        pkg.add((senior_doctor, RDFS.label, Literal("Senior Doctor")))

        pkg.add((junior_nurse, RDF.type, nurse_role))
        pkg.add((junior_nurse, RDFS.label, Literal("Junior Nurse")))

    return pkg, engine


# -------------------- UI helpers --------------------


def _render(engine, page_session: playwright.sync_api.Page):
    display(TaskExecutionUI(engine))
    page_session.get_by_role("button", name=RELOAD_TASKS_BUTTON).click()


def _pv_row_label(dtype: URIRef) -> str:
    # The UI shows the PV label stripped of prefix; in this test setup it matches the URI tail.
    return str(_pv_for(dtype)).rsplit("/", 1)[-1]


def _pv_row_text_selector(dtype: URIRef) -> str:
    # Anchor selectors to a *visible* PV row label to avoid matching hidden <option> texts
    # from the "Add new process value" dialog.
    return f':text("{_pv_row_label(dtype)}"):visible'


def _scalar_inputs(page_session: playwright.sync_api.Page, dtype: URIRef):
    return page_session.locator(f'input:right-of({_pv_row_text_selector(dtype)})')


def _scalar_checkbox(page_session: playwright.sync_api.Page, dtype: URIRef):
    return page_session.locator(f':right-of({_pv_row_text_selector(dtype)})').get_by_role("checkbox")


def _entity_dropdown(page_session: playwright.sync_api.Page, dtype: URIRef):
    return page_session.locator(f'select:right-of({_pv_row_text_selector(dtype)})')


def _row_delete_button(page_session: playwright.sync_api.Page, dtype: URIRef):
    return page_session.locator(f'button.mod-danger:right-of({_pv_row_text_selector(dtype)})').first


def _instance_delete_buttons(page_session: playwright.sync_api.Page, dtype: URIRef):
    return page_session.locator(
        f'button:not(.mod-danger):right-of({_pv_row_text_selector(dtype)}):has-text("×")'
    )


def _add_pv_dropdown(page_session: playwright.sync_api.Page):
    """Locates the add-process-value dropdown by its placeholder option."""
    return page_session.locator('select').filter(
        has=page_session.locator('option', has_text="Add a process value")
    )


def _add_pv(page_session: playwright.sync_api.Page, dtype: URIRef):
    # ipywidgets Dropdown renders <option value="0">Label</option> (value is an index),
    # so we must select by visible label, not by underlying Python value.
    dropdown = _add_pv_dropdown(page_session)
    dropdown.locator("option", has_text=_pv_row_label(dtype)).first.wait_for(state="attached")
    dropdown.select_option(label=_pv_row_label(dtype))


# ==================== Submit ====================


class TestSubmitTask:
    def test_submit_with_defaults_writes_scalar_defaults_only(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Submitting without edits writes scalar defaults and does not emit EMPTY entity values."""
        pkg, engine = system_test_data
        _render(engine, page_session)

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assert (TASK_1, BPO.completedAt, None) in pkg

        expected_defaults = {
            XSD.integer: 0,
            XSD.float: 0.0,
            XSD.string: "",
            XSD.boolean: False,
        }
        for dtype, expected_value in expected_defaults.items():
            actual_value = pkg.value(subject=CASE_1, predicate=_pv_for(dtype)).toPython()
            assert actual_value == expected_value

        assert pkg.value(subject=CASE_1, predicate=_pv_for(BPO.Role)) is None
        assert pkg.value(subject=CASE_1, predicate=_pv_for(BPO.Activity)) is None

    def test_submit_with_explicit_values_writes_all_types(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        _scalar_inputs(page_session, XSD.integer).first.fill(str(basic_test_values[XSD.integer]))
        _scalar_inputs(page_session, XSD.float).first.fill(str(basic_test_values[XSD.float]))
        _scalar_inputs(page_session, XSD.string).first.fill(basic_test_values[XSD.string])
        _scalar_checkbox(page_session, XSD.boolean).first.check()
        _entity_dropdown(page_session, BPO.Role).first.select_option(str(pkg.label(basic_test_values[BPO.Role])))
        _entity_dropdown(page_session, BPO.Activity).first.select_option(str(pkg.label(basic_test_values[BPO.Activity])))

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assert (TASK_1, BPO.completedAt, None) in pkg

        for dtype, expected_value in basic_test_values.items():
            if dtype in [BPO.Role, BPO.Activity]:
                expected_value = str(expected_value)
            actual_value = pkg.value(subject=CASE_1, predicate=_pv_for(dtype)).toPython()
            assert actual_value == expected_value


# ==================== Task list / cases ====================


class TestTaskListAndCases:
    def test_multiple_tasks_displayed_and_one_task_completed(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        engine.open_new_case()
        _assign_activity_to_task(pkg, TASK_2, "log:Activity_LacticAcid")
        _wait_for_task(engine, 2)

        _render(engine, page_session)

        expect(page_session.get_by_role("button").get_by_text("Task_1_1")).to_be_visible()
        expect(page_session.get_by_role("button").get_by_text("Task_2_1")).to_be_visible()

        page_session.get_by_text("Task_2_1").first.click()
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 1)

        assert (TASK_2, BPO.completedAt, None) in pkg
        assert (TASK_1, BPO.completedAt, None) not in pkg

    def test_only_open_tasks_displayed(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        engine.open_new_case()
        _assign_activity_to_task(pkg, TASK_2, "log:Activity_Leucocytes")
        _wait_for_task(engine, 2)

        # create a third case with no active tasks
        engine.open_new_case()
        case_3 = URIRef("http://example.org/Case_3")
        task_3 = URIRef("http://example.org/Task_3_1")
        assert (task_3, RDF.type, BPO.Task) in pkg
        assert (case_3, RDF.type, BPO.Case) in pkg

        # mark first task as completed
        pkg.add((TASK_1, BPO.completedAt, Literal("2020-01-01T00:00:00", datatype=XSD.dateTime)))

        _render(engine, page_session)
        _wait_for_task(engine, 1)

        expect(page_session.get_by_role("button").get_by_text("Task_1_1")).not_to_be_visible()
        expect(page_session.get_by_role("button").get_by_text("Task_2_1")).to_be_visible()
        expect(page_session.get_by_role("button").get_by_text("Task_3_1")).not_to_be_visible()

    def test_values_attached_to_correct_case(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        engine.open_new_case()
        _assign_activity_to_task(pkg, TASK_2, "log:Activity_LacticAcid")
        _wait_for_task(engine, 2)

        _render(engine, page_session)

        page_session.get_by_text("Task_2_1").first.click()
        _scalar_inputs(page_session, XSD.integer).first.fill("20")
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 1)

        val_submitted = pkg.value(subject=CASE_2, predicate=_pv_for(XSD.integer))
        assert val_submitted is not None and val_submitted.toPython() == 20

        val_orig = pkg.value(subject=CASE_1, predicate=_pv_for(XSD.integer))
        assert val_orig is None


# ==================== Persistence ====================


class TestValuePersistence:
    def test_load_existing_values_into_ui(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Future tasks for the same case should load existing submitted values into widgets."""
        pkg, engine = system_test_data

        _render(engine, page_session)

        _scalar_inputs(page_session, XSD.integer).first.fill(str(basic_test_values[XSD.integer]))
        _scalar_inputs(page_session, XSD.float).first.fill(str(basic_test_values[XSD.float]))
        _scalar_inputs(page_session, XSD.string).first.fill(basic_test_values[XSD.string])
        _scalar_checkbox(page_session, XSD.boolean).first.check()
        _entity_dropdown(page_session, BPO.Role).first.select_option(str(pkg.label(basic_test_values[BPO.Role])))
        _entity_dropdown(page_session, BPO.Activity).first.select_option(str(pkg.label(basic_test_values[BPO.Activity])))

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        _assign_activity_to_task(pkg, TASK_1_2, "log:Activity_CRP")
        _wait_for_task(engine, 1)
        page_session.get_by_role("button", name=RELOAD_TASKS_BUTTON).click()
        page_session.get_by_text("Task_1_2").first.click()

        expect(_scalar_inputs(page_session, XSD.integer).first).to_have_value(str(basic_test_values[XSD.integer]))
        expect(_scalar_inputs(page_session, XSD.float).first).to_have_value(str(basic_test_values[XSD.float]))
        expect(_scalar_inputs(page_session, XSD.string).first).to_have_value(basic_test_values[XSD.string])
        expect(_scalar_checkbox(page_session, XSD.boolean).first).to_be_checked()
        expect(page_session.locator(f':text-is("{pkg.label(basic_test_values[BPO.Role])}")')).to_be_visible()
        expect(page_session.locator(f':text-is("{pkg.label(basic_test_values[BPO.Activity])}")')).to_be_visible()


# ==================== Add PV to form ====================


class TestAddProcessValue:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.integer, BPO.Role]}], indirect=True)
    def test_add_process_value_row_and_submit(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        expect(page_session.get_by_text("ProcessValue_integer")).to_be_visible()
        expect(page_session.get_by_text("ProcessValue_Role")).to_be_visible()
        expect(page_session.get_by_text("ProcessValue_string")).not_to_be_visible()
        expect(page_session.get_by_text("ProcessValue_float")).not_to_be_visible()

        _add_pv(page_session,XSD.string)
        expect(page_session.get_by_text("ProcessValue_string")).to_be_visible()

        _add_pv(page_session,XSD.float)
        expect(page_session.get_by_text("ProcessValue_float")).to_be_visible()

        _scalar_inputs(page_session, XSD.string).first.fill("Added String")
        _scalar_inputs(page_session, XSD.float).first.fill("99.99")
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assert pkg.value(subject=CASE_1, predicate=_pv_for(XSD.string)).toPython() == "Added String"
        assert pkg.value(subject=CASE_1, predicate=_pv_for(XSD.float)).toPython() == 99.99

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.integer, BPO.Role]}], indirect=True)
    def test_added_process_value_persists_across_tasks_in_same_case(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        _add_pv(page_session,XSD.string)
        _scalar_inputs(page_session, XSD.string).first.fill("First Task Value")
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        _assign_activity_to_task(pkg, TASK_1_2, "log:Activity_CRP")
        _wait_for_task(engine, 1)
        page_session.get_by_role("button", name=RELOAD_TASKS_BUTTON).click()
        expect(page_session.get_by_text("Task_1_2").first).to_be_visible()

        # PV row is activity-based; should not appear unless re-added.
        expect(page_session.get_by_text("ProcessValue_string")).not_to_be_visible()

        _add_pv(page_session,XSD.string)
        expect(_scalar_inputs(page_session, XSD.string).first).to_have_value("First Task Value")


# ==================== Functional vs non-functional PVs ====================


class TestFunctionalProcessValues:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_functional_entity_has_single_dropdown_and_no_instance_deletes(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        role_pv = _pv_for(BPO.Role)
        pkg.add((role_pv, RDF.type, OWL.FunctionalProperty))

        _render(engine, page_session)

        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(1)
        expect(_instance_delete_buttons(page_session, BPO.Role)).to_have_count(0)

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_functional_entity_overrides_existing_value_on_submit(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        role_pv = _pv_for(BPO.Role)
        pkg.add((role_pv, RDF.type, OWL.FunctionalProperty))

        doctor = URIRef("http://infs.cit.tum.de/karibdis/baseontology/Doctor")
        admin = URIRef("http://infs.cit.tum.de/karibdis/baseontology/Admin")
        pkg.add((CASE_1, role_pv, doctor))

        _render(engine, page_session)

        expect(_entity_dropdown(page_session, BPO.Role).first).to_have_value(str(pkg.label(doctor)))
        _entity_dropdown(page_session, BPO.Role).first.select_option(str(pkg.label(admin)))

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assigned = list(pkg.objects(subject=CASE_1, predicate=role_pv))
        assert len(assigned) == 1
        assert admin in assigned

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.integer]}], indirect=True)
    def test_functional_scalar_has_no_multi_value_controls(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        int_pv = _pv_for(XSD.integer)
        pkg.add((int_pv, RDF.type, OWL.FunctionalProperty))

        _render(engine, page_session)

        expect(_scalar_inputs(page_session, XSD.integer)).to_have_count(1)
        expect(_instance_delete_buttons(page_session, XSD.integer)).to_have_count(0)
        expect(page_session.get_by_role("button", name=ADD_VALUE_BUTTON)).not_to_be_visible()


# ==================== Entity multi-values (non-functional) ====================


class TestEntityMultipleValues:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    @pytest.mark.parametrize("system_test_data_subclasses", ["medical_roles"], indirect=True)
    def test_subclass_instances_appear_and_can_be_selected(self, system_test_data_subclasses, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data_subclasses

        _render(engine, page_session)

        role_dropdown = _entity_dropdown(page_session, BPO.Role).first
        expect(role_dropdown).to_contain_text("Senior Doctor")
        expect(role_dropdown).to_contain_text("Junior Nurse")
        expect(role_dropdown).to_contain_text("Medical Technician")

        role_dropdown.select_option("Senior Doctor")
        expect(page_session.get_by_text("Senior Doctor")).to_be_visible()

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        role_pv = _pv_for(BPO.Role)
        assigned_role = pkg.value(subject=CASE_1, predicate=role_pv)
        assert assigned_role == senior_doctor

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    @pytest.mark.parametrize("system_test_data_subclasses", ["medical_roles"], indirect=True)
    def test_multiple_entity_values_saved(self, system_test_data_subclasses, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data_subclasses

        _render(engine, page_session)

        role_dropdown = _entity_dropdown(page_session, BPO.Role).first
        role_dropdown.select_option("Senior Doctor")
        role_dropdown.select_option("Junior Nurse")
        role_dropdown.select_option("Medical Technician")

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        role_pv = _pv_for(BPO.Role)
        assigned_roles = list(pkg.objects(subject=CASE_1, predicate=role_pv))
        assert set(assigned_roles) == {senior_doctor, junior_nurse, medical_technician}

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": []}], indirect=True)
    @pytest.mark.parametrize("system_test_data_subclasses", ["medical_roles"], indirect=True)
    def test_existing_entity_values_loaded_as_label_rows(self, system_test_data_subclasses, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data_subclasses

        role_pv = _pv_for(BPO.Role)
        pkg.add((CASE_1, role_pv, senior_doctor))
        pkg.add((CASE_1, role_pv, junior_nurse))

        _render(engine, page_session)
        _add_pv(page_session,BPO.Role)

        instance_deletes = _instance_delete_buttons(page_session, BPO.Role)
        expect(instance_deletes).to_have_count(2)
        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(1)

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assigned_roles = list(pkg.objects(subject=CASE_1, predicate=role_pv))
        assert set(assigned_roles) == {senior_doctor, junior_nurse}

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": []}], indirect=True)
    @pytest.mark.parametrize("system_test_data_subclasses", ["medical_roles"], indirect=True)
    def test_deleted_entity_instance_removed_from_graph(self, system_test_data_subclasses, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data_subclasses

        role_pv = _pv_for(BPO.Role)
        pkg.add((CASE_1, role_pv, senior_doctor))
        pkg.add((CASE_1, role_pv, junior_nurse))

        _render(engine, page_session)
        _add_pv(page_session,BPO.Role)

        instance_deletes = _instance_delete_buttons(page_session, BPO.Role)
        expect(instance_deletes).to_have_count(2)

        instance_deletes.first.click()
        expect(_instance_delete_buttons(page_session, BPO.Role)).to_have_count(1)

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assigned_roles = list(pkg.objects(subject=CASE_1, predicate=role_pv))
        assert len(assigned_roles) == 1
        assert assigned_roles[0] in {senior_doctor, junior_nurse}

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_entity_dropdown_disappears_when_all_selected(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        _render(engine, page_session)

        role_dropdown = _entity_dropdown(page_session, BPO.Role)
        expect(role_dropdown).to_have_count(1)

        role_dropdown.first.select_option("Doctor")
        role_dropdown.first.select_option("Nurse")
        role_dropdown.first.select_option("Admin")

        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(0)

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_entity_dropdown_reappears_after_instance_delete(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        _render(engine, page_session)

        role_dropdown = _entity_dropdown(page_session, BPO.Role)
        role_dropdown.first.select_option("Doctor")
        role_dropdown.first.select_option("Nurse")
        role_dropdown.first.select_option("Admin")
        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(0)

        _instance_delete_buttons(page_session, BPO.Role).first.click()
        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(1)


# ==================== Scalar multi-values ====================


class TestScalarMultipleValues:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.string]}], indirect=True)
    def test_multiple_string_inputs_via_add_button_saved(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        _render(engine, page_session)

        string_inputs = _scalar_inputs(page_session, XSD.string)
        expect(string_inputs).to_have_count(1)

        add_btn = page_session.get_by_role("button", name=ADD_VALUE_BUTTON)
        add_btn.first.click()
        add_btn.first.click()
        expect(string_inputs).to_have_count(3)

        string_inputs.nth(0).fill("First Value")
        string_inputs.nth(1).fill("Second Value")
        string_inputs.nth(2).fill("Third Value")

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        string_pv = _pv_for(XSD.string)
        assigned_strings = [str(val) for val in pkg.objects(subject=CASE_1, predicate=string_pv)]
        assert set(assigned_strings) >= {"First Value", "Second Value", "Third Value"}

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.string]}], indirect=True)
    def test_per_instance_delete_remapping_preserves_values_and_order(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        _render(engine, page_session)

        add_btn = page_session.get_by_role("button", name=ADD_VALUE_BUTTON)
        add_btn.first.click()
        add_btn.first.click()

        string_inputs = _scalar_inputs(page_session, XSD.string)
        string_inputs.nth(0).fill("Alpha")
        string_inputs.nth(1).fill("Beta")
        string_inputs.nth(2).fill("Gamma")

        _instance_delete_buttons(page_session, XSD.string).nth(1).click()

        expect(string_inputs).to_have_count(2)
        expect(string_inputs.nth(0)).to_have_value("Alpha")
        expect(string_inputs.nth(1)).to_have_value("Gamma")

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assigned = [str(v) for v in pkg.objects(subject=CASE_1, predicate=_pv_for(XSD.string))]
        assert "Alpha" in assigned
        assert "Gamma" in assigned
        assert "Beta" not in assigned

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_existing_non_entity_values_displayed_and_removable(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        str_pv = _pv_for(XSD.string)
        pkg.add((CASE_1, str_pv, Literal("keep", datatype=XSD.string)))
        pkg.add((CASE_1, str_pv, Literal("remove_me", datatype=XSD.string)))

        _render(engine, page_session)
        _add_pv(page_session,XSD.string)

        string_inputs = _scalar_inputs(page_session, XSD.string)
        expect(string_inputs).to_have_count(2)

        # Remove the instance with value "remove_me".
        remove_idx = next(i for i in range(2) if string_inputs.nth(i).input_value() == "remove_me")
        _instance_delete_buttons(page_session, XSD.string).nth(remove_idx).click()
        expect(string_inputs).to_have_count(1)

        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assigned = [str(v) for v in pkg.objects(subject=CASE_1, predicate=str_pv)]
        assert "keep" in assigned
        assert "remove_me" not in assigned


class TestBooleanNonFunctional:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.boolean]}], indirect=True)
    def test_boolean_has_no_add_value_button_and_submits(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        _render(engine, page_session)
        expect(page_session.get_by_role("button", name=ADD_VALUE_BUTTON)).not_to_be_visible()

        _scalar_checkbox(page_session, XSD.boolean).first.check()
        page_session.get_by_role("button", name="Submit").click()
        _wait_for_task(engine, 0)

        assert pkg.value(subject=CASE_1, predicate=_pv_for(XSD.boolean)).toPython() is True


# ==================== Delete PV rows ====================


class TestProcessValueDeletion:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.string, XSD.integer]}], indirect=True)
    def test_delete_single_scalar_pv_row(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        expect(page_session.get_by_text("ProcessValue_string")).to_be_visible()
        expect(page_session.get_by_text("ProcessValue_integer")).to_be_visible()

        _row_delete_button(page_session, XSD.string).click()

        expect(page_session.get_by_text("ProcessValue_string")).not_to_be_visible()
        expect(page_session.get_by_text("ProcessValue_integer")).to_be_visible()

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_delete_entity_pv_row(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        expect(page_session.get_by_text("ProcessValue_Role")).to_be_visible()
        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(1)

        _row_delete_button(page_session, BPO.Role).click()
        expect(page_session.get_by_text("ProcessValue_Role")).not_to_be_visible()

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_delete_and_readd_entity_row_starts_fresh(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        _entity_dropdown(page_session, BPO.Role).first.select_option(str(pkg.label(basic_test_values[BPO.Role])))
        expect(_instance_delete_buttons(page_session, BPO.Role)).to_have_count(1)

        _row_delete_button(page_session, BPO.Role).click()
        _add_pv(page_session,BPO.Role)

        expect(_entity_dropdown(page_session, BPO.Role)).to_have_count(1)
        expect(_instance_delete_buttons(page_session, BPO.Role)).to_have_count(0)


# ==================== Add-value defaults ====================


class TestAddValueButton:
    @pytest.mark.parametrize(
        "system_test_data, dtype, expected_default",
        [
            ({"activity_pvs": [XSD.integer]}, XSD.integer, "0"),
            ({"activity_pvs": [XSD.float]}, XSD.float, "0.0"),
            ({"activity_pvs": [XSD.string]}, XSD.string, ""),
        ],
        indirect=["system_test_data"],
    )
    def test_add_value_creates_additional_input_with_default(
        self,
        system_test_data,
        dtype,
        expected_default,
        solara_test,
        page_session: playwright.sync_api.Page,
    ):
        pkg, engine = system_test_data
        _render(engine, page_session)

        inputs = _scalar_inputs(page_session, dtype)
        expect(inputs).to_have_count(1)
        page_session.get_by_role("button", name=ADD_VALUE_BUTTON).first.click()
        expect(inputs).to_have_count(2)
        if dtype == XSD.float:
            # Browser may normalize number inputs like "0.0" -> "0".
            assert float(inputs.nth(1).input_value()) == float(expected_default)
        else:
            expect(inputs.nth(1)).to_have_value(expected_default)


# ==================== Add PV dropdown filtering ====================


class TestAddPVDropdown:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role, XSD.string]}], indirect=True)
    def test_dropdown_excludes_pvs_already_in_form(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        dropdown = _add_pv_dropdown(page_session)
        expect(dropdown).not_to_contain_text("ProcessValue_Role")
        expect(dropdown).not_to_contain_text("ProcessValue_string")
        expect(dropdown).to_contain_text("ProcessValue_integer")

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.string]}], indirect=True)
    def test_dropdown_shows_pv_after_row_deletion(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data
        _render(engine, page_session)

        _row_delete_button(page_session, XSD.string).click()
        expect(page_session.get_by_text("ProcessValue_string")).not_to_be_visible()

        expect(_add_pv_dropdown(page_session)).to_contain_text("ProcessValue_string")

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_add_pv_with_existing_case_values_loads_them(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        pkg, engine = system_test_data

        str_pv = _pv_for(XSD.string)
        pkg.add((CASE_1, str_pv, Literal("existing1", datatype=XSD.string)))
        pkg.add((CASE_1, str_pv, Literal("existing2", datatype=XSD.string)))

        _render(engine, page_session)
        _add_pv(page_session, XSD.string)

        string_inputs = _scalar_inputs(page_session, XSD.string)
        expect(string_inputs).to_have_count(2)


# ==================== Input focus ====================


def _assert_focused(locator, timeout=5000):
    """Assert an input has focus via Playwright's native focus check."""
    expect(locator).to_be_focused(timeout=timeout)


class TestInputFocus:
    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [BPO.Role]}], indirect=True)
    def test_input_focused_after_add_pv_dropdown(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Selecting a PV from the add-PV dropdown should auto-focus its first input."""
        pkg, engine = system_test_data
        _render(engine, page_session)

        _add_pv(page_session, XSD.string)

        _assert_focused(_scalar_inputs(page_session, XSD.string).first)

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.string]}], indirect=True)
    def test_input_focused_after_add_pv_dropdown_integer(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Focus also works for numeric (IntText) inputs added via the dropdown."""
        pkg, engine = system_test_data
        _render(engine, page_session)

        _add_pv(page_session, XSD.integer)

        _assert_focused(_scalar_inputs(page_session, XSD.integer).first)

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.string]}], indirect=True)
    def test_input_focused_after_add_value_button(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Clicking 'Add a new value' should auto-focus the newly created input."""
        pkg, engine = system_test_data
        _render(engine, page_session)

        page_session.get_by_role("button", name=ADD_VALUE_BUTTON).first.click()

        _assert_focused(_scalar_inputs(page_session, XSD.string).last)

    @pytest.mark.parametrize("system_test_data", [{"activity_pvs": [XSD.integer]}], indirect=True)
    def test_input_focused_after_add_value_button_integer(self, system_test_data, solara_test, page_session: playwright.sync_api.Page):
        """Focus works for integer inputs added via 'Add a new value'."""
        pkg, engine = system_test_data
        _render(engine, page_session)

        page_session.get_by_role("button", name=ADD_VALUE_BUTTON).first.click()

        _assert_focused(_scalar_inputs(page_session, XSD.integer).last)


# -------------------- Helper functions --------------------


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
    raise AssertionError(
        f"open_tasks count not {expected_count} after timeout, current count: {len(tasks)}"
    )


def _pv_for(dtype):
    # attach the last part of the dtype URI (after the last '/')
    if dtype == BPO.Role:
        return pv_role
    if dtype == BPO.Activity:
        return pv_activity
    name = dtype.fragment
    return URIRef(f"http://example.org/ProcessValue_{name}")


def _assign_activity_to_task(pkg, task_uri, activity_curie):
    # assign activity to undecided task
    activity = pkg.namespace_manager.expand_curie(activity_curie)
    pkg.add((task_uri, BPO.instanceOf, activity))
