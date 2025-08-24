from rdflib import Graph, Literal, RDF, URIRef, Namespace
from urllib.parse import quote, unquote
from karibdis.utils import *
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from pandas import notna
import importlib.resources

class ProcessKnowledgeGraph(Graph):
    
    def __init__(self):
        super().__init__()
        self.parse(importlib.resources.path('karibdis', 'base_ontology.ttl'), format='turtle')
        self.parse(importlib.resources.path('karibdis', 'base_rules.ttl'), format='turtle')
        self.parse(importlib.resources.path('karibdis', 'declare_ontology.ttl'), format='turtle')


    def unassigned_tasks(self):
        return set(self.objects(predicate=~BPO.partOf)) - set(self.subjects(predicate=BPO.performedBy))

    def available_resources(self):
        return set(self.subjects(predicate=BPO.isAvailable, object=Literal(True)))
        
    def valid_resources(self, task_node):
        return set(self.objects(subject=task_node, predicate=BPO.instanceOf / BPO.canBeExecutedBy)) # TODO use rule engine

    def update_availability(self, is_available=lambda resource_node: True):
        self.remove((None, BPO.isAvailable, None))
        for resource_node in self.subjects(predicate=RDF.type, object=BPO.Resource):
            self.add((resource_node, BPO.isAvailable, Literal(is_available(resource_node))))

    def handle_assignment(self, task_node, resource_node):
        self.add((task_node, BPO.performedBy, resource_node))
        self.set(resource_node, BPO.isAvailable, Literal(False))
            

    def subgraph_available_resources(self):
        available_resources = set(self.available_resources())
        resources_assigned = set(self.objects(predicate=BPO.performedBy))
        relevant_resources = available_resources | resources_assigned
        filtered_graph = self - set(filter(lambda triple : ('resource' in ''.join(triple)) and len(set(triple) & relevant_resources) == 0, self)) # TODO This line might not work anymore
        filtered_graph.namespace_manager = self.namespace_manager
        return filtered_graph


    def is_entity_known(self, entity_node):
        return entity_node in self.all_nodes()


    def uri(self, string):
        prefix, id = string.split(':', 1)
        _, uri = next(filter(lambda nsp : nsp[0] == prefix, self.namespace_manager.namespaces()))
        return uri + quote(id)

    def add_rule(self, rule):
        self.addN((s, p, o, URIRef('http://infs.cit.tum.de/karibdis/rules')) for s, p, o in rule) # TODO: magic string and also no thought put into this 

