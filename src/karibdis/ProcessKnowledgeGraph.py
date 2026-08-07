from typing import Any, Union    
from rdflib.plugins.sparql.sparql import Query
from rdflib.store import TripleAddedEvent, TripleRemovedEvent


from rdflib import Graph, Literal, RDF, URIRef, Namespace
from urllib.parse import quote, unquote
from karibdis.utils import *
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from pandas import notna
import importlib.resources


from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery

class ProcessKnowledgeGraph(Graph):
    
    def __init__(self):
        super().__init__()
        self.parse(importlib.resources.files('karibdis').joinpath('base_ontology.ttl'), format='turtle')
        self.parse(importlib.resources.files('karibdis').joinpath('base_rules.ttl'), format='turtle')
        self.parse(importlib.resources.files('karibdis').joinpath('declare_ontology.ttl'), format='turtle')

        self.query_result_cache = {}
        self.store.dispatcher.subscribe(TripleAddedEvent, self.reset_cache)
        self.store.dispatcher.subscribe(TripleRemovedEvent, self.reset_cache)
        self.query_parse_cache = {}

    def reset_cache(self, context):
        # if len(self.query_result_cache):
        #     print(f"Clearing query cache with {len(self.query_result_cache)} entries")
        #print(context.triple)
        #if  '__hypothetical' in str(context.triple):
        #    print('Optimize')
        self.query_result_cache = {}

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
        # Fixes initBindings being passed as a positional argument instead of a keyword argument while retaining stability toward rdflib updates
        # See https://stackoverflow.com/questions/62721132/python-check-if-an-argument-was-passed-in-by-position-or-by-keyword?rq=3
        argnames = Graph.query.__code__.co_varnames
        argdict = dict(zip(argnames, args))
        argdict.update(kwargs)

        # print(query)
        query_key = str(query).replace('\r\n', ' ').replace('\n', ' ').strip()
        bindings_key = str(sorted((str(k), str(v)) for k, v in argdict.get('initBindings', {}).items()))
        query_key_parameterized = query_key + bindings_key
        #print(f"Run? {query_key not in self.query_result_cache} query: {query}")
        
        if isinstance(query, str):
            if query_key not in self.query_parse_cache:
                self.query_parse_cache[query_key] = translateQuery(parseQuery(query), None, dict(self.namespaces()))
            query = self.query_parse_cache[query_key]

        if query_key not in self.query_result_cache:
            # print(f"Adding to cache ({len(self.query_result_cache)}): {query_key}")
            self.query_result_cache[query_key_parameterized] = super().query(query, *args, **kwargs)
            # print(f"Post adding: {self.query_result_cache}")
        else:
            # print(f"Using cached result for query: {5}")
            pass
        return self.query_result_cache[query_key_parameterized]

