from abc import ABC, abstractmethod
from itertools import zip_longest
import os
import ipywidgets
from IPython.display import display, clear_output, Javascript

import uuid

import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v
from ipywidgets.widgets.widget_string import LabelStyle

import pm4py
import json

from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.utils import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from karibdis.KnowledgeImporter import KnowledgeImporter, TextualImporter, SimpleEventLogImporter, ExistingOntologyImporter
import datetime
from rdflib import Literal, RDFS, XSD
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO


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
            ('Decisionmaking', reacton.render_fixed(DecisionUI(self.system.engine))[0]),
            ('Task Execution', reacton.render_fixed(TaskExecutionUI(self.system.engine))[0]),
            ('Explore Graph', reacton.render_fixed(GraphExplorationUI(self.system.pkg))[0]),
        ]
        root = ipywidgets.Tab()
        root.layout = ipywidgets.Layout(width='100%', height='100%')
        root.children = [tab[1] for tab in tabs]
        for tab in root.children:
            tab.layout = ipywidgets.Layout(width='100%', height='60vh')
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
    allowed_templates, set_allowed_templates = reacton.use_state(['init', 'chainresponse', 'exactly_one'])
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
            item_equality=lambda decision_a, decision_b : decision_a.subject == decision_b.subject
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
    with w.VBox(layout=w.Layout(overflow='scroll', height='60vh', width='100%')) as main:
        v.CardTitle(children=f' Decide {engine.pkg.label(context_type)}' + (f' for {engine.pkg.label(context_case)}' if context_case else ''))
        options, set_options = reacton.use_state([])
        reacton.use_effect(lambda: set_options(current_decision.get_top_k_results(20)), [current_decision])
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
def TaskExecutionUI(engine): # TODO refactor to use SelectionMenu like DecisionUI
    attribute_values, set_attribute_values = reacton.use_state({})
    with w.VBox() as main:
        v.CardTitle(children='Task Execution')
        tasks, set_tasks = reacton.use_state(list(engine.open_tasks()))

        def reload():
            set_tasks(list(engine.open_tasks()))
            set_attribute_values({})  # Reset form fields
                
        with w.VBox():
            if len(tasks) > 0:
                TaskBody(tasks, engine, reload, attribute_values, set_attribute_values)
            else: 
                w.Label(value="No open tasks.")
            w.Button(description="Reload Tasks", on_click=lambda *args: reload(), layout=w.Layout(flex='0 0 auto'))
            
    return main

@reacton.component
def TaskBody(tasks, engine, reload, attribute_values, set_attribute_values):
    pkg = engine.pkg
    current_task, set_current_task = reacton.use_state(tasks[0][0])
    current_case, set_current_case = reacton.use_state(tasks[0][1])
    reacton.use_effect(lambda: set_current_task(tasks[0][0]), [tasks])
    reacton.use_effect(lambda: set_current_case(tasks[0][1]), [tasks])
    
    submit_clicked, set_submit_clicked = reacton.use_state(False)
    
    with w.HBox() as main:
        activity = next(pkg.objects(predicate = BPO.instanceOf, subject = current_task), None)
        attributes = list(pkg.objects(subject=activity, predicate=BPO.writesValue))
        
        def on_submit_click(*args):
            # iterate over all expected attributes (use compute_default_for when missing)
            for attr in attributes:
                attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr), None)

                # safe read of state variable
                current_vals = attribute_values if isinstance(attribute_values, dict) else dict(attribute_values or {})

                # use stored value or compute a default now
                val = current_vals.get(attr)
                if val is None:
                    val = compute_default_for(attr)
                    # persist the default so UI and future submits see it
                    try:
                        set_attribute_values(lambda prev: {**(prev or {}), attr: val})
                    except Exception:
                        av = dict(attribute_values or {})
                        av[attr] = val
                        set_attribute_values(av)

                
                is_entity = attr_type is not None and not str(attr_type).startswith(str(XSD._NS))
                if val is None and is_entity:
                    missing_name = next(pkg.objects(predicate=RDFS.label, subject=attr), uri_to_id(attr))
                    print(f"Cannot submit — missing entity value for: {missing_name}")
                    return

                if is_entity:
                    # val is a curie string (from Dropdown) -> expand to URIRef
                    obj = pkg.namespace_manager.expand_curie(val) if isinstance(val, str) else val
                    pkg.set((current_case, attr, obj))
                else:
                    lit = Literal(val, datatype=attr_type if attr_type is not None else None)
                    pkg.set((current_case, attr, lit))

            engine.complete_task(current_task)
            reload()
            set_submit_clicked(True)

        reacton.use_effect(lambda: set_submit_clicked(False), [current_task])
        
        
        with w.VBox():
            for task, case in tasks:
                w.Button(description=f"Task: {pkg.namespace_manager.curie(task)} - Case: {pkg.namespace_manager.curie(case)}", on_click=lambda t=task, c=case: (set_current_task(t), set_current_case(c)), style=w.ButtonStyle(button_color='#DDEEFF' if task == current_task else None))
        
        def load_existing_value_for(attr):
            
            existing = pkg.value(subject=current_case, predicate=attr)
            if existing is not None:
                return existing.toPython() if isinstance(existing, Literal) else pkg.namespace_manager.curie(existing)
            else:
                return compute_default_for(attr)
            
        def compute_default_for(attr):
            # return a default value consistent with what _init_defaults would have set
            attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr), None)
            if attr_type not in XSD:
                options = list(pkg.subjects(predicate=RDF.type, object=attr_type))
                return pkg.namespace_manager.curie(options[0]) if options else None
            if attr_type == XSD.integer:
                return 0
            if attr_type == XSD.float:
                return 0.0
            if attr_type == XSD.boolean:
                return False
            return ""
        
        layout= w.Layout(description_width="initial")
        
        def on_widget_change(attr, _):
            def handler(new_value):
               
                try:
                    
                    set_attribute_values(lambda prev: {**(prev or {}), attr: new_value})
                except TypeError:
                    # fallback if functional updater not supported: build a safe local copy
                    av = dict(attribute_values or {})
                    av[attr] = new_value
                    set_attribute_values(av)
            return handler
        
        with w.VBox():  
            w.Label(value= f"Selected Task: {pkg.label(activity)} - {pkg.label(current_task)} ")
            grid = w.Layout(grid_template_columns='1fr 1fr 1fr', grid_gap='8px')
            with w.GridBox(layout=grid):
                # header row
                w.Label(value='Attribute')
                w.Label(value='Value')
                w.Label(value='Type')
                for attr in attributes:
                    attr_name = next(pkg.objects(predicate=RDFS.label, subject=attr), uri_to_id(attr))
                    attr_type = next(pkg.objects(predicate=BPO.dataType, subject=attr), None)
                    default_value = attribute_values.get(attr, load_existing_value_for(attr))
                    if attr_type not in XSD:
                        options = pkg.subjects(predicate=RDF.type, object=attr_type)
                        short_options = [pkg.namespace_manager.curie(option) for option in options]  
                        widget = w.Dropdown(value=default_value, options=short_options, layout=layout, on_value=on_widget_change(attr, None))
                        type_label = pkg.namespace_manager.curie(attr_type)
                    elif attr_type == XSD.string:
                        widget = w.Text(value=default_value, layout=layout, on_value=on_widget_change(attr, None))
                        type_label = 'string'
                    elif attr_type == XSD.integer:
                        widget = w.IntText(value=default_value, layout=layout, on_value=on_widget_change(attr, None))
                        type_label = 'integer'
                    elif attr_type == XSD.float:
                        widget = w.FloatText(value=default_value, layout=layout, on_value=on_widget_change(attr, None))
                        type_label = 'float'
                    elif attr_type == XSD.boolean:
                        widget = w.Checkbox(value=default_value, on_value=on_widget_change(attr, None))
                        type_label = 'boolean'
                    
                    else:
                        widget = w.Text(value=default_value, layout=layout, on_value=on_widget_change(attr, None))
                        type_label = 'string'
                    
                    w.Label(value=attr_name)
                    w.Box(children=[widget])
                    w.Label(value=type_label)
            w.Button(description="Submit", on_click=on_submit_click, layout=w.Layout(flex='0 0 auto'))
                
    return main

# =========================== UTILS ===========================

@reacton.component
def SelectionMenu(title, items, set_items, reload, item_label, make_item_view, item_equality = lambda a,b : a is b):
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
                    w.Label(value='Nothing to select')
                    
        w.Button(description='Reload', on_click=reload)
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
    current_result_size, set_current_result_size = reacton.use_state(0)
    dirty, set_dirty = reacton.use_state(True)
    query, _set_query = reacton.use_state(initial_query if initial_query else default_initial_query) 
    def set_query(value):
        set_dirty(True)
        _set_query(value)  

    place_box = lambda : w.Textarea(
        layout = w.Layout(width='98%'),
        value = query,
        on_value=set_query,
        rows = len(query.split('\n')) + 2
    )

    def run_query():
        query_result = graph.query(query)
        print(query_result)
        set_current_result_size(len(query_result))
        set_dirty(False)
        set_current_result(query_result)

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