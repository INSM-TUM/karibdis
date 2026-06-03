from typing import Any, Union    
from rdflib.plugins.sparql.sparql import Query
from rdflib.store import TripleAddedEvent, TripleRemovedEvent


from rdflib import Graph, Literal, RDF, URIRef, Namespace
from urllib.parse import quote, unquote
from karibdis.utils import *
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from pandas import notna
import importlib.resources

class ProcessKnowledgeGraph(Graph):
    
    def __init__(self):
        super().__init__()
        # super().__init__(store=Caching_Store())
        self.parse(importlib.resources.files('karibdis').joinpath('base_ontology.ttl'), format='turtle')
        self.parse(importlib.resources.files('karibdis').joinpath('base_rules.ttl'), format='turtle')
        self.parse(importlib.resources.files('karibdis').joinpath('declare_ontology.ttl'), format='turtle')

        self.query_cacheing = {}
        self.store.dispatcher.subscribe(TripleAddedEvent, self.reset_cache)
        self.store.dispatcher.subscribe(TripleRemovedEvent, self.reset_cache)

    def reset_cache(self, context):
        # if len(self.query_cacheing):
        #     print(f"Clearing query cache with {len(self.query_cacheing)} entries")
        self.query_cacheing = {}

    def unassigned_tasks(self):
        return set(self.objects(predicate=~BPO.partOf)) - set(self.subjects(predicate=BPO.performedBy))

    def available_resources(self):
        # return set(self.subjects(predicate=BPO.isAvailable, object=Literal(True)))
        # TODO implement more sophisticated version than "just isn't busy atm"
        available_resources_query = """
            PREFIX : <http://infs.cit.tum.de/karibdis/baseontology/>

            SELECT ?resource
            WHERE {
                ?resource a :Resource .
                FILTER NOT EXISTS { 
                    ?task :performedBy ?resource .  
                    FILTER NOT EXISTS { 
                        ?task :completedAt ?anyTime .  
                    }
                }
            }"""

        for resource_tuple in self.query(available_resources_query):
            yield resource_tuple[0]
    
        
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


    def label(self, uri):
        return next(self.objects(subject=uri, predicate=RDFS.label), self.namespace_manager.curie(uri))

    def query(self, query: Union[Query, str], *args, **kwargs: Any):
        query_key = str(query).replace('\n', ' ').strip()
        #print(f"Run? {query_key not in self.query_cacheing} query: {query}")
        if query_key not in self.query_cacheing:
            # print(f"Adding to cache ({len(self.query_cacheing)}): {query_key}")
            self.query_cacheing[query_key] = super().query(query, *args, **kwargs)
            # print(f"Post adding: {self.query_cacheing}")
        else:
            # print(f"Using cached result for query: {5}")
            pass
        return self.query_cacheing[query_key]

