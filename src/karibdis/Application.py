from abc import ABC, abstractmethod
from itertools import zip_longest
import os
import ipywidgets
from IPython.display import display, clear_output, Javascript

import uuid

from pyparsing import ParseException
import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v
from ipywidgets.widgets.widget_string import LabelStyle


from karibdis.util.async_import import async_import
pm4py = async_import("pm4py")
import json

from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.utils import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from karibdis.KnowledgeImporter import KnowledgeImporter, TextualImporter, SimpleEventLogImporter, ExistingOntologyImporter
import datetime
from rdflib import Literal, RDFS, XSD
from rdflib.paths import ZeroOrMore
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO


class Application(ABC):
    def __init__(self):
        pass

class JupyterApplication(ipywidgets.Box):
    def __init__(self, system=KnowledgeGraphBPMS()):
        super().__init__()
        self.system = system
        self.layout = ipywidgets.Layout(width='100%', height='99vh')

    def display(self, obj):
        for child in self.children:
            child.close()
        self.children = [obj]
        display(self)
        
    def base_view(self):
        tabs = [
            ('Knowledge Modeling', reacton.render_fixed(KnowledgeModelingUI(self.system.pkg))[0]),            
            ('Decisionmaking', reacton.render_fixed(DecisionUI(self.system.engine))[0]),
            ('Task Execution', reacton.render_fixed(TaskExecutionUI(self.system.engine))[0]),
            ('Explore Graph', reacton.render_fixed(GraphExplorationUI(self.system.pkg))[0]),
        ]
        root = ipywidgets.Tab()
        root.layout = ipywidgets.Layout(width='100%', height='100%')
        root.children = [tab[1] for tab in tabs]
        for tab in root.children:
            tab.layout = ipywidgets.Layout(width='100%')
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
                #_log = pm4py.read_xes(f.name) # TODO also support csv at some point
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

@reacton.component
def DiscoveryUI(importer, log, run_extraction):
    declare, set_declare = reacton.use_state(None)
    allowed_templates, set_allowed_templates = reacton.use_state(['init', 'chainresponse', 'exactly_one'])
    if not declare:
        min_support_ratio, set_min_support_ratio = reacton.use_state(0.8)
        min_confidence_ratio, set_min_confidence_ratio = reacton.use_state(0.8)
        
        def discover():
            # TODO take specified activity column (etc.) from importer
            #_declare = pm4py.discover_declare(log, allowed_templates=allowed_templates, min_support_ratio=min_support_ratio, min_confidence_ratio=min_confidence_ratio)
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
def DecisionUI(engine):
    decisions, set_decisions = reacton.use_state(list(engine.open_decisions()))
    def reload():
        set_decisions(list(engine.open_decisions()))

    def decision_label(decision):
        return engine.pkg.label(decision.subject)

    def make_decision_view(decision):
        return DecisionBody(engine, decision, reload)
    
    with w.VBox() as main:
        with w.HBox():
            w.Button(description="Open new case", on_click=lambda: (engine.open_new_case(), reload()))
        SelectionMenu(
            "Decisionmaking", 
            decisions, 
            set_decisions, 
            reload, 
            decision_label ,  
            make_decision_view, 
            item_equality=lambda decision_a, decision_b : (decision_a.subject == decision_b.subject) and (decision_a.predicate == decision_b.predicate),
            collection_name='Decisions'
        )
    return main



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


@reacton.component
def DecisionBody(engine, current_decision, reload):
    context_case = current_decision.context.get('case', None)
    context_type = current_decision.context.get('target_type', None)
    label_context = current_decision.context.get('label_context', None)
    with w.VBox(layout=w.Layout(overflow='scroll', height='60vh', width='100%')) as main:
        options, set_options = reacton.use_state([])
        reacton.use_effect(lambda: set_options(current_decision.get_top_k_results(20)), [current_decision])
        v.CardTitle(children=f' Decide {engine.pkg.label(context_type)}' + (f' for {engine.pkg.label(context_case)}' if context_case else '') + (f' {label_context}' if label_context else ''), layout=w.Layout(flex='0 0 auto'))

        for score, option, reasoning in options:
            with w.VBox(layout=w.Layout(border='solid #FAFAFA', margin='0.2%', padding='0.1%', flex='0 0 auto')):  
                v.Label(children=f'{engine.pkg.label(option)} ({score})', style=LabelStyle(font_weight='bold', width='100%'))
                for reason in reasoning:
                    w.Label(value=f'- {reason}') # TODO: Add single scores?
                w.Button(description='Confirm', on_click=lambda option=option: [engine.handle_decision(current_decision, option), reload()])
        if context_case is not None:
            w.Button(description='Close Case', on_click=lambda: [engine.close_case(context_case), reload()], layout=w.Layout(flex='0 0 auto'))
        


@reacton.component
def GraphViz(graph):
    with w.VBox() as main:
        graph_viz = draw_graph(graph)
        display(graph_viz)
    return main

@reacton.component
def GraphExplorationUI(graph): # TODO don't populate until shown
    reload, set_reload = reacton.use_state(True)
    place_box, current_result, current_result_size, dirty, run_query = QueryBox(graph)
    current_graph, set_current_graph = reacton.use_state(graph)

    def update_subgraph():
        _current_graph = Graph()
        copy_namespaces(_current_graph, graph)
        _current_graph += current_result
        set_current_graph(_current_graph)
    reacton.use_effect(update_subgraph, [current_result])
    
    with w.VBox() as main:
        v.CardTitle(children='Graph Exploration')
        
        if len(current_graph.all_nodes()) < 600:
            GraphViz(current_graph)
        else:
            w.Label(value=f'Too many nodes ({len(current_graph.all_nodes())}) to visualize.')

        if not reload:
            place_box()
        else:
            w.Label(value="Reloading...")
            run_query()
            set_reload(False)
        w.Button(description="Reload Graph", on_click=lambda: set_reload(True))
    return main


@reacton.component
def TaskExecutionUI(engine): 
    tasks, set_tasks = reacton.use_state(list(engine.open_tasks()))
    def reload():
        set_tasks(list(engine.open_tasks()))

    def task_label(task):
        return engine.pkg.label(task[0])

    def make_task_view(task):
        return TaskBody(engine, task, reload)
    
    with w.VBox() as main:
        with w.HBox():
            w.Button(description="Open new case", on_click=lambda: (engine.open_new_case(), reload()))
        SelectionMenu(
            "Task Execution", 
            tasks, 
            set_tasks, 
            reload, 
            task_label ,  
            make_task_view,
            collection_name='Tasks'
        )
    return main


@reacton.component
def TaskBody(engine, current_task_case, reload):
    pkg = engine.pkg

    current_task, current_case = current_task_case

    attribute_instances, set_attribute_instances = reacton.use_state({})
    reacton.use_effect(lambda: set_attribute_instances({}), [current_task_case])

    activity = next(pkg.objects(predicate = BPO.instanceOf, subject = current_task), None)
    attributes_to_show, set_attributes_to_show = reacton.use_state([])
    reacton.use_effect(lambda: set_attributes_to_show(list(pkg.objects(subject=activity, predicate=BPO.writesValue))), [current_task_case])

    def add_all_pv_to_task(pv):
        # Make a defensive copy to prevent issues with state updates
        current_attributes = list(attributes_to_show)
        
        is_functional = (pv, RDF.type, OWL.FunctionalProperty) in pkg
        
        if is_functional:
            if pv in current_attributes:
                return
        
        # For non-functional properties, always allow addition
        # Duplicate entity values are prevented in the UI dropdown filtering
        
        # Check if this PV is already in the form
        current_instances = current_attributes.count(pv)
        
        if current_instances == 0:
            # PV not currently in form - use existing logic to show proper number of instances
            current_case_values = list(pkg.objects(subject=current_case, predicate=pv))
            required_instances = len(current_case_values) + 1  # existing + 1 new
            instances_to_add = required_instances
        else:
            # PV already in form - just add one more instance
            instances_to_add = 1
        
        for _ in range(instances_to_add):
            current_attributes.append(pv)
        
        set_attributes_to_show(current_attributes)
            
                
    def on_submit_click():
        # Collect ProcessValue instances
        pv_instances = {}
        for i, attr in enumerate(attributes_to_show):
            if attr not in pv_instances:
                pv_instances[attr] = []
            pv_instances[attr].append(i)
        
        for attr, instance_indices in pv_instances.items():
            attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr), None)
            is_functional = (attr, RDF.type, OWL.FunctionalProperty) in pkg
            is_entity = attr_type is not None and attr_type not in XSD
            
            if is_functional:
                # Functional property: use pkg.set() for single value
                instance_id = f"{attr}_{instance_indices[0]}"
                val = attribute_instances.get(instance_id)
                if val is None:
                    val = load_existing_value_for(attr)
                if val is None:
                    val = compute_default_for(attr)
                    
                if val is not None:
                    if is_entity:
                        pkg.set((current_case, attr, val))
                    else:
                        lit = Literal(val, datatype=attr_type if attr_type is not None else None)
                        pkg.set((current_case, attr, lit))
            else:
                # Non-functional property: use pkg.add() for multiple values
                if attr in multi_select_mode and is_entity:
                    # Multi-select logic for entities clears existing values and sets only the selected ones
                    existing_values = list(pkg.objects(subject=current_case, predicate=attr))
                    for existing_val in existing_values:
                        pkg.remove((current_case, attr, existing_val))
                    
                    
                    current_selected_values = set()
                    for idx in instance_indices:
                        instance_id = f"{attr}_{idx}"
                        val = attribute_instances.get(instance_id)
                        if val is not None:
                            current_selected_values.add(val)
                            
                    for val in current_selected_values:
                        pkg.add((current_case, attr, val))
                else:
                    for idx in instance_indices:
                        instance_id = f"{attr}_{idx}"
                        val = attribute_instances.get(instance_id)
                        if val is None:
                            if attr not in multi_select_mode:
                                val = compute_default_for(attr)
                            else:
                                continue
                        if val is not None:
                            if is_entity:
                                pkg.add((current_case, attr, val))
                            else:
                                lit = Literal(val, datatype=attr_type if attr_type is not None else None)
                                pkg.add((current_case, attr, lit))
                    
        engine.complete_task(current_task)
        reload()
    
    def load_existing_value_for(attr):
        existing = pkg.value(subject=current_case, predicate=attr)
        if existing is not None:
            return existing.toPython() if isinstance(existing, Literal) else existing
        else:
            return compute_default_for(attr)
            
    def load_existing_values_for(attr):
        existing_values = list(pkg.objects(subject=current_case, predicate=attr))
        return [val.toPython() if isinstance(val, Literal) else val for val in existing_values]
        
    def options_for_entity_pv_type(pv_type):
        return pkg.subjects(predicate=RDF.type / (RDFS.subClassOf*ZeroOrMore), object=pv_type)
        
    def compute_default_for(attr):
        attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr))
        if attr_type not in XSD:
            option_0 = next(options_for_entity_pv_type(attr_type), None)
            return option_0 if option_0 else None
        if attr_type == XSD.integer:
            return 0
        if attr_type == XSD.float:
            return 0.0
        if attr_type == XSD.boolean:
            return False
        return ""
    
    layout= w.Layout(description_width="initial")
    
    # Group form attributes (rows) by process value for display logic
    grouped_attributes = {}
    for i, attr in enumerate(attributes_to_show):
        if attr not in grouped_attributes:
            grouped_attributes[attr] = []
        grouped_attributes[attr].append(i)
    
    # Track attributes in multi-select mode
    multi_select_mode, set_multi_select_mode = reacton.use_state(set())
    
    # Track initially loaded case values to prevent auto-reselection
    case_values_loaded, set_case_values_loaded = reacton.use_state(set())
    
    # Track original case values to delete deselected values in multi-select mode
    original_case_values, set_original_case_values = reacton.use_state({})
    
    # Update multi-select mode when non-functional entities have multiple instances
    def update_multi_select_mode():
        new_multi_select = set(multi_select_mode)
        for attr, indices in grouped_attributes.items():
            is_functional = (attr, RDF.type, OWL.FunctionalProperty) in pkg
            attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr), None)
            
            if (not is_functional and 
                attr_type not in XSD and 
                len(indices) > 1):
                new_multi_select.add(attr)
        
        set_multi_select_mode(new_multi_select)
    
    reacton.use_effect(update_multi_select_mode, [attributes_to_show])
    
    # Initialize case values for multi-select attributes on first load
    def initialize_case_values():
        new_loaded = set(case_values_loaded)
        updated_instances = dict(attribute_instances)
        updated_originals = dict(original_case_values)
        
        for attr, indices in grouped_attributes.items():
            if attr in multi_select_mode and attr not in case_values_loaded:
                # Load case values for this attribute
                case_values = load_existing_values_for(attr)
                if case_values:
                    
                    updated_originals[attr] = set(case_values)
                    # Create a new list without current attribute instances
                    new_attributes = []
                    for a in attributes_to_show:
                        if a != attr:
                            new_attributes.append(a)
                    
                    # Find the original position of the attribute 
                    attr_position = None
                    for i, a in enumerate(attributes_to_show):
                        if a == attr:
                            attr_position = i
                            break
                    
                    # Insert each instance while incrementing starting with the original position
                    if attr_position is not None:
                        for i, case_val in enumerate(case_values):
                            new_attributes.insert(attr_position + i, attr)
                            instance_id = f"{attr}_{attr_position + i}"
                            updated_instances[instance_id] = case_val
                    
                    if len(case_values) != len(indices):
                        set_attributes_to_show(new_attributes)
                else:
                    # No existing case values, but still mark as loaded
                    updated_originals[attr] = set()
                
                new_loaded.add(attr)
        
        if new_loaded != case_values_loaded:
            set_case_values_loaded(new_loaded)
        if updated_instances != attribute_instances:
            set_attribute_instances(updated_instances)
        if updated_originals != original_case_values:
            set_original_case_values(updated_originals)
    
    reacton.use_effect(initialize_case_values, [multi_select_mode])
    
    def on_delete_attribute(attr):
        def handler(*_):
            # Remove all instances of this attribute
            new_attributes = [a for a in attributes_to_show if a != attr]
            set_attributes_to_show(new_attributes)
            
            # Clear from multi-select mode tracking
            new_multi_select = set(multi_select_mode)
            new_multi_select.discard(attr)
            set_multi_select_mode(new_multi_select)
            
            # Clear from case values loaded tracking
            new_loaded = set(case_values_loaded)
            new_loaded.discard(attr)
            set_case_values_loaded(new_loaded)
            
            # Clear from original case values tracking
            new_originals = dict(original_case_values)
            new_originals.pop(attr, None)
            set_original_case_values(new_originals)
        return handler
    
    def on_delete_instance(attr, idx):
        def handler(*_):
            # Rebuild attributes list and remap all instance keys to their new positions.
            # Because instance keys use absolute positions (f"{a}_{pos}"), removing one
            # entry shifts every subsequent position down by 1 - so we must rename them.
            new_attributes = []
            new_instances = {}
            for old_pos, a in enumerate(attributes_to_show):
                if old_pos == idx:
                    continue  # skip deleted instance
                new_pos = len(new_attributes)
                old_key = f"{a}_{old_pos}"
                new_key = f"{a}_{new_pos}"
                if old_key in attribute_instances:
                    new_instances[new_key] = attribute_instances[old_key]
                new_attributes.append(a)

            # If no instances of attr remain, also clean tracking state
            remaining = [a for a in new_attributes if a == attr]
            if not remaining:
                new_multi_select = set(multi_select_mode)
                new_multi_select.discard(attr)
                set_multi_select_mode(new_multi_select)
                new_loaded = set(case_values_loaded)
                new_loaded.discard(attr)
                set_case_values_loaded(new_loaded)
                new_originals = dict(original_case_values)
                new_originals.pop(attr, None)
                set_original_case_values(new_originals)
            
            set_attribute_instances(new_instances)
            set_attributes_to_show(new_attributes)
        return handler

    def on_widget_change(attr, instance_num):
        def handler(new_value):
            instance_id = f"{attr}_{instance_num}"
            set_attribute_instances(lambda prev: {**(prev or {}), instance_id: new_value})
        return handler
    
    def create_checkbox_handler(attr, option):
        def handler(checked):
            current_selected = set()
            attr_instances = []
            
            # Find all current instances of this attribute and their positions
            for i, a in enumerate(attributes_to_show):
                if a == attr:
                    attr_instances.append(i)
                    instance_id = f"{attr}_{i}"
                    val = attribute_instances.get(instance_id)
                    if val:
                        current_selected.add(val)
            
            # Update the set based on checkbox state
            if checked:
                current_selected.add(option)
            else:
                current_selected.discard(option)
            
            # Create new dict without instances of this attribute
            updated_instances = {k: v for k, v in attribute_instances.items() 
                               if not any(k == f"{attr}_{idx}" for idx in attr_instances)}
            
            # Preserve order: rebuild attributes_to_show maintaining positions and assign values
            new_attributes = []
            selected_values = list(current_selected)
            num_instances = max(1, len(selected_values))  # Always keep at least 1 instance for the UI
            
            # Combined loop: rebuild the list and assign values simultaneously
            attr_added = False
            attr_value_index = 0
            for i, a in enumerate(attributes_to_show):
                if a == attr:
                    # Add all attribute instances to new dict starting at the first occurrence position
                    if not attr_added:
                        for _ in range(num_instances):
                            new_attributes.append(attr)
                            # Assign value to this instance position
                            instance_id = f"{attr}_{len(new_attributes) - 1}"
                            if attr_value_index < len(selected_values):
                                updated_instances[instance_id] = selected_values[attr_value_index]
                            attr_value_index += 1
                        attr_added = True
                    # Skip other instances in the original list
                else:
                    new_attributes.append(a)
            
            set_attributes_to_show(new_attributes)
            
            set_attribute_instances(updated_instances)
        return handler
    
    with w.VBox() as main:  
        v.CardTitle(children=f'{pkg.label(activity)} for {engine.pkg.label(current_case)}')
        
        # Header row with better styling
        with w.HBox(layout=w.Layout(padding='10px', background_color='#f5f5f5', border_bottom='2px solid #ddd')):
            w.Label(value='Attribute', layout=w.Layout(width='200px', font_weight='bold'))
            w.Label(value='Value', layout=w.Layout(width='400px', font_weight='bold'))
            w.Label(value='Type', layout=w.Layout(width='150px', font_weight='bold'))
            w.Label(value='Actions', layout=w.Layout(width='80px', font_weight='bold'))
        
        # Container for all attribute rows
        with w.VBox(layout=w.Layout(border='1px solid #e0e0e0')) as rows_container:
            # Render each unique attribute as a single row
            for attr, instance_indices in grouped_attributes.items():
                is_functional = (attr, RDF.type, OWL.FunctionalProperty) in pkg
                attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr), None)
                attr_name = pkg.label(attr)
                
                with w.HBox(layout=w.Layout(padding='10px', border_bottom='1px solid #eee')):
                    # Attribute name column
                    with w.VBox(layout=w.Layout(width='200px')):
                        w.Label(value=attr_name)
                        if not is_functional:
                            w.Button(description='+', layout=w.Layout(width='30px', height='30px'),
                                     button_style='info', on_click=lambda *_, attr=attr: add_all_pv_to_task(attr))
                    
                    # Value column - different rendering based on type and instance count
                    with w.VBox(layout=w.Layout(width='400px')) as value_container:
                        
                        if attr_type not in XSD:  # Entity type
                            options = list(options_for_entity_pv_type(attr_type))
                            
                            should_show_multiselect = (not is_functional and 
                                                     (attr in multi_select_mode or len(instance_indices) > 1))
                            
                            if not should_show_multiselect:
                                # Single dropdown for functional or single instance (not yet in multi-select mode)
                                instance_id = f"{attr}_{instance_indices[0]}"
                                default_value = attribute_instances.get(instance_id, load_existing_value_for(attr))
                                
                                labels = [str(pkg.label(option)) for option in options]
                                dropdown_options = list(zip(labels, options))
                                w.Dropdown(value=default_value, options=dropdown_options, 
                                          layout=layout, on_value=on_widget_change(attr, instance_indices[0]))
                            else:
                                # Multi-select checkboxes for multiple non-functional instances
                                existing_values = set()
                                
                                # Load from current attribute instances
                                for idx in instance_indices:
                                    instance_id = f"{attr}_{idx}"
                                    val = attribute_instances.get(instance_id)
                                    if val:
                                        existing_values.add(val)
                                
                                # Only load case values if not already loaded (prevents auto-reselection)
                                if attr not in case_values_loaded:
                                    case_values = load_existing_values_for(attr)
                                    for case_val in case_values:
                                        existing_values.add(case_val)
                                
                                # Create checkboxes for each option
                                for option in options:
                                    is_selected = option in existing_values
                                    checkbox = w.Checkbox(
                                        description=str(pkg.label(option)), 
                                        value=is_selected,
                                        on_value=create_checkbox_handler(attr, option)
                                    )
                                    w.Box(children=[checkbox], layout=w.Layout(margin='2px 0'))
                        
                        else:  # Non-entity types
                            for idx in instance_indices:
                                instance_id = f"{attr}_{idx}"
                                instance_pos = instance_indices.index(idx) + 1
                                
                                # Load existing or default value
                                if is_functional:
                                    default_value = attribute_instances.get(instance_id, load_existing_value_for(attr))
                                else:
                                    existing_values = load_existing_values_for(attr)
                                    if instance_pos <= len(existing_values):
                                        default_value = attribute_instances.get(instance_id, existing_values[instance_pos - 1])
                                    else:
                                        default_value = attribute_instances.get(instance_id, compute_default_for(attr))
                                
                                widget_layout = w.Layout(margin='2px 0', width='350px')
                                placeholder = f"Value {instance_pos}" if len(instance_indices) > 1 else ""
                                
                                if attr_type == XSD.string:
                                    widget = w.Text(value=default_value, placeholder=placeholder,
                                                   layout=widget_layout, on_value=on_widget_change(attr, idx))
                                elif attr_type == XSD.integer:
                                    widget = w.IntText(value=default_value, description=placeholder,
                                                     layout=widget_layout, on_value=on_widget_change(attr, idx))
                                elif attr_type == XSD.float:
                                    widget = w.FloatText(value=default_value, description=placeholder,
                                                       layout=widget_layout, on_value=on_widget_change(attr, idx))
                                elif attr_type == XSD.boolean:
                                    widget = w.Checkbox(value=default_value, description=placeholder,
                                                      on_value=on_widget_change(attr, idx))
                                else:
                                    widget = w.Text(value=default_value, placeholder=placeholder,
                                                   layout=widget_layout, on_value=on_widget_change(attr, idx))
                                
                                w.Box(children=[widget], layout=w.Layout(margin='2px 0'))
                    
                    # Type label column
                    if attr_type not in XSD:
                        type_label = pkg.label(attr_type)
                    elif attr_type == XSD.string:
                        type_label = 'string'
                    elif attr_type == XSD.integer:
                        type_label = 'integer'
                    elif attr_type == XSD.float:
                        type_label = 'float'
                    elif attr_type == XSD.boolean:
                        type_label = 'boolean'
                    else:
                        type_label = 'string'
                    
                    w.Label(value=type_label, layout=w.Layout(width='150px'))
                    
                    # Delete button column
                    with w.VBox(layout=w.Layout(width='80px')):
                        if is_functional or attr_type not in XSD:
                            # Single delete-all button for functional/entity attrs
                            w.Button(
                                description='×',
                                layout=w.Layout(width='36px', height='30px'),
                                button_style='danger',
                                on_click=on_delete_attribute(attr)
                            )
                        else:
                            # Per-instance delete buttons aligned with each value row
                            for idx in instance_indices:
                                w.Button(
                                    description='×',
                                    layout=w.Layout(width='36px', height='30px'),
                                    button_style='danger',
                                    on_click=on_delete_instance(attr, idx)
                                )
                
            
        AddProcessValueUI(pkg, attributes_to_show, add_all_pv_to_task) # TODO compute default should need to be a parameter?
        w.Button(description="Submit", on_click=on_submit_click, layout=w.Layout(flex='0 0 auto'))
                
    return main

@reacton.component
def AddProcessValueUI(pkg, attributes, add_all_pv_to_task):
    
    open, set_open = reacton.use_state(False)
    remaining_options, set_remaining_options = reacton.use_state([])
    selected_pv, set_selected_pv = reacton.use_state(None)
    
    # Update remaining options when attributes change
    def update_remaining_options():
        all_pvs = list(pkg.subjects(predicate=RDF.type, object=BPO.ProcessValue))
        new_options = []
        
        for pv in all_pvs:
            # Only show PVs not already present in the form
            if pv not in attributes:
                new_options.append((pkg.label(pv), pv))
        
        set_remaining_options(new_options)
        
        # Reset selected_pv when options change
        if new_options:
            first_pv = new_options[0][1]
            set_selected_pv(first_pv)
        else:
            set_selected_pv(None)
    
    # Update options when attributes change
    reacton.use_effect(update_remaining_options, [attributes])
    
    # Update selected PV
    def on_pv_change(new_pv):
        set_selected_pv(new_pv)

    with w.VBox() as main:
        if len(remaining_options) == 0:
            w.Label(value="No other ProcessValues available to add.")
        elif not open:
            w.Button(description="Add new ProcessValue", on_click=lambda *_: set_open(True))
        else:
            # Show form only if there are options and selected_pv is set
            if remaining_options and selected_pv is not None:
                w.Label(value="Add a new ProcessValue to this case")
                w.Dropdown(options=remaining_options, value=selected_pv, on_value=on_pv_change)

                def _add_to_pkg(b=None):
                    pv_to_add = selected_pv
                    set_open(False)              
                    try:
                        add_all_pv_to_task(pv_to_add)
                    except Exception as e:
                        print(f"Error adding ProcessValue: {e}")
                        # Reopen dialog on error
                        set_open(True)
                    
                with w.HBox():
                    w.Button(description="Create", on_click=_add_to_pkg)
                    w.Button(description="Cancel", on_click=lambda *_: set_open(False))
            else:
                w.Label(value="Loading ProcessValues...")
    return main

# =========================== UTILS ===========================

@reacton.component
def SelectionMenu(title, items, set_items, reload, item_label, make_item_view, item_equality = lambda a,b : a is b, collection_name='items'):
    with w.VBox() as main:
        
        with v.Card(): 
            v.CardTitle(children=title)
            with v.CardText():
                current_item, set_current_item = reacton.use_state(next(iter(items), None))
                reacton.use_effect(lambda: set_current_item(next(iter(items), None)), [items])
                if len(items) > 0 and current_item is not None:
                    with w.HBox():
                        with w.VBox():
                            for item in items:
                                w.Button(
                                    description=item_label(item), 
                                    on_click=lambda item=item: set_current_item(item),
                                    style=w.ButtonStyle(button_color='#DDEEFF' if item_equality(item, current_item) else None)
                                )
                        make_item_view(current_item)
                else:
                    w.Label(value=f'No {collection_name} to select')
                    
        w.Button(description=f'Reload {collection_name}', on_click=reload, layout=w.Layout(flex='0 0 auto'))
    return main


@reacton.component
def TextEditor(importer, init_value, set_editing):
    with w.VBox(layout = ipywidgets.Layout(width='100%', height='98%')) as main:
        text_value, set_text_value = reacton.use_state(init_value)
        text = w.Textarea(
            layout = ipywidgets.Layout(width='98%'),
            value = text_value,
            rows = len(text_value.split('\n')),
            on_value=set_text_value
        )
        def accept_edit(b=None):
            if text_value != init_value:
                importer.reload_from_text(text_value)
            else:
                print('No changes')
            set_editing(False)

        button_accept = w.Button(description='Accept Edit', on_click=accept_edit, layout=w.Layout(flex='0 0 auto'))
        button_cancel = w.Button(description='Cancel Edit', on_click=lambda: set_editing(False), layout=w.Layout(flex='0 0 auto'))
    return main


def QueryBox(graph, initial_query=None):
    # TODO consider adding namespaces per default
    default_initial_query = ''' 
SELECT ?subject ?predicate ?object
WHERE {
    ?subject ?predicate ?object . 
    FILTER("true") .
} 
'''  
    current_result, set_current_result = reacton.use_state(None)
    error_msg, set_error_msg = reacton.use_state('')
    current_result_size, set_current_result_size = reacton.use_state(0)
    dirty, set_dirty = reacton.use_state(True)
    query, _set_query = reacton.use_state(initial_query if initial_query else default_initial_query) 
    def set_query(value):
        set_dirty(True)
        _set_query(value)  

    def place_box():
        with w.VBox():
            if error_msg:
                w.Label(value=f'Error: {error_msg}', style=LabelStyle(text_color='red')) 
            w.Textarea(
                layout = w.Layout(width='98%'),
                value = query,
                on_value=set_query,
                rows = len(query.split('\n')) + 2
            )

    def run_query():
        try:
            query_result = graph.query(query)
            set_current_result_size(len(query_result))
            set_dirty(False)
            set_current_result(query_result)
            set_error_msg('')
        except ParseException as e:
            set_error_msg('Invalid Query')
            print(e)
        # print(query_result)

    return place_box, current_result, current_result_size, dirty, run_query



# Attention: Veeeeery hacky
def format_query(queries, callback, output=None):
#    try:
#        async with async_timeout.timeout(2):
            
            bridge = ipywidgets.Textarea()
            classname = 'x' + str(uuid.uuid4()).replace('-', '')
            bridge.add_class(classname)
            
            js = Javascript("""
            // https://stackoverflow.com/a/61511955
            function waitForElm(selector) {
                return new Promise(resolve => {
                    if (document.querySelector(selector)) {
                        return resolve(document.querySelector(selector));
                    }
            
                    const observer = new MutationObserver(mutations => {
                        if (document.querySelector(selector)) {
                            observer.disconnect();
                            resolve(document.querySelector(selector));
                        }
                    });
            
                    // If you get "parameter 1 is not of type 'Node'" error, see https://stackoverflow.com/a/77855838/492336
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                });
            }
            
            
            (async () => {
                if (!window.spfmt) {
                    await import("https://cdn.jsdelivr.net/gh/sparqling/sparql-formatter@v1.0.2/dist/spfmt.js");
                }
                console.log(window.spfmt)
                const queries = """+ json.dumps(queries) +""";
                console.log(queries)
                let formatted = [];
                try {
                    formatted = queries.map(x => window.spfmt.format(x));
                    console.log("Formatted queries:\\n", formatted);
                } catch(e) {
                    formatted = 'ERROR: ' + e;
                }
                const elm = await waitForElm('."""+classname+"""');
                const input = elm.getElementsByClassName('widget-input')[0]
                input.value = JSON.stringify(formatted);
                input.dispatchEvent(new Event("input", { bubbles: true }));
            })();
            """)

            
            if output is not None:
                with output:
                    display(ipywidgets.Label('foo2'))
                    display(js)
                    display(ipywidgets.Label('foo3'))
                    display(bridge)
            else:
                display(bridge, js)
            
            def handle_value(x):
                value = x['new']
                bridge.close()
                #future.set_result(json.loads(value))
                callback(json.loads(value))
                if output is not None:
                    output.clear_output()
            
            bridge.observe(handle_value, 'value')
#    except asyncio.TimeoutError:
#        return query