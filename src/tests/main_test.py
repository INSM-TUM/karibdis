import unittest
import datetime
# from . import context
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.KGProcessEngine import KGProcessEngine
from rdflib import Graph, URIRef, RDF, Literal
import importlib.resources
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO

from pyshacl import validate



class TestDefaultDeductions(unittest.TestCase):

    def get_deduced_triples(self, graph):
        before = set(graph)

        r = validate(graph, # TODO replace with appropriate deduction function once implemented
                        shacl_graph=graph,
                        ont_graph=None,
                        abort_on_first=False,
                        allow_infos=True,
                        allow_warnings=True,
                        meta_shacl=True,
                        advanced=True,
                        js=False,
                        debug=False,
                        inplace=True)

        return set(graph) - before

    def testOpenStaleCaseExtended(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.files('tests').joinpath('running_case_example.ttl'), format='turtle')

        new = self.get_deduced_triples(test_graph)

        self.assertIn((URIRef('http://example.org/Task_B_7'), BPO.partOf, URIRef('http://example.org/Case_B')), new)
        self.assertIn((URIRef('http://example.org/Task_B_7'), RDF.type, BPO.Task), new)
        self.assertNotIn((URIRef('http://example.org/Task_B_8'), BPO.partOf, URIRef('http://example.org/Case_B')), new)


    def testClosedCaseNotExtended(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.files('tests').joinpath('running_case_example.ttl'), format='turtle')
        test_graph.add((URIRef('http://example.org/Case_B'), BPO.isClosed, Literal(True)))
        
        new = self.get_deduced_triples(test_graph)

        self.assertNotIn((URIRef('http://example.org/Task_B_7'), BPO.partOf, URIRef('http://example.org/Case_B')), new)

    def testDeclareInit(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.files('tests').joinpath('running_case_example.ttl'), format='turtle')
        
        new_case = URIRef('http://example.org/Case_A')
        test_graph.add((new_case, RDF.type, BPO.Case))
        activity = URIRef('http://example.org/Activity_ER%20Registration')
        test_graph.add((activity, URIRef('http://infs.cit.tum.de/karibdis/declare/init'), activity))

        new = self.get_deduced_triples(test_graph)
        self.assertIn((URIRef('http://example.org/Task_A_1'), BPO.instanceOf, activity), new)

    
    def testDeclareChainResponse(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.files('tests').joinpath('running_case_example.ttl'), format='turtle')
        
        new_case = URIRef('http://example.org/Case_A')
        test_graph.add((new_case, RDF.type, BPO.Case))
        activity = URIRef('http://example.org/Activity_ER%20Registration')
        test_graph.add((URIRef('http://example.org/Task_A_1'), BPO.instanceOf, activity))
        test_graph.add((URIRef('http://example.org/Task_A_1'), BPO.partOf, new_case))
        test_graph.add((URIRef('http://example.org/Task_A_1'), BPO.completedAt, Literal(datetime.datetime.now())))
        activity2 = URIRef('http://example.org/Activity_ER%20Triage')
        test_graph.add((activity, URIRef('http://infs.cit.tum.de/karibdis/declare/chainresponse'), activity2))
        activity3 = URIRef('http://example.org/Activity_ER%20Triage')
        test_graph.add((activity2, URIRef('http://infs.cit.tum.de/karibdis/declare/chainresponse'), activity3))

        new = self.get_deduced_triples(test_graph)
        self.assertIn((URIRef('http://example.org/Task_A_2'), BPO.instanceOf, activity2), new)
        test_graph.add((URIRef('http://example.org/Task_A_2'), BPO.completedAt, Literal(datetime.datetime.now())))
        new = self.get_deduced_triples(test_graph)
        self.assertIn((URIRef('http://example.org/Task_A_3'), BPO.instanceOf, activity3), new)


    def testDeclareExactlyOnce(self):
        test_graph = ProcessKnowledgeGraph()
        engine = KGProcessEngine(test_graph)
        once_activity = URIRef('http://example.org/Activity_Once')
        test_graph.add((once_activity, BPO.instanceOf, BPO.Activity))
        test_graph.add((once_activity, URIRef('http://infs.cit.tum.de/karibdis/declare/exactly_one'), once_activity))
        also_once_activity = URIRef('http://example.org/Activity_Also_Once')
        test_graph.add((also_once_activity, BPO.instanceOf, BPO.Activity))
        test_graph.add((also_once_activity, URIRef('http://infs.cit.tum.de/karibdis/declare/exactly_one'), also_once_activity))
        any_activity = URIRef('http://example.org/Activity_Any')
        test_graph.add((any_activity, BPO.instanceOf, BPO.Activity))
        engine.open_new_case()
        engine.deduce() # Creates new task

        decision = next(engine.open_decisions())
        # Activities still have to be executed
        self.assertGreater(decision.evaluate_option(once_activity)[0], decision.evaluate_option(any_activity)[0])
        self.assertGreater(decision.evaluate_option(also_once_activity)[0], decision.evaluate_option(any_activity)[0])

        engine.handle_decision(decision, once_activity)
        engine.complete_task(next(engine.open_tasks())[0])
        decision = next(engine.open_decisions())
        # One activity has been executed already
        self.assertGreater(decision.evaluate_option(any_activity)[0], decision.evaluate_option(once_activity)[0])
        self.assertGreater(decision.evaluate_option(also_once_activity)[0], decision.evaluate_option(any_activity)[0])


    def testLastCompleted(self):
        test_graph = ProcessKnowledgeGraph()
        engine = KGProcessEngine(test_graph)
        activity = URIRef('http://example.org/Activity_A')
        test_graph.add((activity, BPO.instanceOf, BPO.Activity))

        case = engine.open_new_case()
        engine.deduce() # Creates new task
        engine.handle_decision(next(engine.open_decisions()), activity)
        engine.complete_task(next(engine.open_tasks())[0])
        engine.deduce() # Creates new task
        engine.handle_decision(next(engine.open_decisions()), activity)
        second_task = next(engine.open_tasks())[0]
        engine.complete_task(second_task)


        testURI = URIRef('http://example.org/lastCompleted')
        assertion_graph = Graph().parse(data='''
            @prefix : <http://infs.cit.tum.de/karibdis/baseontology/> .
            @prefix ex: <http://infs.cit.tum.de/karibdis/tests/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rules: <http://infs.cit.tum.de/karibdis/rules/> .
                                        
            ex:TestLastCompleted a sh:NodeShape ;
                sh:targetClass :Case ;
                sh:rule [
                    a sh:SPARQLRule ;
                    sh:construct """
                        CONSTRUCT {
                            ?task <'''+str(testURI)+'''> $this .
                        } WHERE {
                            BIND (rules:lastCompleted($this) AS ?task) .
                        }
                    """ ;
                ] .
        ''', format='ttl')
        test_graph += assertion_graph
        engine.deduce()
        self.assertIn((second_task, testURI, case), test_graph)
        

        


if __name__ == '__main__':
    unittest.main()