from rdflib import Graph, Dataset, Literal, RDF, URIRef, Namespace
from random import shuffle
from pyshacl import validate
from ProcessKnowledgeGraph import ProcessKnowledgeGraph
from utils import *
import numbers


# TODO assumes specific namespace
base_prefixes = '''
@prefix activity: <http://example.org/instances/activitys/> .
@prefix case: <http://example.org/instances/cases/> .
@prefix task: <http://example.org/instances/tasks/> .
@prefix relation: <http://example.org/relations/> .
@prefix resource: <http://example.org/instances/resources/> .
@prefix type: <http://example.org/types/> .

@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://foobar.org/> .

'''

clippings = '''
# Shape for Task class
ex:TaskShape
    a sh:NodeShape ;
    sh:targetClass type:task ;  # Target nodes of class Task
    sh:property [
        sh:path relation:instanceOf ;
        sh:class type:activity ;  
		sh:maxCount 1 ;
        sh:minCount 1 ;
        sh:message "Task needs an activity" ;
    ] ;
    sh:property [
        sh:path relation:partOf;
        sh:class type:case;  
		sh:maxCount 1 ;
		sh:minCount 1 ;
        sh:message "Task needs a case" ;
    ] ;
.
'''

base_shacl_code = base_prefixes + '''


ex:ExecutionPermissionConsistency a sh:NodeShape ;
    sh:targetClass type:resource ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:message "The resource '{$this}' is not allowed to perform the activity '{?value}'" ;
        sh:select """
            SELECT (?activity as ?value) (relation:performedBy__hypothetical AS ?path) $this ("Hi there!" as ?message)
            WHERE {
                ?task relation:performedBy__hypothetical $this .
                ?task relation:instanceOf ?activity .
                FILTER NOT EXISTS { 
                    $this relation:hasRole* / ^relation:canBeExecutedBy ?activity .
                }
            }
        """ ;
    ] .


@prefix ApplicationType: <http://example.org/instances/ApplicationTypes/> .

ex:LikesConstraint a sh:NodeShape ;
    sh:targetClass type:resource ;
    ex:value 5 ;
    sh:severity sh:Info;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:message "The resource '{$this}' likes to perform activities in cases of with attribute '{?value}'" ;
        sh:select """
            SELECT  $this (relation:performedBy__hypothetical AS ?path) (?applicationtype as ?value)
            WHERE {
                $this ^relation:performedBy__hypothetical / relation:partOf ?case .
                ?case ?relation ?applicationtype .
                FILTER EXISTS { 
                    $this relation:likes ?applicationtype .
                }
            }
        """ ;
    ] .


''' 


class SHACLAllocator:
    def __init__(self, graph_to_check : ProcessKnowledgeGraph, use_hypothetical=True):
        self.shacl_graph = Graph().parse(data=base_shacl_code, format='n3') 
        self.ontology = Graph().parse('main/base_ontology.ttl', format='n3')
        self.graph_to_check = graph_to_check
        self._first_time = True
        self.use_hypothetical = use_hypothetical

    
    def get_resource(self, task_node, threshold=float('-inf')):
        if self._first_time: # TODO temp
            printmd('#### Example Allocation Situation')
            draw_graph(self.graph_to_check)
            
        if len(list(self.graph_to_check.available_resources())) < 2: #TODO temp to enforce decisions
            return (float('-inf'), None, 'We need more drama')
            
        return next(iter(self.get_top_k_resources(task_node, k=1, threshold=threshold)), (float('-inf'), None, 'No fitting resource found'))

    # Return the top k resources for the given task as ordered list of triples (score, resource_node, results_text)
    def get_top_k_resources(self, task_node, k=-1, threshold=float('-inf')):
        
        if self._first_time:
            self._first_time = False
            # self.init_shacl_graph()

        verdicts = []
        available_resources = list(self.graph_to_check.available_resources()) #& graph.valid_resources(task) 
        shuffle(available_resources)
        
        for resource_node in available_resources:
            test_result = self.test_assignment(task_node, resource_node)
            conforms, results_graph, results_text = test_result
            # print(results_text)
            score, verdict = self.calculate_score(test_result)
            if score >= threshold:
                verdicts.append((score, resource_node, verdict))

        verdicts.sort(reverse=True, key=lambda x : x[0]) # Only sort by score, no secondary 
        if k < 1:
            k = len(verdicts)
        return verdicts[:k]
        

    def calculate_score(self, test_result):
        conforms, results_graph, results_text = test_result
        
        verdict = ''
        score = 0

        for result in results_graph.subjects(predicate=RDF.type, object=URIRef('http://www.w3.org/ns/shacl#ValidationResult')):
            severity = next(results_graph.objects(predicate=URIRef('http://www.w3.org/ns/shacl#resultSeverity'), subject=result))
            if severity == URIRef('http://www.w3.org/ns/shacl#Info'):
                # Method A: Get value dynamically as result from query 
                value = next(results_graph.objects(predicate=URIRef('http://www.w3.org/ns/shacl#value'), subject=result), None)
                
                # Method B: Get static value from constraint spec 
                if value == None or not isinstance(value.toPython(), numbers.Number): # TODO remove this deprecated method B
                    source_constraint = next(results_graph.objects(predicate=URIRef('http://www.w3.org/ns/shacl#sourceShape'), subject=result))
                    value = next(self.shacl_graph.objects(predicate=URIRef('http://foobar.org/value'), subject=source_constraint))# TODO magic string
                    
                score += value.toPython()
            else:
                score += float('-inf')
            message = next(results_graph.objects(predicate=URIRef('http://www.w3.org/ns/shacl#resultMessage'), subject=result))
            verdict += message + '\n'
            # print('Ah, interesting: '+message)
        return score, verdict
        

    def test_assignment(self, task_node, resource_node):
        hypothetical = (
            (task_node,
             self.graph_to_check.attribute_relation(Keys.RESOURCE) + ('__hypothetical' if self.use_hypothetical else ''), #TODO magic string
             resource_node)
        )
    
        assert hypothetical not in self.graph_to_check
        try:
            self.graph_to_check.add(hypothetical)
            
            r = validate(self.graph_to_check,
                  shacl_graph=self.shacl_graph,
                  ont_graph=self.ontology,
                  inference='rdfs',
                  abort_on_first=False,
                  allow_infos=True,
                  allow_warnings=True,
                  meta_shacl=True,
                  advanced=True,
                  js=False,
                  debug=False)
        finally:
            self.graph_to_check.remove(hypothetical)
        
        # display(r)
        # print(results_text)
        return r