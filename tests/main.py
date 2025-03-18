import unittest
from . import context
from src.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from src.SHACLAllocator import SHACLAllocator
from rdflib import Graph



test_graph_data = '''
@prefix ApplicationType: <http://example.org/instances/ApplicationTypes/> .
@prefix LoanGoal: <http://example.org/instances/LoanGoals/> .
@prefix activity: <http://example.org/instances/activitys/> .
@prefix case: <http://example.org/instances/cases/> .
@prefix task: <http://example.org/instances/tasks/> .
@prefix relation: <http://example.org/relations/> .
@prefix resource: <http://example.org/instances/resources/> .
@prefix four_eyes: <http://example.org/instances/four_eyes/> .
@prefix type: <http://example.org/types/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .


task:task-1 a type:task ;
    relation:directlyPrecedes task:task-2 ;
    relation:instanceOf activity:W_Call%20after%20offers ;
    relation:performedBy resource:User_1 ;
    relation:partOf case:case-0 .
    
task:task-2 a type:task ;
    relation:directlyPrecedes task:task-3 ;
    relation:instanceOf activity:W_Validate%20application ;
    relation:performedBy resource:User_2 ;
    relation:partOf case:case-0 .
    
task:task-3 a type:task ;
    relation:instanceOf activity:W_Assess%20potential%20fraud ;
    relation:partOf case:case-0 .
    

activity:W_Handle%20leads a type:activity ;
    relation:canBeExecutedBy resource:User_2,
        resource:User_1,
        resource:User_3 .

activity:W_Complete%20application a type:activity ;
    relation:canBeExecutedBy resource:User_2,
        resource:User_1,
        resource:User_3 .


activity:W_Call%20after%20offers a type:activity ;
    relation:canBeExecutedBy resource:User_2,
        resource:User_1,
        resource:User_3 .

activity:W_Call%20incomplete%20files a type:activity ;
    relation:canBeExecutedBy resource:User_2,
        resource:User_1,
        resource:User_3 .

activity:W_Validate%20application a type:activity ;
    relation:canBeExecutedBy resource:User_2,
        resource:User_1,
        resource:User_3 .

activity:W_Assess%20potential%20fraud a type:activity ;
    relation:canBeExecutedBy resource:User_2,
        resource:User_1,
        resource:User_3 .

case:case-0 a type:case ;
    relation:ApplicationType ApplicationType:New%20credit ;
    relation:LoanGoal LoanGoal:Existing%20loan%20takeover .



ApplicationType:New%20credit a type:ApplicationType .

LoanGoal:Existing%20loan%20takeover a type:LoanGoal .

resource:User_3 a type:resource ;
    relation:available true.

resource:User_2 a type:resource ;
    relation:available true.

resource:User_1 a type:resource ;
    relation:available true.
    
four_eyes:rule1 a type:four_eyes ;
    relation:contains activity:W_Validate%20application, activity:W_Assess%20potential%20fraud.


'''


class TestRiskSeniorityRequirement(unittest.TestCase):

    def test(self):
        print('Commencing tests!')
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(data=test_graph_data, format='turtle')
        validator = SHACLAllocator(test_graph)
        validator.shacl_graph = Graph() # reset, so default rules don't interfere

        validator.load_extension(rules_ext='./src/extension_riskReqSeniority.ttl')
        validator.load_extension(instance_ext='./src/extension_instances.ttl')

        test_graph.add((test_graph.uri('resource:User_1'), test_graph.attribute_relation('Seniority'), test_graph.uri('Seniority:Low')))
        test_graph.add((test_graph.uri('resource:User_2'), test_graph.attribute_relation('Seniority'), test_graph.uri('Seniority:Medium')))
        test_graph.add((test_graph.uri('resource:User_3'), test_graph.attribute_relation('Seniority'), test_graph.uri('Seniority:High')))


        task_to_be_allocated = test_graph.uri('task:task-3')
        for sen_index, seniority in enumerate(['Low', 'Medium', 'High']):
            test_graph.set((test_graph.uri('LoanGoal:Existing loan takeover'), test_graph.attribute_relation('RiskClass'), test_graph.uri('RiskClass:'+seniority)))
            for res_index, resource in enumerate(['User_1', 'User_2', 'User_3']):
                test_result = validator.test_assignment(task_to_be_allocated, test_graph.uri('resource:'+resource))
                score, verdict = validator.calculate_score(test_result)
                if res_index >= sen_index:
                    assert score > 0 
                else:
                    assert score < 0 and verdict != '' 

        self.assertEqual('foo'.upper(), 'FOO')

if __name__ == '__main__':
    unittest.main()