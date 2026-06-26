from itertools import zip_longest
import os
import ipywidgets
from IPython.display import display


import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v


from karibdis.ui.ui_util import QueryBox, TextEditor, format_query
from karibdis.util.async_import import async_import
pm4py = async_import("pm4py")

from karibdis.utils import *
from karibdis.KnowledgeImporter import KnowledgeImporter, TextualImporter, SimpleEventLogImporter, ExistingOntologyImporter, default_attribute_aliases



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
        be_busy_with(importer.load)
        print('Data successfully loaded into the knowledge graph.') # TODO Maybe send nice alert to user
        terminate()
        
    def cancel():
        print('Canceled')
        terminate()
    
    w.Label(value=f"Import from {source}. Currently importing {count} tuples. Importer: {importer}. Stage: {stage}. {'processing...' if is_processing else ''}")

    with w.Box(): # Needs its own box, as otherwise would lead to a whole reload of normal view, which leads to loss of data
        if is_processing:
            w.Label(value="PROCESSING") # TODO nice loading wheel that blocks inputs
    with v.Card(layout = ipywidgets.Layout(width='100%', height='100%')): 
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
                    TextExtractionUI(importer, set_subtitle, be_busy_with, run_extraction)
                
                elif source == EVENT_LOG:
                    EventLogExtractionUI(importer, set_subtitle, be_busy_with, run_extraction)
                                
                elif source == EXISTING_ONTOLOGY:
                    ExistingOntologyExtractionUI(importer, set_subtitle, be_busy_with, run_extraction)

    
        elif stage == ALIGN:
            set_title(f'Align')
            set_subtitle(f'Importing from {source}')
            AlignmentUI(importer, set_stage, be_busy_with)
                
        elif stage == VALIDATE:
            set_title(f'Validate')
            set_subtitle(f'Importing from {source}')
            ValidationView(importer, complete, set_stage)
        
    w.Button(description="Cancel Knowledge Import", on_click=cancel, layout=w.Layout(flex='0 0 auto'))

@reacton.component
def TextExtractionUI(importer, set_subtitle, be_busy_with, run_extraction):
    text, set_text = reacton.use_state('')#'The process value CRP represents the mg of C-reactive protein per liter of blood in a blood test')
    rulesloading, set_rulesloading = reacton.use_state(False)

    def import_rules(): # TODO add busy-ness
        importer.import_rules_from_statement(text)
        set_rulesloading(True)    

    w.Textarea(value=text, on_value=set_text, rows=10, layout = ipywidgets.Layout(width='98%'))
    with w.HBox():
        w.Button(description="Load Entities", on_click=lambda: run_extraction(lambda: importer.import_content_from_statement(text)))
        w.Button(description="Load Rules", on_click=import_rules)
    # w.Button(description="Continue to alignment", on_click=) TODO allow import of multiple statements

        
    if rulesloading:
        output = ipywidgets.Output()
        display(output)

        def run():
            triples = importer.get_query_triples()
            queries = list(map(lambda triple: triple[2].toPython(), triples))

            def update_format(res):
                if not str(res).startswith('ERROR'):
                    importer.update_query_formatting(triples, res)
                run_extraction(lambda: None) # continue to alignment stage
                
            format_query(queries, update_format, output)  
        
        run()

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
            filename = os.path.join(tempfile.gettempdir(), os.urandom(24).hex())
            with open(filename, 'wb') as f:
                f.write(file.content)
                _log = pm4py.read_xes(f.name) # TODO also support csv at some point
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
                grid = w.Layout(grid_template_columns='1fr 1fr 1fr', width='fit-content')
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
                        
                        all_aliases = list(set(importer.attribute_aliases.values()) | set(default_attribute_aliases.values())) # TODO allow dynamic alias sets
                        w.Dropdown(
                            options=list(zip(map(lambda alias: str(alias).replace(BASE_URL, ''), all_aliases), all_aliases)) + [('None', None)], # TODO 1: Make nice labels by shortening URIs # TODO 2: Allow more options / custom input
                            value=alias,
                            on_value=lambda x, col=col: change_col_alias(col, x)
                        )
                w.Button(description="Load Entities", on_click=complete_column_import)
        else:
            set_dirty(False) # Force Reload
    else:
        set_subtitle('Import Control Flow Constraints')
        DiscoveryUI(importer, log, run_extraction)

@reacton.component
def DiscoveryUI(importer, log, run_extraction):
    declare, set_declare = reacton.use_state(None)
    supported_templates = ['init', 'chainresponse', 'exactly_one', 'responded_existence', 'response', 'precedence']
    allowed_templates, set_allowed_templates = reacton.use_state(supported_templates)
    if not declare:
        min_support_ratio, set_min_support_ratio = reacton.use_state(0.8)
        min_confidence_ratio, set_min_confidence_ratio = reacton.use_state(0.8)
        
        def discover():
            # TODO take specified activity column (etc.) from importer
            _declare = pm4py.discover_declare(log, allowed_templates=allowed_templates, min_support_ratio=min_support_ratio, min_confidence_ratio=min_confidence_ratio)
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
            items=supported_templates,
            label='Allowed Templates',
            multiple=True,
            chips=True, 
            v_model=allowed_templates,
            on_v_model=set_allowed_templates,
        )
        
        w.Button(description="Discover", on_click=discover)
    else:
        for relation in allowed_templates:
            x = declare.get(relation, dict())
            v.ToolbarTitle(children=relation)
            for relations, data in x.items():
                with v.ListItem() as main:
                    v.Checkbox(v_model=data, on_v_model=lambda value, relation=relation, relations=relations: (set_declare({**declare, relation : {**declare.get(relation, dict()), relations: value}})))
                    v.Label(children= f'{relations}', disabled=not data)
                #w.Label(value=f'\t{relations} : {data}')
        with w.HBox():
            w.Button(description="Load Constraints", on_click=lambda: run_extraction(lambda: importer.import_declare(declare))) 
            w.Button(description="Adapt Parameters", on_click=lambda: set_declare(None))  

@reacton.component
def ExistingOntologyExtractionUI(importer, set_subtitle, be_busy_with, run_extraction):
    ontology, set_ontology = reacton.use_state(None)
    prompt_url, set_prompt_url = reacton.use_state(False)

    if ontology is not None:
        QueryView(ontology, be_busy_with, callback_accept=lambda subgraph: run_extraction(lambda: importer.accept_filtered_result(subgraph, ontology)))
    elif not prompt_url: 
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

        w.Button(description='Load from URL', on_click=lambda: set_prompt_url(True))
    else:
        url, set_url = reacton.use_state('')
        
        def load_from_url(url):
            graph = Graph()
            for format in [None, 'xml', 'n3']: # Brute force format
                try:
                    graph.parse(url, format=format)
                    break
                except:
                    continue
            set_ontology(graph)

        w.Text(
            value=url,
            placeholder='Ontology URL:',
            on_value=set_url,
            layout=ipywidgets.Layout(width='80%')
        )
        w.Button(description='Load', on_click=lambda : load_from_url(url))

# =========================== SHARED UI ===========================
@reacton.component
def QueryView(graph, be_busy_with, initial_query=None, callback_accept=None):


    with w.VBox(layout = ipywidgets.Layout(width='100%', height='98%')) as main:  


        place_box, current_result, current_result_size, dirty, run_query = QueryBox(graph, initial_query)
        
        # label = w.Label(value = f'{current_result} {dirty}')
        place_box()

        with w.HBox():
            if current_result is not None and not dirty:
                def accept(b=None):
                    callback_accept(current_result) # TODO reduce unnecessary duplicate query running
                    print('Ontology successfully queried.')

                label = w.Label(value = f'You are about to load {current_result_size} tuples. Adapt the query if appropriate.')
                button_accept = w.Button(description='Load Data', on_click=accept)

            else:
                def edit(b=None):
                    button_edit.disabled = True
                    run_query()
                    button_edit.disabled = False
                button_edit = w.Button(description='Test Query', on_click=lambda : be_busy_with(edit))

        # TODO one initial edit

    return main

@reacton.component
def AlignmentUI(importer, set_stage, be_busy_with):
    alignment, set_alignment = reacton.use_state([])

    def apply_alignment(accepted_alignment):
        importer.apply_alignment(accepted_alignment)
        set_stage(VALIDATE)
    with w.VBox() as main:
        AlignmentView(importer, alignment, apply_alignment)
        w.Button(description="Automated Alignment", on_click=lambda: be_busy_with(lambda: set_alignment(importer.determine_alignment())))  
    return main

@reacton.component
def AlignmentView(importer, llm_approved, callback_done):
    g1 = Graph()
    copy_namespaces(g1, importer.addition_graph)
    g2 = Graph()
    copy_namespaces(g2, importer.addition_graph)
    hidden = URIRef('http://example.org/hidden')

    # colors = dict()
    for source_id, target_id in llm_approved:
        g1.add((source_id, OWL.sameAs, target_id))
        g2.add((target_id, URIRef('hidden'), hidden))
        # colors[source_id] = '#99AA00'
        # colors[target_id] = '#1100AA' 
        
    alignment_knowledge_importer = KnowledgeImporter(g2)
    alignment_knowledge_importer.addition_graph = g1

    def confirm_alignment():
        alignment_knowledge_importer.load()
        callback_done(list(filter(lambda triple: hidden not in triple, g2)))

    return ValidationView(alignment_knowledge_importer, confirm_alignment)

@reacton.component
def ValidationView(importer, callback_done, set_stage=None):
    with w.VBox(layout = ipywidgets.Layout(width='100%', height='98%')) as main:
        editing, set_editing = reacton.use_state(False)
        if not editing:
            with w.HBox():
                w.Button(description='Accept', on_click=callback_done)
                w.Button(description='Edit', on_click=lambda: set_editing(True))
                if set_stage is not None:
                    w.Button(description='Go back to Alignment', on_click=lambda: set_stage(ALIGN))
                # w.Button(description='Cancel')
            if len(importer.addition_graph) == 0:
                w.Label(value='No data to visualize.')
            elif len(importer.addition_graph.all_nodes()) > 600:
                w.Label(value=f'Too many nodes ({len(importer.addition_graph.all_nodes())}) to visualize.')
            else:
                graph = visualize_addition_graph(importer)
                display(graph)
        else:
            TextEditor(importer, importer.serialize(format='ttl'), set_editing)
    return main


def visualize_addition_graph(importer): # TODO Partial duplicate to GraphViz
    return draw_graph(importer.addition_graph, color_func=lambda _: dict(zip_longest(importer.addition_graph.all_nodes() - importer.pkg.all_nodes(), [], fillvalue='#99AA00')))