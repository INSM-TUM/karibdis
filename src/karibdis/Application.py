from abc import ABC, abstractmethod
import ipywidgets
from IPython.display import display, clear_output

import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v

import pm4py

from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.utils import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from karibdis.KnowledgeImporter import TextualImporter, SimpleEventLogImporter, ExistingOntologyImporter, ImporterJupyterUI2


class Application(ABC):
    def __init__(self):
        pass

class JupyterApplication(ipywidgets.Box):
    def __init__(self, system=KnowledgeGraphBPMS()):
        super().__init__()
        self.system = system

    def display(self, obj):
        for child in self.children:
            child.close()
        self.children = [obj]
        display(self)
        
    def base_view(self):
        tabs = [
            ('Knowledge Modeling', reacton.render_fixed(KnowledgeModelingUI(self.system.pkg))[0]),
            ('Process Execution', reacton.render_fixed(PrescriptionAndTaskUI())[0]),
        ]
        root = ipywidgets.Tab()
        root.layout = ipywidgets.Layout(width='100%', height='100%')
        root.children = [tab[1] for tab in tabs]
        for tab in root.children:
            tab.layout = ipywidgets.Layout(width='100%', height='100%')
        root.titles = [tab[0] for tab in tabs]
        return root

    def run(self):
        self.display(self.base_view())

            
    class PrescriptionAndTaskUI2(ipywidgets.VBox):
        def __init__(self):
            super().__init__()
            graph = draw_graph(ProcessKnowledgeGraph())
            
            # Extra Hack. See commend in utils.py 
            with ipywidgets.Output():
                display(graph)
                clear_output()
            self.children = [ipywidgets.Label("Prescription and Task UI"), graph]

            
# TODO make proper enums
TEXT = 'Text'
EVENT_LOG = 'Event Log'
EXISTING_ONTOLOGY = 'Existing Ontology'
sources = [TEXT, EVENT_LOG, EXISTING_ONTOLOGY]

EXTRACT = 'extract'
ALIGN = 'align'
VALIDATE = 'validate'
stages = [EXTRACT, ALIGN, VALIDATE]



@reacton.component
def KnowledgeModelingUI(pkg):
    source, set_source = reacton.use_state(None)
    
    with w.VBox() as main:
        if source == None:
            with v.Card(): 
                v.CardTitle(children="Start New Import from ...")
                with v.CardText():
                    for source in sources:
                        w.Button(description=f"{source}", on_click=lambda source=source: set_source(source))
        else:    
            ActiveImportUI(source, set_source, pkg)
    main.layout = ipywidgets.Layout(width='100%')
    return main

@reacton.component
def ActiveImportUI(source, set_source, pkg):
    stage, set_stage = reacton.use_state(EXTRACT)
    importer, set_importer = reacton.use_state(None)
    count, set_count = reacton.use_state(0)
    is_processing, set_processing = reacton.use_state(False)

    def be_busy_with(executable):
        set_processing(True)
        executable()
        set_processing(False)

    def terminate():
        set_count(0)
        set_stage(None)
        set_importer(None)
        set_source(None)
        
    def complete():
        set_processing(True)
        importer.load()
        set_processing(False)
        print('Data successfully loaded into the knowledge graph.') # TODO Maybe send nice alert to user
        terminate()
        
    def cancel():
        print('Canceled')
        terminate()
    
    w.Label(value=f"Import from {source}. Currently importing {count} tuples. Importer: {importer}. Stage: {stage}. {'processing...' if is_processing else ''}")

    with w.Box(): # Needs its own box, as otherwise would lead to a whole reload of normal view, which leads to loss of data
        if is_processing:
            w.Label(value="PROCESSING") # TODO nice loading wheel that blocks inputs
    with v.Card(layout = ipywidgets.Layout(width='100%', height='98%')): 
        title, set_title = reacton.use_state('')
        subtitle, set_subtitle = reacton.use_state('')
        v.CardTitle(children=title)
        v.CardSubtitle(children=subtitle)

        if stage == EXTRACT:
            set_title(f'Extraction from {source}')

            with v.CardText():

                def run_extraction(extraction_routine):
                    be_busy_with(extraction_routine)
                    set_count(len(importer.addition_graph))
                    set_stage(ALIGN)

                if importer is None:
                    if source == TEXT:
                        _importer = TextualImporter(pkg)
                    elif source == EVENT_LOG:
                        _importer = SimpleEventLogImporter(pkg)
                    elif source == EXISTING_ONTOLOGY:
                        _importer = ExistingOntologyImporter(pkg)
                    else:
                        raise ValueError(f'Unknown source {source}')
                    set_importer(_importer)
                    print('Constructed Importer')

                elif source == TEXT:
                    text, set_text = reacton.use_state('')#'The process value CRP represents the mg of C-reactive protein per liter of blood in a blood test') #TODO
                    w.Textarea(value=text, on_value=set_text, rows=10, layout = ipywidgets.Layout(width='98%'))
                    w.Button(description="Confirm", on_click=lambda: run_extraction(lambda: importer.import_content_from_statement(text)))
                    # w.Button(description="Continue to alignment", on_click=) TODO allow import of multiple statements
                
                elif source == EVENT_LOG:
                    EventLogExtractionUI(importer, set_subtitle, be_busy_with, run_extraction)
                                
                elif source == EXISTING_ONTOLOGY:
                    ontology, set_ontology = reacton.use_state(None)

                    if ontology is not None:
                        ImporterJupyterUI2.query_view(ontology, set_processing, callback_accept=lambda subgraph: run_extraction(lambda: importer.accept_filtered_result(subgraph, ontology)))
                    else: 
                        def upload(files):
                            file = files[0]
                            data = str(file.content,'utf-8')
                            graph = Graph().parse(data=data, format='ttl')
                            set_ontology(graph)
                        
                        w.FileUpload(
                            description = 'Upload Ontology File',
                            accept='.ttl',
                            on_accept=lambda **args: print(args),
                            multiple=False,
                            on_value=upload
                        )
    
        elif stage == ALIGN:
            AlignmentUI(importer, set_stage, set_processing)
                
        elif stage == VALIDATE:
            ImporterJupyterUI2.validation_view(importer, complete)
        
    w.Button(description="Cancel Knowledge Import", on_click=cancel)

@reacton.component
def EventLogExtractionUI(importer, set_subtitle, be_busy_with, run_extraction):
    log, set_log = reacton.use_state(None)
    done_with_columns, set_done_with_columns = reacton.use_state(False)
    if log is None:
        set_subtitle('Upload Event Log to be Extracted From')
        def upload(files): # TODO code duplicate to ontology importer
            file = files[0]
            _log = None
            import tempfile 
            with tempfile.NamedTemporaryFile() as f:
                f.write(file.content)
                _log = pm4py.read_xes(f.name) # also support csv at some point
            set_log(_log)
        
        w.FileUpload(
            description = 'Upload Event Log File',
            accept='.xes',
            on_accept=lambda **args: print(args),
            multiple=False,
            on_value=upload
        )
    elif not done_with_columns:
        set_subtitle('Determine Column Imports')
        dirty, set_dirty = reacton.use_state(False)

        def complete_column_import():
            be_busy_with(lambda: importer.import_event_log_entities(log))
            set_done_with_columns(True)
        
        def change_col_type(column, value):
            if value == 'ENTITY':
                importer.entity_columns.add(column)
            else:
                importer.entity_columns.discard(column)
                
            if value == 'VALUE':
                importer.value_columns.add(column)
            else:
                importer.value_columns.discard(column)
                
            if value == 'IGNORE':
                importer.ignore_columns.add(column)
            else:
                importer.ignore_columns.discard(column)
            set_dirty(True)

        def change_col_alias(col_key, value):
            importer.change_col_alias(col_key, value)
            set_dirty(True)
            
        if not dirty:
            with w.VBox():
                #grid = w.GridspecLayout(n_rows=len(log.columns), n_columns=2)
                grid = w.Layout(grid_template_columns='1fr 1fr 1fr')
                with w.GridBox(layout=grid):
                    w.Label(value='Attribute') 
                    w.Label(value='Column Type') 
                    w.Label(value='Map To (Optional)') 
                    for i, col in enumerate(log.columns):
                        key = importer.get_col_key(col)
                        alias = importer.attribute_aliases.get(col, None)
                        
                        w.Label(value=f'{col}') 
                        
                        is_entity_column, is_value_column = importer.determine_col_type(key, log[col])
                        w.Dropdown(
                            options=['ENTITY', 'VALUE', 'IGNORE'],
                            value=(is_entity_column and 'ENTITY') or (is_value_column and 'VALUE') or 'IGNORE',
                            on_value=lambda x, key=key: change_col_type(key, x),
                            disabled=alias is not None
                        )
                        
                        all_aliases = list(importer.attribute_aliases.values())
                        w.Dropdown(
                            options=list(zip(map(lambda alias: str(alias).replace(BASE_URL, ''), all_aliases), all_aliases)) + [('None', None)], # TODO 1: Make nice labels by shortening URIs # TODO 2: Allow more options / custom input
                            value=alias,
                            on_value=lambda x, key=key: change_col_alias(key, x)
                        )
                w.Button(description="Load Entities", on_click=complete_column_import)
        else:
            set_dirty(False) # Force Reload
    else:
        set_subtitle('Import Control Flow Constraints')
        DiscoveryUI(importer, log, run_extraction)

from pm4py import discover_declare
@reacton.component
def DiscoveryUI(importer, log, run_extraction):
    declare, set_declare = reacton.use_state(None)
    allowed_templates, set_allowed_templates = reacton.use_state(['init', 'chainresponse'])# TODO, 'exactly_one'])
    if not declare:
        min_support_ratio, set_min_support_ratio = reacton.use_state(0.8)
        min_confidence_ratio, set_min_confidence_ratio = reacton.use_state(0.8)
        
        def discover():
            # TODO take specified activity column (etc.) from importer
            _declare = discover_declare(log, allowed_templates=allowed_templates, min_support_ratio=min_support_ratio, min_confidence_ratio=min_confidence_ratio)
            set_declare(_declare)

        v.Slider(
            label=f'Minimum Support Ratio ({min_support_ratio:.2f})',
            min=0,
            max=1,
            step=0.05,
            thumb_label=True,
            v_model = min_support_ratio,
            on_v_model=set_min_support_ratio,
        )

        v.Slider(
            label=f'Minimum Confidence Ratio ({min_confidence_ratio:.2f})',
            min=0,
            max=1,
            step=0.05,
            thumb_label=True,
            v_model = min_confidence_ratio,
            on_v_model=set_min_confidence_ratio,
        )

        v.Select(
            prepend_icon='mdi-cogs',
            items=allowed_templates,
            label='Allowed Templates',
            multiple=True,
            chips=True, 
            v_model=allowed_templates,
            on_v_model=set_allowed_templates,
        )
        
        w.Button(description="Discover", on_click=discover)
    else:
        for relation in allowed_templates:
            x = declare[relation]
            v.ToolbarTitle(children=relation)
            for relations, data in x.items():
                with v.ListItem() as main:
                    # TODO v.Checkbox(v_model=declare, on_v_model=lambda)
                    v.Label(children= f'{relations}')
                #w.Label(value=f'\t{relations} : {data}')
        
        w.Button(description="Load Constraints", on_click=lambda: run_extraction(lambda: importer.import_declare(declare)))  

@reacton.component
def AlignmentUI(importer, set_stage, set_processing):
    alignment, set_alignment = reacton.use_state(None)

    def apply_alignment(accepted_alignment):
        importer.apply_alignment(accepted_alignment)
        set_stage(VALIDATE)
    
    if alignment is None or alignment == '':
        # TODO allow user to customize filters
        set_processing(True)
        set_alignment(importer.determine_alignment())
        set_processing(False)
    else:
        ImporterJupyterUI2.alignment_view(importer, alignment, apply_alignment)


@reacton.component
def PrescriptionAndTaskUI():
    with w.VBox() as main:
        w.Label(value="Prescription and Task UI")
        graph = draw_graph(ProcessKnowledgeGraph())
    
        # Extra Hack. See commend in utils.py 
        with ipywidgets.Output():
            display(graph)
            clear_output()
    return main