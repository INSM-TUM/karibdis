import os
from urllib.parse import quote
import requests
import rdflib
from pathlib import Path
from collections import deque

API_KEY = os.environ["BIOPORTAL_API_KEY"]

SNOMED = rdflib.Namespace("http://purl.bioontology.org/ontology/SNOMEDCT/")
BIOPORTAL_API_URL = "https://data.bioontology.org/ontologies/SNOMEDCT/classes/"
CONCEPT_IDS = {
    "Anti-infective" : "373249005",
    "Antibacterial" : "419241000",
    "Vancomycin": "372735009", #is_antiMRSA true, no gram negative coverage
    "Ceftriaxone": "372670001", #is_antiMRSA fale, is_gram_negative true
    "Piperacillin": "372836004", #is_antiMRSA false, is_gram_negative true
    "Cefepime": "96048006", #not antimrsa, gram negative
    "Metrodinazole": "372602008", #not antimrsa, not gram negative
    "Anti-fungal": "373219008",
    "Fluconazole" : "387174006",
    "Echinocandin" : "373570003",
    "Bacterium" : "41146007",
    "MRSA": "115329001",
    "ECOLI": "112283007",
    "Fungus": "414561005",
    "Candida": "53326005"
 }

def get_parents(concept_uri):
    encoded_uri = quote(str(concept_uri), safe="")
    url = f"{BIOPORTAL_API_URL}{encoded_uri}/parents"
    
    response = requests.get(
        url,
        headers={"Authorization": f"apikey token={API_KEY}"},
        timeout=30
    )
    response.raise_for_status()
    
    data = response.json()
    return data["collection"] if isinstance(data, dict) else data

def get_base_info(concept_uri):
    encoded_uri = quote(str(concept_uri), safe="")
    url = f"{BIOPORTAL_API_URL}{encoded_uri}"
    
    response = requests.get(
        url,
        headers={"Authorization": f"apikey token={API_KEY}"},
        timeout=30
    )
    response.raise_for_status()
    
    return response.json()


def collect_hierarchy(concept_uris, concepts, relationships):
    queue = deque(str(concept_uri) for concept_uri in concept_uris)
    discovered = set(queue)
    
    while queue:
        concept_uri = queue.popleft()
        
        print(f"Retrieving parents and base info of {concept_uri}")
        
        base_info = get_base_info(concept_uri)
        parents = get_parents(concept_uri)
        
        concepts[concept_uri] = {
            "label": base_info["prefLabel"],
            "definitions": base_info.get("definition") or []
        }
        
        for parent in parents:
            parent_uri = parent["@id"]
            
            relationships.add((concept_uri, parent_uri))
            
            if parent_uri not in discovered:
                discovered.add(parent_uri)
                queue.append(parent_uri)

def owlify(concepts, relationships):
    graph = rdflib.Graph()
    
    graph.bind("owl", rdflib.OWL)
    graph.bind("rdfs", rdflib.RDFS)
    graph.bind("skos", rdflib.SKOS)
    
    for concept_uri, info in concepts.items():
        concept = rdflib.URIRef(concept_uri)
        
        graph.add((concept, rdflib.RDF.type, rdflib.OWL.Class))
        graph.add((concept, rdflib.RDFS.label, rdflib.Literal(info["label"])))
        
        for definition in info["definitions"]:
            graph.add((concept, rdflib.SKOS.definition, rdflib.Literal(definition)))
    
    for child_uri, parent_uri in relationships:
        graph.add((
            rdflib.URIRef(child_uri),
            rdflib.RDFS.subClassOf,
            rdflib.URIRef(parent_uri)
        ))
    
    return graph

if __name__ == "__main__":
    concepts = {} #Every concept already processed
    relationships = set() #every direct subclass relationship discovered
    
    collect_hierarchy(
        [SNOMED[concept_id] for concept_id in CONCEPT_IDS.values()],
        concepts,
        relationships
    )
    
    print(f"\nTotal concepts: {len(concepts)}")
    print(f"Total subclass relationships: {len(relationships)}")
    
    owl_graph = owlify(concepts, relationships)
    
    output_path = Path(__file__).with_name("extracted_hierarchy.ttl")
    
    owl_graph.serialize(destination = output_path, format="turtle")
    
    print(f"OWL ontology saved to: {output_path}")
    print(f"Total RDF triples: {len(owl_graph)}")


