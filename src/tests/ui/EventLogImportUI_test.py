import importlib.resources
import time

import pytest
import reacton
import reacton.ipywidgets as w
from pm4py import discover_declare
from IPython.display import display
from playwright.sync_api import Page, expect
from rdflib import RDF, OWL, URIRef

from karibdis.KnowledgeImporter import SimpleEventLogImporter, read_event_log
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.ui.KnowledgeModelingUI import KnowledgeModelingUI
from karibdis.ui.toast import ToastHost, _dispatch
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO

EX = 'http://example.org/'
DATA = importlib.resources.files('tests').joinpath('data')
INIT = URIRef('http://infs.cit.tum.de/karibdis/declare/init')

# Same small repair process in each format, see tests/KnowledgeImporter_test.py
EVENT_LOG_FILES = ['repair_log.xes', 'repair_log.csv', 'repair_log_common_columns.csv']
IMPORT_TIMEOUT = 30000
# Defaults of the DiscoveryUI
DECLARE_TEMPLATES = ['init', 'chainresponse', 'exactly_one', 'responded_existence', 'response', 'precedence']


@reacton.component
def ModelingWithToasts(pkg):
    """Mounts the toast host next to the modeling UI, as the application does"""
    with w.VBox() as main:
        KnowledgeModelingUI(pkg)
        ToastHost()
    return main

def open_event_log_import(page: Page, pkg):
    display(ModelingWithToasts(pkg))
    page.get_by_role('button', name='Event Log').click()
    expect(page.get_by_text('Upload Event Log to be Extracted From')).to_be_visible()

def programmatic_import(path):
    pkg = ProcessKnowledgeGraph()
    before = set(pkg)
    log = read_event_log(path)
    importer = SimpleEventLogImporter(pkg)
    importer.import_event_log_entities(log)
    importer.import_declare(discover_declare(log, allowed_templates=DECLARE_TEMPLATES, min_support_ratio=0.8, min_confidence_ratio=0.8))
    importer.load()
    return set(pkg) - before

def open_file_chooser(page: Page):
    with page.expect_file_chooser() as file_chooser:
        page.get_by_role('button', name='Upload Event Log File').click()
    return file_chooser.value

def upload(page: Page, path):
    open_file_chooser(page).set_files(str(path))

def column_type_select(page: Page, column):
    """The column grid lists attribute label, type dropdown and alias dropdown per column."""
    cells = page.locator('.widget-gridbox > *')
    labels = cells.all_inner_texts()
    return cells.nth(labels.index(column) + 1).locator('select')

def expect_column_grid(page: Page):
    expect(page.get_by_text('Determine Column Imports')).to_be_visible(timeout=IMPORT_TIMEOUT)
    expect(page.get_by_role('button', name='Load Entities')).to_be_visible()

def complete_import(page: Page):
    """Click through entity loading, declare discovery, alignment and validation."""
    page.get_by_role('button', name='Load Entities').click()
    page.get_by_role('button', name='Discover').click(timeout=IMPORT_TIMEOUT)
    page.get_by_role('button', name='Load Constraints').click(timeout=IMPORT_TIMEOUT)
    # Alignment (skipped)
    expect(page.get_by_role('button', name='Automated Alignment')).to_be_visible(timeout=IMPORT_TIMEOUT)
    page.get_by_role('button', name='Accept').click()
    # Validation
    expect(page.get_by_role('button', name='Go back to Alignment')).to_be_visible(timeout=IMPORT_TIMEOUT)
    page.get_by_role('button', name='Accept').click()
    expect(page.get_by_role('button', name='Event Log')).to_be_visible(timeout=IMPORT_TIMEOUT)


def test_upload_accepts_xes_and_csv(solara_test, page_session: Page):
    open_event_log_import(page_session, ProcessKnowledgeGraph())
    accept = open_file_chooser(page_session).element.get_attribute('accept')
    assert set(accept.split(',')) == {'.xes', '.csv'}


@pytest.mark.parametrize('filename', EVENT_LOG_FILES)
def test_upload_shows_columns(solara_test, page_session: Page, filename):
    open_event_log_import(page_session, ProcessKnowledgeGraph())
    upload(page_session, DATA.joinpath(filename))
    expect_column_grid(page_session)

    for column in ['case:concept:name', 'concept:name', 'org:resource', 'time:timestamp', 'phoneType', 'cost', 'defectFixed']:
        expect(page_session.get_by_text(column, exact=True)).to_be_visible()
    # Key columns of csv logs are shown by their standard names
    for column in ['Case ID', 'Activity', 'Resource', 'Complete Timestamp']:
        expect(page_session.get_by_text(column, exact=True)).to_have_count(0)

    expect(column_type_select(page_session, 'phoneType')).to_have_value('ENTITY')
    expect(column_type_select(page_session, 'cost')).to_have_value('VALUE')
    expect(column_type_select(page_session, 'defectFixed')).to_have_value('VALUE')


@pytest.mark.parametrize('filename', EVENT_LOG_FILES)
def test_import_into_knowledge_graph(solara_test, page_session: Page, filename):
    pkg = ProcessKnowledgeGraph()
    before = set(pkg)
    open_event_log_import(page_session, pkg)
    upload(page_session, DATA.joinpath(filename))
    expect_column_grid(page_session)
    complete_import(page_session)

    assert set(pkg) - before == programmatic_import(DATA.joinpath(filename))
    if filename != 'repair_log_common_columns.csv': # Has an additional start timestamp column
        assert set(pkg) - before == programmatic_import(DATA.joinpath('repair_log.xes'))

    register = URIRef(EX + 'Activity_Register')
    assert (register, RDF.type, BPO.Activity) in pkg
    assert (URIRef(EX + 'Activity_Inform%20User'), RDF.type, BPO.Activity) in pkg
    assert (URIRef(EX + 'Resource_Tester1'), RDF.type, BPO.Resource) in pkg
    assert (URIRef(EX + 'phoneType_T1'), RDF.type, URIRef(EX + 'type_phoneType')) in pkg
    assert (URIRef(EX + 'ProcessValue_cost'), RDF.type, BPO.ProcessValue) in pkg
    assert (URIRef(EX + 'Activity_Repair'), BPO.writesValue, URIRef(EX + 'ProcessValue_cost')) in pkg
    assert (register, INIT, register) in pkg # Discovered from the uploaded log


def test_csv_column_type_change(solara_test, page_session: Page):
    pkg = ProcessKnowledgeGraph()
    open_event_log_import(page_session, pkg)
    upload(page_session, DATA.joinpath('repair_log.csv'))
    expect_column_grid(page_session)

    column_type_select(page_session, 'phoneType').select_option('IGNORE')
    expect(column_type_select(page_session, 'phoneType')).to_have_value('IGNORE')
    complete_import(page_session)

    assert (URIRef(EX + 'type_phoneType'), RDF.type, OWL.Class) not in pkg
    assert (URIRef(EX + 'Activity_Register'), RDF.type, BPO.Activity) in pkg


def test_unreadable_csv_shows_error(solara_test, page_session: Page, tmp_path, monkeypatch):
    path = tmp_path / 'no_activities.csv'
    path.write_text('case,foo\n1,A\n')
    monkeypatch.setitem(_dispatch, 'push', None) # Wait for this test's toast host
    open_event_log_import(page_session, ProcessKnowledgeGraph())
    deadline = time.time() + 5
    while _dispatch['push'] is None and time.time() < deadline:
        time.sleep(0.02)
    assert _dispatch['push'] is not None, 'ToastHost never registered'
    upload(page_session, path)

    expect(page_session.get_by_text('Could not read event log')).to_be_visible(timeout=IMPORT_TIMEOUT)
    # User can retry with another file
    expect(page_session.get_by_text('Upload Event Log to be Extracted From')).to_be_visible()
    upload(page_session, DATA.joinpath('repair_log.csv'))
    expect_column_grid(page_session)
