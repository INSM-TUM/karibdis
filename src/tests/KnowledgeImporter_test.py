import importlib.resources

import pandas as pd
import pm4py
import pytest
from rdflib import Graph, URIRef, RDF, RDFS, OWL, XSD, Literal
from rdflib.compare import isomorphic

from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.KnowledgeImporter import SimpleEventLogImporter, read_event_log, read_csv_event_log, event_log_format
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO

EX = 'http://example.org/'

# Two cases of a small repair process, the csv logs contain the same events as the xes log
DATA = importlib.resources.files('tests').joinpath('data')
XES_LOG = DATA.joinpath('repair_log.xes')
CSV_LOG_STANDARD_COLUMNS = DATA.joinpath('repair_log.csv')
# Common csv export naming (e.g., BPI challenges / Disco) with additional start timestamps, shuffled event order
CSV_LOG_COMMON_COLUMNS = DATA.joinpath('repair_log_common_columns.csv')


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return path

@pytest.fixture
def xes_path():
    return XES_LOG

@pytest.fixture
def csv_path():
    return CSV_LOG_STANDARD_COLUMNS

@pytest.fixture
def common_csv_path():
    return CSV_LOG_COMMON_COLUMNS

def import_entities(log, **importer_args):
    importer = SimpleEventLogImporter(ProcessKnowledgeGraph(), **importer_args)
    importer.import_event_log_entities(log)
    return importer

def events(log):
    return list(log[['case:concept:name', 'concept:name', 'org:resource']].itertuples(index=False, name=None))

EXPECTED_EVENTS = [
    ('1', 'Register', 'System'),
    ('1', 'Repair', 'Tester1'),
    ('1', 'Inform User', 'System'),
    ('2', 'Register', 'System'),
    ('2', 'Inform User', 'Tester2'),
]


class TestEventLogFormat:

    @pytest.mark.parametrize('filename, expected', [
        ('log.xes', 'xes'),
        ('LOG.XES', 'xes'),
        ('some/dir/log.csv', 'csv'),
        ('Log.CSV', 'csv'),
    ])
    def test_supported_formats(self, filename, expected):
        assert event_log_format(filename) == expected

    @pytest.mark.parametrize('filename', ['log.xlsx', 'log.txt', 'log', 'csv.xes.bak'])
    def test_unsupported_formats(self, filename):
        with pytest.raises(ValueError, match='Unsupported event log file'):
            event_log_format(filename)

    def test_read_unsupported_format(self, csv_path):
        with pytest.raises(ValueError, match='Unsupported event log format'):
            read_event_log(csv_path, file_format='parquet')


class TestReadXesEventLog:

    def test_identical_to_pm4py(self, xes_path):
        pd.testing.assert_frame_equal(read_event_log(xes_path), pm4py.read_xes(str(xes_path)))

    def test_standard_columns(self, xes_path):
        log = read_event_log(xes_path)
        assert events(log) == EXPECTED_EVENTS
        assert pd.api.types.is_datetime64_any_dtype(log['time:timestamp'])

    def test_explicit_format_overrides_extension(self, tmp_path):
        # Uploaded files are stored without extension, so the format is passed explicitly
        path = write(tmp_path, 'upload', XES_LOG.read_text())
        assert events(read_event_log(path, file_format='xes')) == EXPECTED_EVENTS

    def test_repair_example(self):
        path = importlib.resources.files('tests').joinpath('repairExample.xes')
        if not path.is_file() or path.read_bytes().startswith(b'version https://git-lfs'):
            pytest.skip('repairExample.xes not available')
        log = read_event_log(path)
        assert len(log) == 11855
        assert log['case:concept:name'].nunique() == 1104


class TestReadCsvEventLog:

    def test_standard_columns(self, csv_path):
        log = read_event_log(csv_path)
        assert events(log) == EXPECTED_EVENTS
        assert str(log['time:timestamp'].dt.tz) == 'UTC'
        assert log['time:timestamp'].iloc[0] == pd.Timestamp('2024-01-01T10:00:00', tz='UTC')

    def test_same_columns_as_xes(self, csv_path, xes_path):
        assert set(read_event_log(csv_path).columns) == set(read_event_log(xes_path).columns)

    def test_detects_common_column_names(self, common_csv_path):
        log = read_event_log(common_csv_path)
        for col in ['case:concept:name', 'concept:name', 'org:resource', 'time:timestamp']:
            assert col in log.columns
        for col in ['Case ID', 'Activity', 'Resource', 'Complete Timestamp']:
            assert col not in log.columns

    def test_orders_events_by_case_and_time(self, common_csv_path):
        assert events(read_event_log(common_csv_path)) == EXPECTED_EVENTS

    def test_parses_other_timestamp_columns(self, common_csv_path):
        log = read_event_log(common_csv_path)
        assert pd.api.types.is_datetime64_any_dtype(log['Start Timestamp'])
        assert log['Start Timestamp'].iloc[0] == pd.Timestamp('2024-01-01T09:30:00', tz='UTC')

    def test_keeps_unparseable_other_timestamp_columns(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,timestamp,timestamp note\n1,A,2024-01-01 10:00,not a date\n')
        log = read_event_log(path)
        assert log['timestamp note'].iloc[0] == 'not a date'

    def test_unparseable_timestamp_column(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,timestamp\n1,A,not a date\n')
        with pytest.raises(ValueError, match='Could not parse timestamps'):
            read_event_log(path)

    def test_timestamp_format(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,timestamp\n1,A,02.01.2024 10:00\n1,B,13.01.2024 10:00\n')
        log = read_event_log(path, timestamp_format='%d.%m.%Y %H:%M')
        assert list(log['time:timestamp'].dt.month) == [1, 1]
        assert list(log['time:timestamp'].dt.day) == [2, 13]

    def test_explicit_columns(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'patient,step,when,who\nP1,Admission,2024-01-01 10:00,Nurse\nP1,Discharge,2024-01-02 10:00,Doctor\n')
        log = read_csv_event_log(path, case_column='patient', activity_column='step', timestamp_column='when', resource_column='who')
        assert events(log) == [('P1', 'Admission', 'Nurse'), ('P1', 'Discharge', 'Doctor')]
        assert pd.api.types.is_datetime64_any_dtype(log['time:timestamp'])

    def test_explicit_columns_override_detection(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,detailed activity\n1,A,A - detail\n')
        log = read_event_log(path, activity_column='detailed activity')
        assert log['concept:name'].iloc[0] == 'A - detail'
        assert log['activity'].iloc[0] == 'A'

    def test_without_timestamp_or_resource(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity\n2,B\n1,A\n2,C\n')
        log = read_event_log(path)
        assert 'time:timestamp' not in log.columns
        assert 'org:resource' not in log.columns
        assert list(zip(log['case:concept:name'], log['concept:name'])) == [('1', 'A'), ('2', 'B'), ('2', 'C')]

    @pytest.mark.parametrize('sep', [';', '\t', '|'])
    def test_sniffs_separator(self, tmp_path, sep):
        path = write(tmp_path, 'log.csv', CSV_LOG_STANDARD_COLUMNS.read_text().replace(',', sep))
        assert events(read_event_log(path)) == EXPECTED_EVENTS

    def test_quoted_separators(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,goal\n1,A,"Other, see explanation"\n1,B,Car\n')
        log = read_event_log(path)
        assert list(log['goal']) == ['Other, see explanation', 'Car']

    def test_explicit_separator(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case;activity\n1;A,B\n')
        log = read_event_log(path, sep=';')
        assert log['concept:name'].iloc[0] == 'A,B'

    def test_numeric_identifiers_become_strings(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,resource\n1,10,7\n1,20,\n2,10,8\n')
        log = read_event_log(path)
        assert list(log['case:concept:name']) == ['1', '1', '2']
        assert list(log['concept:name']) == ['10', '20', '10']
        assert log['org:resource'].iloc[0] == '7' # a string, not 7.0 or 7
        assert pd.isna(log['org:resource'].iloc[1])

    def test_text_not_parsed_as_missing(self, tmp_path):
        # The sepsis log has a case and a diagnosis "NA", which pandas would read as missing by default
        path = write(tmp_path, 'log.csv', 'case,activity,resource,diagnose,value,flag\nNA,null,None,NA,NA,True\nNA,B,,,1,NA\nC,B,,B,2,False\n')
        log = read_event_log(path)
        first, second = log[log['case:concept:name'] == 'NA'].to_dict('records')
        assert first['concept:name'] == 'null'
        assert first['org:resource'] == 'None'
        assert first['diagnose'] == 'NA'
        assert pd.isna(second['org:resource'])
        assert pd.isna(second['diagnose'])
        # Numeric and boolean columns keep the default missing value handling
        assert pd.api.types.is_numeric_dtype(log['value'])
        assert pd.isna(first['value'])
        assert first['flag'] == True
        assert pd.isna(second['flag'])

    def test_value_column_types(self, csv_path):
        log = read_event_log(csv_path)
        assert pd.api.types.is_numeric_dtype(log['cost'])
        assert set(log['defectFixed'].dropna()) == {True, False}

    def test_missing_activity_column(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,foo\n1,A\n')
        with pytest.raises(ValueError, match='concept:name'):
            read_event_log(path)

    def test_missing_case_column(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'activity,foo\nA,1\n')
        with pytest.raises(ValueError, match='case:concept:name'):
            read_event_log(path)

    def test_nonexistent_explicit_column(self, csv_path):
        with pytest.raises(ValueError, match='does not exist'):
            read_event_log(csv_path, case_column='Patient')

    def test_column_used_twice(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity\n1,A\n')
        with pytest.raises(ValueError, match='cannot be used for both'):
            read_event_log(path, case_column='activity', activity_column='activity')

    def test_conflicting_standard_column(self, csv_path):
        with pytest.raises(ValueError, match='already has a column'):
            read_event_log(csv_path, activity_column='phoneType')


class TestSimpleEventLogImporter:

    def test_xes_import(self, xes_path):
        graph = import_entities(read_event_log(xes_path)).addition_graph
        self._assert_expected_entities(graph)

    def test_csv_import(self, csv_path):
        graph = import_entities(read_event_log(csv_path)).addition_graph
        self._assert_expected_entities(graph)

    def test_csv_import_with_common_column_names(self, common_csv_path):
        graph = import_entities(read_event_log(common_csv_path)).addition_graph
        self._assert_expected_entities(graph)
        # Additional timestamp column is imported as value
        start = URIRef(EX + 'ProcessValue_Start%20Timestamp')
        assert (start, BPO.dataType, XSD.dateTimeStamp) in graph

    def test_csv_and_xes_import_identical(self, csv_path, xes_path):
        xes_graph = import_entities(read_event_log(xes_path)).addition_graph
        csv_graph = import_entities(read_event_log(csv_path)).addition_graph
        assert set(csv_graph) == set(xes_graph)
        assert isomorphic(csv_graph, xes_graph)

    def _assert_expected_entities(self, graph):
        # Activities
        for activity in ['Register', 'Repair', 'Inform%20User']:
            node = URIRef(EX + f'Activity_{activity}')
            assert (node, RDF.type, BPO.Activity) in graph
        assert (URIRef(EX + 'Activity_Inform%20User'), RDFS.label, Literal('Inform User')) in graph

        # Resources
        for resource in ['System', 'Tester1', 'Tester2']:
            assert (URIRef(EX + f'Resource_{resource}'), RDF.type, BPO.Resource) in graph

        # Custom entity column gets its own class
        phone_type = URIRef(EX + 'type_phoneType')
        assert (phone_type, RDF.type, OWL.Class) in graph
        assert (URIRef(EX + 'phoneType_T1'), RDF.type, phone_type) in graph
        assert (URIRef(EX + 'phoneType_T2'), RDF.type, phone_type) in graph

        # Value columns
        cost = URIRef(EX + 'ProcessValue_cost')
        defect_fixed = URIRef(EX + 'ProcessValue_defectFixed')
        assert (cost, RDF.type, BPO.ProcessValue) in graph
        assert (cost, RDF.type, OWL.FunctionalProperty) in graph
        assert (cost, BPO.dataType, XSD.float) in graph
        assert (defect_fixed, BPO.dataType, XSD.boolean) in graph
        assert (URIRef(EX + 'ProcessValue_phoneType'), BPO.dataType, phone_type) in graph

        # Activities write the values that are present on their events
        assert (URIRef(EX + 'Activity_Repair'), BPO.writesValue, cost) in graph
        assert (URIRef(EX + 'Activity_Register'), BPO.writesValue, cost) not in graph
        assert (URIRef(EX + 'Activity_Inform%20User'), BPO.writesValue, defect_fixed) in graph
        assert (URIRef(EX + 'Activity_Register'), BPO.writesValue, URIRef(EX + 'ProcessValue_phoneType')) in graph

        # Columns that are handled differently are not imported as values or entities
        for col in ['case%3Aconcept%3Aname', 'time%3Atimestamp', 'lifecycle%3Atransition']:
            assert (URIRef(EX + f'ProcessValue_{col}'), None, None) not in graph
        assert (None, RDF.type, BPO.Case) not in graph

    def test_ignore_columns(self, csv_path):
        graph = import_entities(read_event_log(csv_path), ignore_columns=['phoneType', 'cost']).addition_graph
        assert (URIRef(EX + 'type_phoneType'), None, None) not in graph
        assert (URIRef(EX + 'ProcessValue_cost'), None, None) not in graph
        assert (URIRef(EX + 'ProcessValue_defectFixed'), None, None) in graph

    def test_attribute_aliases(self, csv_path):
        graph = import_entities(read_event_log(csv_path), attribute_aliases={'phoneType' : BPO.Resource}).addition_graph
        assert (URIRef(EX + 'Resource_T1'), RDF.type, BPO.Resource) in graph

    def test_numeric_entity_column(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity,ward\n1,A,3\n1,B,4\n')
        graph = import_entities(read_event_log(path), entity_columns={'ward'}).addition_graph
        assert (URIRef(EX + 'ward_3'), RDF.type, URIRef(EX + 'type_ward')) in graph
        assert str(graph.value(URIRef(EX + 'ward_3'), RDFS.label)) == '3'

    def test_numeric_activities(self, tmp_path):
        path = write(tmp_path, 'log.csv', 'case,activity\n1,10\n1,20\n')
        graph = import_entities(read_event_log(path)).addition_graph
        assert (URIRef(EX + 'Activity_10'), RDF.type, BPO.Activity) in graph

    def test_load_into_pkg(self, csv_path):
        importer = import_entities(read_event_log(csv_path))
        importer.load()
        assert (URIRef(EX + 'Activity_Repair'), RDF.type, BPO.Activity) in importer.pkg
        assert set(importer.addition_graph) <= set(importer.pkg)

    def test_declare_import(self, csv_path, xes_path):
        templates = ['init', 'response', 'precedence']
        results = []
        for path in [xes_path, csv_path]:
            log = read_event_log(path)
            importer = import_entities(log)
            declare = pm4py.discover_declare(log, allowed_templates=templates, min_support_ratio=1.0, min_confidence_ratio=1.0)
            importer.import_declare(declare)
            results.append(importer.addition_graph)

        xes_graph, csv_graph = results
        init = URIRef('http://infs.cit.tum.de/karibdis/declare/init')
        register = URIRef(EX + 'Activity_Register')
        assert (register, init, register) in csv_graph
        assert set(csv_graph) == set(xes_graph)
