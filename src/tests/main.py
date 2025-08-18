import unittest
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


if __name__ == '__main__':
    unittest.main()