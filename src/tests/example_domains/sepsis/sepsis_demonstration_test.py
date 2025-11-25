
import os
import importlib.resources
from pathlib import Path


import pm4py
from pm4py import discover_declare
from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef

from karibdis.KnowledgeImporter import ExistingOntologyImporter, TextualImporter
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS
from karibdis.KnowledgeImporter import SimpleEventLogImporter
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO

statement_import_fixture = [
"""```turtle
log:ProcessValue_CRP a :ProcessValue ;
    rdfs:label "C-reactive protein" ;
    rdfs:comment "The mg of C-reactive protein per liter of blood in a blood test." .
```""", 
"""```turtle
log:ProcessValue_LacticAcid a :ProcessValue ;
    rdfs:label "Lactic Acid" ;
    rdfs:comment "Measures the amount of lactic acid in a blood test." .
```""", 
"""```turtle
log:ProcessValue_Leucocytes a :ProcessValue ;
    rdfs:label "Leucocytes" ;
    rdfs:comment "The number of white blood cells in a blood test." .
```""", 
"""```turtle
log:ProcessValue_Hypoxie a :ProcessValue ;
    rdfs:label "Hypoxie" ;
    rdfs:comment "Whether hypoxia has been detected for the patient. " .
```"""
]

valid_alignment = [(URIRef('http://www.semanticweb.org/zchero/ontologies/2023/11/SepsisOntology#Leukocyte_Count'), OWL.sameAs,
  URIRef('http://example.org/ProcessValue_Leucocytes')),
 (URIRef('http://www.semanticweb.org/zchero/ontologies/2023/11/SepsisOntology#C-Reactive_Protein'), OWL.sameAs,
  URIRef('http://example.org/ProcessValue_CRP')),
 (URIRef('http://www.semanticweb.org/zchero/ontologies/2023/11/SepsisOntology#Lactate'), OWL.sameAs,
  URIRef('http://example.org/ProcessValue_LacticAcid')),
 (URIRef('http://www.semanticweb.org/zchero/ontologies/2023/11/SepsisOntology#Hypoxia'), OWL.sameAs,
  URIRef('http://example.org/ProcessValue_Hypoxie'))]


from langchain_core.runnables import Runnable
from langchain_core.messages import BaseMessage



class MockLLM(Runnable):
    def __init__(self, responses):
        self.responses = responses
        self.index = 0

    def generate(self, prompt=None):
        if self.index < len(self.responses):
            response = self.responses[self.index]
            self.index += 1
            return response
        return ""

    def invoke(self, input, config, **kwargs):
        # input.messages
        return BaseMessage(content=self.generate(), type='')
    



def test_sepsis_demonstration():
    bpms = KnowledgeGraphBPMS(ProcessKnowledgeGraph())
    engine = bpms.engine
    pkg = bpms.pkg
    example_domains = os.path.abspath(importlib.resources.files('karibdis').joinpath('../../example_domains'))
    mock_llm = MockLLM([
        *statement_import_fixture
    ])

    log = pm4py.read_xes(os.path.join(example_domains, 'sepsis/Sepsis Cases - Event Log.xes'))
    event_log_importer = SimpleEventLogImporter(pkg=pkg, ignore_columns=['Infusion'], attribute_aliases={'org:group' : BPO.Resource,})
    event_log_importer.import_event_log_entities(log=log)
    _declare = discover_declare(log, allowed_templates=['init', 'chainresponse', 'exactly_one'], min_support_ratio=0.8, min_confidence_ratio=0.8)
    _declare['exactly_one']['LacticAcid'] = False
    event_log_importer.import_declare(_declare)
    # Skip Alignment
    event_log_importer.load()
    assert URIRef('http://example.org/Activity_ER%20Triage') in pkg.subjects(RDF.type, BPO.Activity)
    assert (URIRef('http://example.org/Activity_ER%20Triage'), URIRef('http://infs.cit.tum.de/karibdis/declare/chainresponse'), URIRef('http://example.org/Activity_ER%20Sepsis%20Triage')) in pkg

    text_importer = TextualImporter(pkg, mock_llm)
    text = Path(example_domains).joinpath('sepsis/text_input.txt').read_text()
    for line in text.splitlines():
        text_importer.import_content_from_statement(line)
    # Skip Alignment
    text_importer.load()
    assert (URIRef('http://example.org/ProcessValue_CRP'), RDFS.comment, Literal('The mg of C-reactive protein per liter of blood in a blood test.')) in pkg

    sepon = Graph().parse(os.path.join(example_domains, 'sepsis/SEPON.ttl'), format='turtle')
    filter_query = Path(example_domains).joinpath('sepsis/filter_sepon_ontology.sparql').read_text()
    sepon_filtered = sepon.query(filter_query)
    existing_ontology_importer = ExistingOntologyImporter(pkg)
    existing_ontology_importer.accept_filtered_result(sepon_filtered, sepon)
    existing_ontology_importer.apply_alignment(valid_alignment)  # TODO mock calling actual alignment
    existing_ontology_importer.load()
    assert (URIRef('http://example.org/ProcessValue_Leucocytes'), RDFS.subClassOf, URIRef('http://www.semanticweb.org/zchero/ontologies/2023/11/SepsisOntology#Paediatric_Sepsis_Diagnostic_Biomarker')) in pkg

    mondo = Graph()
    mondo.parse('http://purl.obolibrary.org/obo/mondo/mondo-simple.owl', format='xml')
    existing_ontology_importer_mondo = ExistingOntologyImporter(pkg)
    filter_query_mondo = Path(example_domains).joinpath('sepsis/filter_mondo_ontology.sparql').read_text()
    mondo_filtered = mondo.query(filter_query_mondo)
    existing_ontology_importer_mondo.accept_filtered_result(mondo_filtered, mondo)
    # Skip alignment
    existing_ontology_importer_mondo.load()
    assert (URIRef('http://purl.obolibrary.org/obo/MONDO_0005015'), RDFS.label, Literal('diabetes mellitus')) in pkg

    new_knowledge = Graph().parse(os.path.join(example_domains, 'sepsis/additional_knowledge.ttl'), format='turtle')
    pkg += new_knowledge
    
    engine.deduce()