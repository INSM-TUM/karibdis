from abc import ABC, abstractmethod
import ipywidgets
from IPython.display import display, clear_output

import reacton
import reacton.ipywidgets as w

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
            w.Label(value="Start New Import from ...")
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
    with w.Box(layout = ipywidgets.Layout(width='100%', height='98%')): 
        if stage == EXTRACT:
                
            if source == TEXT:
                if importer == None:
                    _importer = TextualImporter(pkg)
                    set_importer(_importer)
                    print('Constructed Importer')
                text, set_text = reacton.use_state('')#'The process value CRP represents the mg of C-reactive protein per liter of blood in a blood test') #TODO
                w.Textarea(value=text, on_value=set_text, rows=10, layout = ipywidgets.Layout(width='98%'))
                def load_statement():
                    set_processing(True)
                    importer.import_content_from_statement(text)
                    set_text('')
                    set_count(len(importer.addition_graph))
                    set_processing(False)
                    set_stage(ALIGN)
                w.Button(description="Confirm", on_click=load_statement)
                # w.Button(description="Continue to alignment", on_click=) TODO allow import of multiple statements
            
            elif source == EVENT_LOG:
                log, set_log = reacton.use_state(None)

                if importer == None:
                    _importer = SimpleEventLogImporter(pkg)
                    set_importer(_importer)
                    print('Constructed Importer')

                elif log is None:
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
                else:
                    
                    dirty, set_dirty = reacton.use_state(False)
                    
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
                    def load_log_entities():
                        set_processing(True)
                        importer.import_event_log_entities(log) # TODO duplicate code except this line
                        set_count(len(importer.addition_graph))
                        set_processing(False)
                        set_stage(ALIGN)

                        
                    if not dirty:
                        with w.VBox():
                            #grid = w.GridspecLayout(n_rows=len(log.columns), n_columns=2)
                            grid = w.Layout(grid_template_columns='1fr 1fr 1fr')
                            with w.GridBox(layout=grid):
                                w.Label(value='Attribute') 
                                w.Label(value='Type') 
                                w.Label(value='Map To') 
                                for i, col in enumerate(log.columns):
                                    key = importer.get_col_key(col)
                                    
                                    w.Label(value=f'{col}') 
                                    
                                    is_entity_column, is_value_column = importer.determine_col_type(key, log[col])
                                    w.Dropdown(
                                        options=['ENTITY', 'VALUE', 'IGNORE'],
                                        value=(is_entity_column and 'ENTITY') or (is_value_column and 'VALUE') or 'IGNORE',
                                        on_value=lambda x, key=key: change_col_type(key, x)
                                    )
                                    
                                    alias = importer.attribute_aliases.get(col, None)
                                    w.Dropdown(
                                        options=list(importer.attribute_aliases.values()) + [None], # TODO 1: Make nice labels by shortening URIs # TODO 2: Allow more options / custom input
                                        value=alias,
                                        on_value=lambda x, key=key: change_col_alias(key, x)
                                    )
                            w.Button(description="Load Entities", on_click=load_log_entities)
                    else:
                        set_dirty(False) # Force Reload
                            
            elif source == EXISTING_ONTOLOGY:
                ontology, set_ontology = reacton.use_state(None)
                def load_from_subgraph(subgraph):
                    set_processing(True)
                    importer.accept_filtered_result(subgraph, ontology)
                    set_count(len(importer.addition_graph))
                    set_processing(False)
                    set_stage(ALIGN)
                    
                if importer is None:
                    _importer = ExistingOntologyImporter(pkg)
                    set_importer(_importer)
                    print('Constructed Importer')
                else:
                    if ontology is not None:
                        ImporterJupyterUI2.query_view(ontology, set_processing, callback_accept=load_from_subgraph)
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
        
    w.Button(description="Cancel", on_click=cancel)


@reacton.component
def AlignmentUI(importer, set_stage, set_processing):
    alignment, set_alignment = reacton.use_state(None)

    def apply_alignment(accepted_alignment):
        importer.apply_alignment(accepted_alignment)
        set_stage(VALIDATE)
    
    if alignment == None or alignment == '':
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