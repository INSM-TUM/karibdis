from abc import ABC, abstractmethod
from enum import Enum, auto

from rdflib import Graph, Literal, RDF, RDFS, OWL, XSD, URIRef, Namespace
from urllib.parse import quote, unquote
from src.utils import *
from src.utils import BASE_PROCESS_ONTOLOGY as BPO
import src.ProcessKnowledgeGraph as ProcessKnowledgeGraph
from pandas import notna
import pandas as pd
from pandas.api.types import is_string_dtype, is_numeric_dtype, is_datetime64_any_dtype


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
    
    CASE = BPO.Case, BPO.partOf
    TASK = BPO.Task, None
    ACTIVITY = BPO.Activity, BPO.instanceOf
    RESOURCE = BPO.Resource, BPO.performedBy
    ROLE = BPO.Role, BPO.hasRole

    ID = None, 'id'
    DIRECTLY_FOLLOWED_BY = None, BPO.directlyFollowedBy
    CAN_BE_EXECUTED_BY = None, BPO.canBeExecutedBy

default_attribute_aliases = {
    'concept:name' : Keys.ACTIVITY,
    'case:concept:name' : Keys.CASE,
    'org:resource' : Keys.RESOURCE,
#    'OfferID' : ('offer', 'offer') #TODO
}


task_lifecycle_relations = {
    EventType.TASK_ACTIVATE : BPO.activatedAt,
    EventType.TASK_PLANNED : BPO.plannedAt,
    EventType.START_TASK : BPO.startedAt,
    EventType.COMPLETE_TASK : BPO.completedAt,
}


class KnowledgeImporter(ABC):

    def __init__(self, pkg : ProcessKnowledgeGraph):
        self.pkg = pkg
        self.addition_graph = Graph()
        copy_namespaces(self.addition_graph, self.pkg)

    def add(self, triple):
        self.addition_graph.add(triple)

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

#    @abstractmethod
#    def import_event_log(self, log_dataframe):
#        pass



class SimpleEventLogImporter(KnowledgeImporter):

    def __init__(self, pkg : ProcessKnowledgeGraph, namespace_name='log', namespace=Namespace('http://example.org/'), attribute_aliases=default_attribute_aliases, entity_columns=set(), value_columns=set(), ignore_columns=set()):
        super().__init__(pkg)

        self.namespace_name = namespace_name
        self.namespace = namespace
        self.addition_graph.bind(self.namespace_name, self.namespace, override=True)

        self.attribute_aliases = attribute_aliases
        self.reverse_attribute_aliases = dict((v, k) for k, v in attribute_aliases.items())

        # self.case_attributes = set(case_attributes)
        self.ignore_columns = set(ignore_columns).union(set([Keys.CASE, Keys.ID])) # These two are handled differently
        self.entity_columns = set(entity_columns).union(set([Keys.CASE, Keys.ACTIVITY]))
        self.value_columns = set(value_columns)

    
    def log(self, message):
        print(message)

    def entity_instance_node(self, col : str, entity):
        return self.namespace[f'{quote(col)}_{quote(entity)}']
    
    def activity_node(self, activity): #TODO this ignores merged nodes, assuming all relevant activities came from this log/importer
        return self.entity_instance_node(self.reverse_attribute_aliases.get(Keys.ACTIVITY), activity)

    # Default behavior for importing event logs
    def import_event_log_entities(self, log : pd.DataFrame):

        activity_col = self.reverse_attribute_aliases.get(Keys.ACTIVITY) # Must exist

        for col in log:
            print(f'{col}, {log.dtypes[col]} : {log[col].unique()[0:10]}') # TODO: make nice UI
            col_key = self.attribute_aliases.get(col, col)
            if col_key not in self.ignore_columns:

                is_entity_column, is_value_column = self.determine_col_type(col_key, log[col])

                if is_entity_column:
                    print('=> Entity column')
                    values = log[col].dropna().unique()
                    clazz, relation = self.determine_entity_col_class(col, values)
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
    
    def determine_entity_col_class(self, col : str | Keys, coldata) -> tuple[URIRef, URIRef]:
        if col in self.attribute_aliases:
            return self.attribute_aliases[col].type_name, self.attribute_aliases[col].relationship_name
        else:
            # TODO infer proper entity type to be able to reuse existing types => That's the neat part: Do it in a transform step
            return self.namespace['type_'+col], self.namespace['relation_'+col]
    

    def infer_value_col_type(self, col):
        if is_numeric_dtype(col):
            return XSD.float
        elif is_datetime64_any_dtype(col):
            return XSD.dateTimeStamp
        elif set([True, False]).issubset(col.unique()):
            return XSD.boolean
        else:
            return Literal(col.value_counts(dropna=True).index[0]).datatype # Get most common value inferred datatype


    
class OnlineEventImporter(KnowledgeImporter):

    def __init__(self, pkg : ProcessKnowledgeGraph, namespace=Namespace('http://example.org/'), attribute_aliases=default_attribute_aliases, case_attributes=set(), ignore_attributes=set(), entity_attributes=set()):
        super().__init__(pkg)

    
    def lazy_load_resources(self, resources, roles, activities, can_role_execute, can_resource_execute):
            # XXX check if lazy init works here
        
        for activity in activities: # TODO refactor "Add if not known pattern"
            activity_node = self.entity_instance_node(Keys.ACTIVITY, activity)
            if not self.pkg.is_entity_known(activity_node):
                self.add(self.entity_triple(Keys.ACTIVITY, activity))
                
        for resource in resources:
            resource_node = self.entity_instance_node(Keys.RESOURCE, resource)
            if not self.pkg.is_entity_known(resource_node):
                self.add(self.entity_triple(Keys.RESOURCE, resource))

            # Reset direct executability
            self.remove((None, self.attribute_relation(Keys.CAN_BE_EXECUTED_BY), resource_node))
            for activity in activities:
                if can_resource_execute and (can_resource_execute(resource, activity)):
                    self.add((self.entity_instance_node(Keys.ACTIVITY, activity), self.attribute_relation(Keys.CAN_BE_EXECUTED_BY), self.entity_instance_node(Keys.RESOURCE, resource)))
        
        for role, associated_resources in roles.items():
            role_node = self.entity_instance_node(Keys.ROLE, role)
            if not self.pkg.is_entity_known(role_node):
                self.add(self.entity_triple(Keys.ROLE, role))
                
            for activity in activities:
                if can_role_execute and (can_role_execute(role, activity)):
                    self.add((self.entity_instance_node(Keys.ACTIVITY, activity), self.attribute_relation(Keys.CAN_BE_EXECUTED_BY), role_node))
            for resource in associated_resources:
                    self.add((self.entity_instance_node(Keys.RESOURCE, resource), self.attribute_relation(Keys.ROLE), role_node))


    def translate_event(self, event):
        # Add basic node
        node = self.entity_instance_node(Keys.TASK, self.get_entity_attr(event, Keys.ID))
        self.add((node, RDF.type, self.entity_type_node(Keys.TASK)))

        # Connect to case node an case tail
        currentCase = self.get_entity_attr(event, Keys.CASE)
        case_node = self.entity_instance_node(Keys.CASE, currentCase)
        current_tail = self.case_tail(case_node)
        self.set_node_attribute(node, Keys.CASE, currentCase)
        if current_tail:
            # Connect to to preceding node
            self.add((current_tail, self.attribute_relation(Keys.DIRECTLY_FOLLOWED_BY), node))

        # Add event attributes
        for attr in self.get_entity_attr_list(event):
            value = self.get_entity_attr(event, attr)
            target = node if (attr not in self.case_attributes) else case_node
            if notna(value) and (attr not in self.ignore_attributes): 
                self.set_node_attribute(target, attr, value)

        # Can be overriden, currently assumes entities as dicts
    def get_entity_attr(self, entity, attr : str | Keys):
        return entity[self.reverse_attribute_aliases.get(attr, attr)]

    # Can be overriden, currently assumes entities as dicts
    def get_entity_attr_list(self, entity):
        return list(map(lambda attr : self.attribute_aliases.get(attr, attr), entity.keys()))

    def set_node_attribute(self, entity_node, attr, value):
        if attr in self.entity_attributes:
            attr_node = self.entity_instance_node(attr, value)
            if not self.pkg.is_entity_known(attr_node):
                self.add(self.entity_triple(attr, value))
        else:
            attr_node = Literal(value)

        attr_triple = (entity_node, self.attribute_relation(attr), attr_node)
        if attr_triple not in self:
            self.add(attr_triple) 

        return attr_triple
    




class ImporterUI():
    def __init__(self):
        pass

