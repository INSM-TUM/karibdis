import os
from urllib import response
from urllib.parse import quote
import requests
from rdflib import Graph, URIRef, Literal, Namespace, OWL, RDFS, RDF, SKOS
from pathlib import Path
from collections import deque

from dotenv import load_dotenv

load_dotenv() 
API_KEY = os.environ["BIOPORTAL_API_KEY"]

SNOMED = Namespace("http://purl.bioontology.org/ontology/SNOMEDCT/")
BIOPORTAL_API_URL = "https://data.bioontology.org/ontologies/SNOMEDCT/classes/"
CONCEPT_IDS = {
    "Anti-infective" : "373249005",
    "Antibacterial" : "419241000",
    "Vancomycin": "372735009", #is_antiMRSA true, no gram negative coverage
    "Ceftriaxone": "372670001", #is_antiMRSA fale, is_gram_negative true
    "Clindamycin": "372786004", # :is_antiMRSA true ; # No gram-negative coverage
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


def retrieve_from_snomed(url, endpoint=''):
    encoded_uri = quote(str(url), safe="")
    response = requests.get(
        f"{BIOPORTAL_API_URL}{encoded_uri}/{endpoint}",
        headers={"Authorization": f"apikey token={API_KEY}"},
        timeout=30
    )
    response.raise_for_status()
    return response.json()


# Run hierarchy extraction
def main():
    base_path = Path(__file__).resolve().parent

    graph = Graph()

    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)
    graph.bind("skos", SKOS)
    graph.bind("snomed", SNOMED)

    queue = deque(str(SNOMED[concept_id]) for concept_id in CONCEPT_IDS.values())
    discovered = set(queue)

    while queue:
        concept_uri = queue.popleft()

        print(f"Retrieving parents and base info of {concept_uri}")

        base_info = retrieve_from_snomed(concept_uri)
        graph.add((URIRef(concept_uri), RDF.type, OWL.Class))
        graph.add((URIRef(concept_uri), RDFS.label, Literal(base_info["prefLabel"])))
        for definition in base_info.get("definition") or []:
            graph.add((URIRef(concept_uri), SKOS.definition, Literal(definition)))

        parents = retrieve_from_snomed(concept_uri, "parents")
        parents = parents["collection"] if isinstance(parents, dict) else parents
        for parent in parents:
            parent_uri = parent["@id"]

            graph.add((
                URIRef(concept_uri),
                RDFS.subClassOf,
                URIRef(parent_uri)
            ))

            if parent_uri not in discovered:
                discovered.add(parent_uri)
                queue.append(parent_uri)

    output_path = base_path / "snomed_hierarchy.ttl"
    graph.serialize(destination=output_path, format="turtle")
    print(f"OWL ontology saved to: {output_path}")
    print(f"Total RDF triples: {len(graph)}")


# ====== MAIN ======
if __name__ == "__main__":
    main()
