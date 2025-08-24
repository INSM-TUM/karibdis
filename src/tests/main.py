import unittest
import datetime
# from . import context
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from rdflib import URIRef, RDF, Literal
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
        test_graph.parse(importlib.resources.path('tests', 'running_case_example.ttl'), format='turtle')

        new = self.get_deduced_triples(test_graph)

        self.assertIn((URIRef('http://example.org/Task_B_7'), BPO.partOf, URIRef('http://example.org/Case_B')), new)
        self.assertIn((URIRef('http://example.org/Task_B_7'), RDF.type, BPO.Task), new)
        self.assertNotIn((URIRef('http://example.org/Task_B_8'), BPO.partOf, URIRef('http://example.org/Case_B')), new)


    def testClosedCaseNotExtended(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.path('tests', 'running_case_example.ttl'), format='turtle')
        test_graph.add((URIRef('http://example.org/Case_B'), BPO.isClosed, Literal(True)))
        
        new = self.get_deduced_triples(test_graph)

        self.assertNotIn((URIRef('http://example.org/Task_B_7'), BPO.partOf, URIRef('http://example.org/Case_B')), new)

    def testDeclareInit(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.path('tests', 'running_case_example.ttl'), format='turtle')
        
        new_case = URIRef('http://example.org/Case_A')
        test_graph.add((new_case, RDF.type, BPO.Case))
        activity = URIRef('http://example.org/Activity_ER%20Registration')
        test_graph.add((activity, URIRef('http://infs.cit.tum.de/karibdis/declare/init'), activity))

        new = self.get_deduced_triples(test_graph)
        self.assertIn((URIRef('http://example.org/Task_A_1'), BPO.instanceOf, activity), new)

    
    def testDeclareChainResponse(self):
        test_graph = ProcessKnowledgeGraph()
        test_graph.parse(importlib.resources.path('tests', 'running_case_example.ttl'), format='turtle')
        
        new_case = URIRef('http://example.org/Case_A')
        test_graph.add((new_case, RDF.type, BPO.Case))
        activity = URIRef('http://example.org/Activity_ER%20Registration')
        test_graph.add((URIRef('http://example.org/Task_A_1'), BPO.instanceOf, activity))
        test_graph.add((URIRef('http://example.org/Task_A_1'), BPO.partOf, new_case))
        test_graph.add((URIRef('http://example.org/Task_A_1'), BPO.completedAt, Literal(datetime.datetime.now())))
        activity2 = URIRef('http://example.org/Activity_ER%20Triage')
        test_graph.add((activity, URIRef('http://infs.cit.tum.de/karibdis/declare/chainresponse'), activity2))

        new = self.get_deduced_triples(test_graph)
        self.assertIn((URIRef('http://example.org/Task_A_2'), BPO.instanceOf, activity2), new)
        


if __name__ == '__main__':
    unittest.main()