from abc import ABC, abstractmethod
from enum import Enum, auto
import numbers

from rdflib import Graph, Literal, RDF, RDFS, OWL, XSD, URIRef, Namespace
from urllib.parse import quote, unquote
from karibdis.utils import *
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
import karibdis.ProcessKnowledgeGraph as ProcessKnowledgeGraph
from pandas import notna
import pandas as pd
from pandas.api.types import is_string_dtype, is_numeric_dtype, is_datetime64_any_dtype
import datetime


from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

from itertools import zip_longest



# TODO are these even still used?
# Copied and adapted from Business Process Optimization Competition 2023
# https://github.com/bpogroup/bpo-project/
class EventType(Enum):
	CASE_ARRIVAL = auto()
	START_TASK = auto()
	COMPLETE_TASK = auto()
	PLAN_TASKS = auto()
	TASK_ACTIVATE = auto()
	TASK_PLANNED = auto()
	COMPLETE_CASE = auto()
	SCHEDULE_RESOURCES = auto()



import enum
class Keys(enum.Enum):

    def __new__(cls, *args, **kwds):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        return obj
    
    def __init__(self, type_name, relationship_name):
        self.type_name = type_name
        self.relationship_name = relationship_name
    
    # CASE = BPO.Case, BPO.partOf
    # TASK = BPO.Task, None
    # ACTIVITY = BPO.Activity, BPO.instanceOf
    # RESOURCE = BPO.Resource, BPO.performedBy
    # ROLE = BPO.Role, BPO.hasRole

    ID = None, 'id'
    TIMESTAMP = None, None
    LIFECYCLE = None, None
    # DIRECTLY_FOLLOWED_BY = None, BPO.directlyFollowedBy
    # CAN_BE_EXECUTED_BY = None, BPO.canBeExecutedBy

default_attribute_aliases = {
    'concept:name' : BPO.Activity,
    'case:concept:name' : BPO.Case,
    'org:resource' : BPO.Resource,
    'time:timestamp' : Keys.TIMESTAMP,
    'lifecycle:transition' : Keys.LIFECYCLE,
}

default_attribute_relations = {
    BPO.Case : BPO.partOf,
    BPO.Activity : BPO.instanceOf,
    BPO.Resource : BPO.performedBy
}


task_lifecycle_relations = {
    EventType.TASK_ACTIVATE : BPO.activatedAt,
    EventType.TASK_PLANNED : BPO.plannedAt,
    EventType.START_TASK : BPO.startedAt,
    EventType.COMPLETE_TASK : BPO.completedAt,
}

default_lifecycle_relations = {
    'start' : EventType.START_TASK,
    'complete' : EventType.COMPLETE_TASK,
}


class KnowledgeImporter(ABC):

    def __init__(self, pkg : ProcessKnowledgeGraph):
        self.pkg = pkg
        self.addition_graph = Graph()
        copy_namespaces(self.addition_graph, self.pkg)
        self.ui = ImporterJupyterUI(self)

    def add(self, triple):
        self.addition_graph.add(triple)

    ### ===== Load =====
    # Nothing to see here, is done in the subclasses, with varying entry points

    ### ===== Alignment =====
    def align(self, addition_node_filter=None, target_node_filter=None, addition_text_params={}, target_text_params={}):
        
        print('Textualizing graphs for alignment...')
        addition_texts = textualize_graph(self.addition_graph, graph_annotations_properties(self.addition_graph, **addition_text_params), filter_func=addition_node_filter)
        target_texts = textualize_graph(self.pkg, graph_annotations_properties(self.pkg, **target_text_params), filter_func=target_node_filter)
        print('Calculating basic alignment...')
        alignment = graph_alignment(addition_texts, target_texts)
        reverse_alignment = graph_alignment(target_texts, addition_texts)

        pairs = dict()
        reverse_pairs = dict()
        for source_id, result in alignment.items():
            pairs.setdefault(source_id, set())
            ranks, top_ids = result
            for i, rank in enumerate(ranks):
                target_id = top_ids[i]
                reverse_pairs.setdefault(target_id, set())
                if source_id in reverse_alignment[target_id][1]:
                    pairs[source_id].add(target_id)
                    reverse_pairs[target_id].add(source_id)
                    
        print('Trial by LLM...')
        trial_by_llm = self.prepare_trial_by_llm() 
        llm_approved = set()
        for index, source_id in enumerate(pairs.keys()):
                print(f'{index}/{len(alignment)}', end='\r')
                matches = pairs[source_id]
                if len(matches) > 0:
                    # print(source_id.n3(addition_graph.namespace_manager))
                    for target_id in matches:
                        # print(f'\t{target_id.n3(target_graph.namespace_manager)}')
                        if trial_by_llm(addition_texts[source_id], target_texts[target_id]):
                            llm_approved.add((source_id, target_id))
                            print(f'{source_id.n3(self.addition_graph.namespace_manager)} -> {target_id.n3(self.pkg.namespace_manager)}')
        with self.ui:
            self.ui.show_alignment_validation(llm_approved)

    def apply_alignment(self, alignment_edges):
        for s,p,o in filter(lambda triple: OWL.sameAs in triple, alignment_edges):
            rename_identifier(self.addition_graph, s, o)

    def prepare_trial_by_llm(self):
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from dotenv import load_dotenv
        load_dotenv()


        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini")
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                "system", # TODO prompt is currently very generous
        '''You are a knowledge importer for a knowledge-graph-based business process management system.
Your task is to decide whether two stringifications of knowledge graph are related to the same concept.
Please output only True or False, whether the entities represented are related.''',
                ),
                ("human", "String 1:\n{str1}\n\n\nString 2:\n{str2}"),
            ]
        )
        chain = prompt | llm

        def trial_by_llm(source_text, target_text):
            #print(prompt.format(str1=addition_texts[source_id], str2=target_texts[target_id]))
            return chain.invoke(
                {
                    "str1": source_text,
                    "str2": target_text,
                }
            ).content == 'True'
        
        return trial_by_llm

    ### ===== Validate =====
    def validate(self):
        self.ui.show_validation()

    def reload_from_text(self, text):
        self.addition_graph = Graph() 
        copy_namespaces(self.addition_graph, self.pkg)

        self.addition_graph.parse(data=text, format='turtle')


    ### ===== Load =====
    def load(self):
        self.load_namespaces()
        self.pkg += self.addition_graph

    def load_namespaces(self):
        bound_uris = dict(self.pkg.namespaces()).values()
        bound_aliases = dict(self.pkg.namespaces()).keys()
        for alias, namespace in self.addition_graph.namespaces():
            if namespace not in bound_uris:
                alias_to_bind = alias
                index = 0
                while alias_to_bind in bound_aliases:
                    alias_to_bind = alias + index
                    index += 1
                self.pkg.bind(alias_to_bind, namespace, override=True)


    ### ===== Util =====    
    def log(self, message):
        print(message)

#    @abstractmethod
#    def import_event_log(self, log_dataframe):
#        pass



class SimpleEventLogImporter(KnowledgeImporter):

    def __init__(
            self, 
            pkg : ProcessKnowledgeGraph, 
            namespace_name='log', 
            namespace=Namespace('http://example.org/'), 
            attribute_aliases=default_attribute_aliases, 
            entity_columns=set(), 
            value_columns=set(), 
            ignore_columns=set()):
        super().__init__(pkg)

        self.namespace_name = namespace_name
        self.namespace = namespace
        self.addition_graph.bind(self.namespace_name, self.namespace, override=True)

        self.attribute_aliases = attribute_aliases
        self.reverse_attribute_aliases = dict((v, k) for k, v in attribute_aliases.items())

        self.ignore_columns = set(ignore_columns).union(set([BPO.Case, Keys.ID, Keys.LIFECYCLE, Keys.TIMESTAMP])) # These are handled differently
        self.entity_columns = set(entity_columns).union(set([BPO.Case, BPO.Activity]))
        self.value_columns = set(value_columns)


    def entity_instance_node(self, col : str | URIRef, entity):
        return self.namespace[f'{quote(uri_to_id(col))}_{quote(entity)}']
    
    def activity_node(self, activity): #TODO this ignores merged nodes, assuming all relevant activities came from this log/importer
        return self.entity_instance_node(BPO.Activity, activity)

    # Default behavior for importing event logs
    def import_event_log_entities(self, log : pd.DataFrame):

        activity_col = self.reverse_attribute_aliases.get(BPO.Activity) # Must exist

        for col in log:
            print(f'{col}, {log.dtypes[col]} : {log[col].unique()[0:10]}') # TODO: make nice UI
            col_key = self.attribute_aliases.get(col, col)
            if col_key not in self.ignore_columns:

                is_entity_column, is_value_column = self.determine_col_type(col_key, log[col])

                # TODO: Do something with case attributes vs. task attributes

                if is_entity_column:
                    print('=> Entity column')
                    values = log[col].dropna().unique()
                    clazz = self.determine_entity_col_class(col, values)
                    if (clazz, RDF.type, OWL.Class) not in self.pkg:
                        self.add((clazz, RDF.type, OWL.Class))  # Add OWL Class triple
                        self.log(f'Added type owl class for {col}: {clazz}')

                    for entity in values:
                        entity_node = self.entity_instance_node(col, entity)
                        self.add((entity_node, RDF.type, clazz))
                        self.add((entity_node, RDFS.label, Literal(entity)))

                if is_value_column:
                    value_node = self.entity_instance_node('processValue', col) # TODO magic string
                    self.add((value_node, RDF.type, BPO.ProcessValue))

                    for activity in log[log[col].notnull()][activity_col].unique(): 
                        activity_node = self.activity_node(activity) 
                        self.add((activity_node, BPO.writesValue , value_node))

                    type_hint = self.infer_value_col_type(log[col])
                    self.add((value_node, BPO.dataType , type_hint))
                    print(f'=> Value column of type {type_hint}')


    def determine_col_type(self, col_key : str | Keys, col_data):
        is_entity_column = False
        is_value_column = False

        if col_key in self.entity_columns:
            is_entity_column = True
        elif col_key in self.value_columns:
            is_value_column = True
        elif is_numeric_dtype(col_data) or is_datetime64_any_dtype(col_data):
            is_value_column = True
        elif set([True, False]).issubset(col_data.unique()):
            is_value_column = True
        else:
            is_entity_column = True

        return is_entity_column, is_value_column
    
    def determine_entity_col_class(self, col : str | URIRef, coldata) -> URIRef:
        if isinstance(col, URIRef):
            return col
        elif col in self.attribute_aliases:
            return self.attribute_aliases[col]
        else:
            # TODO infer proper entity type to be able to reuse existing types => That's the neat part: Do it in a transform step
            return self.namespace['type_'+quote(col)]# , self.namespace['relation_'+quote(col)]
    

    def infer_value_col_type(self, col):
        if is_numeric_dtype(col):
            return XSD.float
        elif is_datetime64_any_dtype(col):
            return XSD.dateTimeStamp
        elif set([True, False]).issubset(col.unique()):
            return XSD.boolean
        else:
            return Literal(col.value_counts(dropna=True).index[0]).datatype # Get most common value inferred datatype


# Imports events as they occur
class OnlineEventImporter(SimpleEventLogImporter):

    def __init__(
            self, 
            pkg : ProcessKnowledgeGraph, 
            namespace_name='log', 
            namespace=Namespace('http://example.org/'), 
            attribute_aliases=default_attribute_aliases, 
            attribute_relations=dict(), 
            lifecycle_relations=default_lifecycle_relations,
            entity_columns=set(), 
            value_columns=set(), 
            ignore_columns=set(), 
            case_attributes=set()):
        super().__init__(pkg, namespace_name, namespace, attribute_aliases, entity_columns, value_columns, ignore_columns)
        self.attribute_relations = dict(default_attribute_relations)
        self.attribute_relations.update(attribute_relations)
        self.lifecycle_relations = lifecycle_relations
        self.case_attributes = set(case_attributes)

    
    def lazy_load_resources(self, resources, roles, activities, can_role_execute, can_resource_execute):
            # XXX check if lazy init works here
        
        for activity in activities: # TODO refactor "Add if not known pattern"
            activity_node = self.entity_instance_node(BPO.Activity, activity)
            if not self.pkg.is_entity_known(activity_node):
                self.add(self.entity_triple(BPO.Activity, activity))
                
        for resource in resources:
            resource_node = self.entity_instance_node(BPO.Resource, resource)
            if not self.pkg.is_entity_known(resource_node):
                self.add(self.entity_triple(BPO.Resource, resource))

            # Reset direct executability
            self.remove((None, BPO.canBeExecutedBy, resource_node))
            for activity in activities:
                if can_resource_execute and (can_resource_execute(resource, activity)):
                    self.add((self.entity_instance_node(BPO.Activity, activity), BPO.canBeExecutedBy, self.entity_instance_node(BPO.Resource, resource)))
        
        for role, associated_resources in roles.items():
            role_node = self.entity_instance_node(BPO.Role, role)
            if not self.pkg.is_entity_known(role_node):
                self.add(self.entity_triple(BPO.Role, role))
                
            for activity in activities:
                if can_role_execute and (can_role_execute(role, activity)):
                    self.add((self.entity_instance_node(BPO.Activity, activity), BPO.canBeExecutedBy, role_node))
            for resource in associated_resources:
                    self.add((self.entity_instance_node(BPO.Resource, resource), BPO.hasRole, role_node))


    def translate_event(self, event):
        # Context
        current_case = self.get_entity_attr(event, BPO.Case)
        case_node = self.entity_instance_node(BPO.Case, current_case)

        # Add basic node
        task_node = self.entity_instance_node(BPO.Task, self.task_id_for_event(event, current_case, case_node)) # TODO: Why infer type task? Could be different event!
        self.add((task_node, RDF.type, BPO.Task))

        # Connect to case node an case tail
        current_tail = self.case_tail(case_node)
        self.set_node_attribute(task_node, BPO.Case, current_case)
        if current_tail:
            # Connect to to preceding node
            self.add((current_tail, BPO.directlyFollowedBy, task_node))

        attributes = self.get_entity_attr_list(event)

        # Log lifecycle transition timestamp
        if Keys.TIMESTAMP in attributes:
            value = self.get_entity_attr(event, Keys.TIMESTAMP)
            event_type = None
            if Keys.LIFECYCLE in attributes:
                lifecycle_attr = self.get_entity_attr(event, Keys.LIFECYCLE)
                event_type = self.lifecycle_relations.get(lifecycle_attr, None) # Explicitly None for unknown lifecycle values
            else:
                event_type = EventType.COMPLETE_TASK
            if event_type: # Otherwise, there is a lifecycle value, but none that has a translation
                self.add((task_node, task_lifecycle_relations[event_type], Literal(value)))


        # Add event attributes to either task or case
        for attr in attributes:
            value = self.get_entity_attr(event, attr)
            target = task_node if (attr not in self.case_attributes) else case_node

            if notna(value) and (attr not in self.ignore_columns): 
                self.set_node_attribute(target, attr, value)

                

    def case_tail(self, case_node):
        def case_tail_in(graph, case_node):
            case_tasks = set(graph.objects(subject=case_node, predicate=~BPO.partOf))
            followed_case_tasks = set(graph.objects(subject=case_node, predicate=~BPO.partOf / ~BPO.directlyFollowedBy))
            return next(iter(case_tasks - followed_case_tasks), None)
        loading_tail = case_tail_in(self.addition_graph, case_node)
        if not loading_tail:
            return case_tail_in(self.pkg, case_node)
        else:
            return loading_tail

    
        # Can be overriden, currently assumes entities as dicts
    def get_entity_attr(self, entity, attr : str | URIRef):
        return entity[self.reverse_attribute_aliases.get(attr, attr)]

    # Can be overriden, currently assumes entities as dicts
    def get_entity_attr_list(self, entity):
        return list(map(lambda attr : self.attribute_aliases.get(attr, attr), entity.keys()))

    def set_node_attribute(self, entity_node, attr : str | URIRef, value):
        is_entity_column, is_value_column = self.determine_col_type(attr, value)
        if is_entity_column:
            clazz = self.determine_entity_col_class(attr, [value])
            attr_node = self.entity_instance_node(attr, value)
            #if not self.pkg.is_entity_known(attr_node):
            self.add((attr_node, RDF.type, clazz))
        else:
            attr_node = Literal(value)

        attr_triple = (entity_node, self.attribute_relation(attr), attr_node) 
        self.add(attr_triple) 

        return attr_triple
    
    # TODO a lot of code duplication
    def determine_col_type(self, col_key : str | Keys, col_data):
        is_entity_column = False
        is_value_column = False

        if col_key in self.entity_columns:
            is_entity_column = True
        elif col_key in self.value_columns:
            is_value_column = True
        elif isinstance(col_data, numbers.Number) or isinstance(col_data, datetime.date):
            is_value_column = True
        elif col_data in set([True, False]):
            is_value_column = True
        else:
            is_entity_column = True

        return is_entity_column, is_value_column
    
    def attribute_relation(self, attr):
        return self.attribute_relations.get(attr, self.namespace[quote(attr)])
    
    def task_id_for_event(self, event, case_id, case_node):
        try:
            return self.get_entity_attr(event, Keys.ID)
        except:  # TODO: A bit hacky
            num_current_tasks = len(set(self.addition_graph.objects(subject=case_node, predicate=~BPO.partOf)) | set(self.pkg.objects(subject=case_node, predicate=~BPO.partOf)))
            return f'{case_id}_{num_current_tasks + 1}' # TODO: This doesn't allow to have mulitple events for the same task!



class TextualImporter(KnowledgeImporter):

    
    load_dotenv()

    def __init__(self, pkg, llm=ChatOpenAI(temperature=0, model="gpt-4o-mini")):
        super().__init__(pkg)
        self.llm = llm

    def import_content_from_statement(self, statement : str):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
'''You are a knowledge importer for a knowledge-graph-based business process management system.
Your task is to input textual process knowledge and an existing knowledge graph and output new nodes and edges representing the knowledge of the text.
Reuse existing owl:classes and owl:properties where appropriate. 
Reuse existing entity nodes where appropriate.

Please output the nodes and edges in RDF-turtle-syntax.
Output nothing else. Don't output any notes or justifications.

For generating the nodes and edges, please consider the following contextual schema information in OWL-RDF format and key entities in RDF format.  

{context}''',
                ),
                ("human", "{statement}"),
            ]
        )
        prompt_context = self.pkg.serialize(format='ttl')

        chain = prompt | self.llm
        response = chain.invoke(
            {
                "context": prompt_context,
                "statement": statement,
            }
        ).content
        self.log(response)
        self.addition_graph.parse(data=f'{namespace_string(self.pkg)}\n\n{unwrap_markdown_code(response)}', format='turtle')


class ExistingOntologyImporter(KnowledgeImporter):

    def __init__(self, pkg : ProcessKnowledgeGraph):
        super().__init__(pkg)

    def import_ontology(self, ontology, initial_query=None):

        def accept_filtered_result(result):
            self.addition_graph += result
            # Add predicates metadata so annotation properties can be used
            predicates = set(self.addition_graph.predicates())
            self.addition_graph += list(filter(lambda triple: triple[0] in predicates or triple[2] in predicates, ontology))

        with self.ui:
            self.ui.prompt_selection_query(ontology, callback_accept=accept_filtered_result, initial_query=initial_query)



class ImporterUI(ABC):
    def __init__(self, importer : KnowledgeImporter):
        assert importer is not None
        self.importer = importer
    
    @abstractmethod
    def show_validation(self):
        pass

    @abstractmethod
    def show_alignment_validation(self, llm_approved):
        pass

    @abstractmethod
    def prompt_selection_query(self, initial_query=None, callback_accept=None):
        pass

    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_value, exc_traceback):
        pass

import ipywidgets
from IPython.display import display, clear_output    
from jupyter_ui_poll import ui_events
import time

class ImporterJupyterUI(ImporterUI):

    def __init__(self, importer : KnowledgeImporter):
        super().__init__(importer)

    def __enter__(self):
        # TODO to be implemented
        pass


    def __exit__(self, exc_type, exc_value, exc_traceback):
        # TODO to be implemented
        pass

    def show_alignment_validation(self, llm_approved):
        g1 = Graph()
        copy_namespaces(g1, self.importer.addition_graph)
        g2 = Graph()
        copy_namespaces(g2, self.importer.addition_graph)
        hidden = URIRef('http://example.org/hidden')

        # colors = dict()
        for source_id, target_id in llm_approved:
            g1.add((source_id, OWL.sameAs, target_id))
            g2.add((target_id, URIRef('hidden'), hidden))
            # colors[source_id] = '#99AA00'
            # colors[target_id] = '#1100AA' 
            
        alignment_knowledge_importer = KnowledgeImporter(g2)
        alignment_knowledge_importer.addition_graph = g1
        alignment_knowledge_importer.validate()

        self.importer.apply_alignment(list(filter(lambda triple: hidden not in triple, g2)))

        # draw_graph(g, lambda _ : colors)

    def show_validation(self):
        self.loaded = False
        self.output = ipywidgets.Output()
        self.show_graph()
        display(self.output)
        with ui_events() as poll:
            while self.loaded is False:
                poll(10)          # React to UI events (up to 10 at a time)
                time.sleep(0.1)

    def show_graph(self, b=None):
        button_accept = ipywidgets.Button(description='Accept')
        def accept(b=None):
            self.importer.load()
            with self.output:
                self.output.clear_output()
                print('Data successfully loaded into the knowledge graph.')
                self.loaded = True
        button_accept.on_click(accept)
        button_edit = ipywidgets.Button(description='Edit')
        button_cancel = ipywidgets.Button(description='Cancel')
        button_edit.on_click(self.show_edit)
        with self.output:
            self.output.clear_output()
            self.visualize_addition_graph()
            display(button_accept, button_edit, button_cancel)

    
    def visualize_addition_graph(self): 
        draw_graph(self.importer.addition_graph, color_func=lambda _: dict(zip_longest(self.importer.addition_graph.all_nodes() - self.importer.pkg.all_nodes(), [], fillvalue='#99AA00')))

    def show_edit(self, b=None):
        init_value = self.importer.addition_graph.serialize(format='ttl')
        text = ipywidgets.Textarea(
            layout = ipywidgets.Layout(width='98%'),
            value = init_value,
            rows = len(init_value.split('\n'))
        )
        button_accept = ipywidgets.Button(description='Accept Edit')
        def accept_edit(b=None):
            if text.value != init_value:
                self.importer.reload_from_text(text.value)
            else:
                print('No changes')
            self.show_graph()
        button_accept.on_click(accept_edit)
        button_cancel = ipywidgets.Button(description='Cancel Edit')
        button_cancel.on_click(self.show_graph)
        with self.output:
            self.output.clear_output()
            display(ipywidgets.Label('Data to load'), text, button_accept, button_cancel)

    def prompt_selection_query(self, graph, initial_query=None, callback_accept=None):
        self.output = ipywidgets.Output()

        label = ipywidgets.Label()
        def update_label(result_size):
            label.value = f'You are about to load {result_size} tuples. Adapt the query if appropriate.'

        if initial_query is None: # TODO consider adding namespaces per default
            initial_query = '''
SELECT ?subject ?predicate ?object
WHERE {?subject ?predicate ?object} 
'''
        text = ipywidgets.Textarea(
            layout = ipywidgets.Layout(width='98%'),
            value = initial_query,
            rows = len(initial_query.split('\n'))
        )

        button_accept = ipywidgets.Button(description='Load Data')
        def accept(b=None):
            with self.output:
                callback_accept(graph.query(text.value)) # TODO reduc unnecessary duplicate query running
                self.output.clear_output()
                print('Ontology successfully queries.')
        button_accept.on_click(accept)

        button_edit = ipywidgets.Button(description='Update Query')
        def edit(b=None):
            button_edit.disabled = True
            update_label(len(graph.query(text.value)))
            button_edit.disabled = False

        button_edit.on_click(edit)

        button_cancel = ipywidgets.Button(description='Cancel')
        with self.output:
            self.output.clear_output()
            edit()
            display(label, text, button_accept, button_edit, button_cancel)

        display(self.output)

