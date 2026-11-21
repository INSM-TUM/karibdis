# ====== REQUIRED INPUT FILES AND SETUP ======
# The following files must be present relative to this script:
#
# hierarchy_extractor.py
# aro.owl (Antibiotic Resistance Ontology (RDF/XML))
# card_data/
#     index-for-model-sequences.txt.gz  # CARD prevalence sequence index from CARD Prevalence, Genomes, and Variants
#     ncbi_taxonomy.json                # CARD NCBI Taxonomy name-to-TaxID data from CARD Ontology
#
# Keep the sequence index gzip-compressed. Extract the ontology and taxonomy
# files from their respective distributions and use the filenames shown above.
# Input paths are resolved relative to the script, not the working directory.
import os
import tarfile
import tempfile
from urllib.parse import quote
import requests
import rdflib
from pathlib import Path
import csv #reading CARD's tabbed index
import gzip #reading the compressed dataset
from collections import deque, defaultdict
import json

from dotenv import load_dotenv
import urllib
load_dotenv() 
API_KEY = os.environ["BIOPORTAL_API_KEY"]

SNOMED = rdflib.Namespace("http://purl.bioontology.org/ontology/SNOMEDCT/")
BIOPORTAL_ROOT = "https://data.bioontology.org"
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

ARO = rdflib.Namespace("http://purl.obolibrary.org/obo/")
EX = rdflib.Namespace("http://example.org/")
NCBITAXON = rdflib.Namespace("http://purl.bioontology.org/ontology/NCBITAXON/")

# ====== FUNCTION DEFINITIONS ======
# Retrieve the immediate parent concepts of a SNOMED CT concept via BioPortal.
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


# Retrieve concept metadata from BioPortal, including labels and definitions.
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


# Traverse the SNOMED CT ancestors of the seed concepts using bfs.
# Populate the concept metadata and child-parent relationship collections.
def collect_hierarchy(concept_uris):
    concepts = {}
    relationships = set()

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
    return concepts, relationships
    


# Convert the collected concepts and subclass relationships into an RDF graph.
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


# Identify seed concepts that descend from the SNOMED CT antibacterial concept.
def find_antibiotic_seeds(seed_uris, concepts, owl_graph):
    ANTIBACTERIAL = SNOMED["419241000"]
    antibiotics = {}

    for seed_uri in seed_uris:
        concept = rdflib.URIRef(seed_uri)

        if concept == ANTIBACTERIAL:
            continue

        ancestors = owl_graph.transitive_objects(concept, rdflib.RDFS.subClassOf) # TODO: Could be one statement (get subjects with predicate subClass* and object ANTIBACTERIAL, to set intersection)

        if ANTIBACTERIAL in ancestors:
            antibiotics[str(concept)] = concepts[str(concept)]["label"]

    return antibiotics


# Find ARO determinants with direct resistance restrictions targeting the named antibiotic.
def find_resistance_determinants(antibiotic_name, aro_graph):
    resistance_property = ARO.ARO_2000000 #confers_resistance_to_antibiotic
    matches = set()

    
    for restriction in aro_graph.subjects(
        rdflib.OWL.onProperty, resistance_property
    ):
        antibiotic = aro_graph.value(restriction, rdflib.OWL.someValuesFrom) 

        if antibiotic is None:
            continue

        label = aro_graph.value(antibiotic, rdflib.RDFS.label)

        if label is None or str(label).casefold() != antibiotic_name.casefold(): # TODO string-based matching?
            continue

        for determinant in aro_graph.subjects(rdflib.RDFS.subClassOf, restriction):
            matches.add(normalize_aro_ids(determinant))

    return matches


# Normalize ARO identifiers to the ARO:<number> format and reject invalid accessions.
def normalize_aro_ids(value):
    value = str(value).strip()

    if value.startswith("http://purl.obolibrary.org/obo/ARO_"):
        number = value.rsplit("ARO_", 1)[1]
    elif value.startswith(("ARO:", "ARO_")):
        number = value[4:]
    elif value.isdecimal():
        number = value
    else:
        raise ValueError(f"Unrecognized ARO accession: {value!r}")

    if not number.isdecimal():
        raise ValueError(f"Invalid ARO accession: {value!r}")

    return f"ARO:{number}"


# Read the compressed CARD sequence index and yield matching determinant-species pairs.
def find_determinant_microbes(index_path, aro_accessions=None):
    wanted = None if aro_accessions is None else {
        normalize_aro_ids(accession)
        for accession in aro_accessions
    }

    with gzip.open(index_path, "rt", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")

        required = {
            "aro_accession",
            "species_name"
        }

        missing = required - set(reader.fieldnames or [])

        if missing:
            raise ValueError(f"Missing columns in CARD index: {missing}")

        for row in reader:
            aro = normalize_aro_ids(row["aro_accession"])

            if wanted is not None and aro not in wanted:
                continue

            species = row["species_name"].strip()

            if species:
                yield aro, species


# Link antibiotics to bacterial species through ARO resistance determinants and CARD records.
def match_antibiotics(antibiotics, aro_graph, index_path):
    results = {
        rdflib.URIRef(uri): set()
        for uri in antibiotics
    }

    antibiotics_by_determinant = defaultdict(set)

    for antibiotic_uri, antibiotic_name in antibiotics.items():
        determinants = find_resistance_determinants(antibiotic_name, aro_graph)
        antibiotic = rdflib.URIRef(antibiotic_uri)

        for aro in determinants:
            antibiotics_by_determinant[aro].add(antibiotic)

    if antibiotics_by_determinant:
        print("\nScanning CARD sequence index")

        for aro, species in find_determinant_microbes(index_path, antibiotics_by_determinant):
            for antibiotic in antibiotics_by_determinant[aro]:
                results[antibiotic].add(species)

    return results


# Build a lookup from normalized CARD taxonomy names to sets of NCBI TaxIDs.
def load_taxonomy_lookup(taxonomy_path):
    with taxonomy_path.open(encoding="utf-8") as file:
        taxonomy = json.load(file)

    lookup = defaultdict(set)

    for entry in taxonomy:

        name = entry["name"].strip().casefold()
        taxid = entry["accession"]

        if name and taxid.isdecimal():
            lookup[name].add(taxid)

    return lookup


# Retrieve CUI and LOOM SNOMED CT mapping candidates for an NCBI TaxID.
# Collect candidates across all returned mapping pages.
def get_snomed_mappings(taxid):
    encoded_uri = quote(str(NCBITAXON[str(taxid)]), safe="")
    url = (
        f"{BIOPORTAL_ROOT}/ontologies/NCBITAXON/"
        f"classes/{encoded_uri}/mappings"
    )
    candidates = {
        "CUI": set(),
        "LOOM": set()
    }
    page = 1

    while True:
        response = requests.get(
            url,
            headers={"Authorization": f"apikey token={API_KEY}"},
            params={"page": page, "pagesize": 100},
            timeout=30
        )
        if response.status_code == 404 and page == 1:
            return None  # TaxID/mapping endpoint unavailable in BioPortal
        response.raise_for_status()
        data = response.json()
        records = data if isinstance(data, list) else data["collection"]

        for mapping in records:
            source = mapping.get("source")

            if source not in candidates:
                continue

            for concept in mapping["classes"]:
                uri = concept["@id"]

                if uri.startswith(str(SNOMED)):
                    snomed_id = uri.rsplit("/", 1)[1]

                    if snomed_id.isdecimal():
                        candidates[source].add(snomed_id)

        if isinstance(data, list) or page >= data["pageCount"]:
            return candidates
        page += 1


# Check that a SNOMED CT concept is active, labeled and has an organism semantic tag.
def is_organism(info):
    descriptions = [info.get("prefLabel") or "", *(info.get("synonym") or [])]

    return (
        info.get("obsolete") is False
        and any(text.strip(). casefold().endswith("(organism)")
            for text in descriptions)
        and bool(info.get("prefLabel"))
    )


# Resolve bacterial species to unique active SNOMED CT organism concepts via NCBI TaxIDs.
# Prefer CUI mappings, use LOOM as fallback if CUI candidates are absent, and log outcomes.
def map_microbes_to_snomed(results, taxonomy_lookup):
    species_names = set().union(*results.values())

    mapped = {}
    taxid_cache = {}

    for species in sorted(species_names):
        taxids = taxonomy_lookup.get(species.strip().casefold(), set())
        mappings = None
        source = ""
        valid = {}
        selected = ""

        if not taxids:
            status = "taxonomy_not_found"

        elif len(taxids) > 1:
            status = "ambiguous_taxonomy"

        else:
            taxid = next(iter(taxids))

            if taxid not in taxid_cache:
                mappings = get_snomed_mappings(taxid)

                # Prefer CUI, fall back on LOOM
                if mappings:
                    if mappings["CUI"]:
                        source = "CUI"
                    elif mappings["LOOM"]:
                        source = "LOOM"

                candidates = mappings[source] if source else set()

                for snomed_id in sorted(candidates):
                    info = get_base_info(str(SNOMED[snomed_id]))

                    if is_organism(info):
                        valid[snomed_id] = info["prefLabel"]

                taxid_cache[taxid] = mappings, source, valid

            mappings, source, valid = taxid_cache[taxid]

            if mappings is None:
                status = "bioportal_not_found"

            elif not source:
                status = "no_cui_or_loom_mapping"

            elif not valid:
                status = "no_active_organism_mapping"

            elif len(valid) > 1:
                status = "ambiguous_snomed"

            else:
                selected, label = next(iter(valid.items()))
                mapped[species] = (SNOMED[selected], label)
                status = "mapped"

        print(f"{species}: {selected or status}")

    return mapped


# Prepare new bacterial concepts and unique antibiotic-species pairs for RDF generation.
def prepare_resistance_relationships(owl_graph, results, mapped):
    new_microbes = {
        microbe: label
        for microbe, label in mapped.values()
        if (microbe, rdflib.RDF.type, rdflib.OWL.Class) not in owl_graph
    }
    resistance_pairs = {
        (antibiotic, mapped[species][0])
        for antibiotic, species_names in results.items()
        for species in species_names
        if species in mapped
    }
    return new_microbes, resistance_pairs


# Add bacterial classes, labels and reported resistance associations to the RDF graph.
def add_resistance_relationships(owl_graph, new_microbes, resistance_pairs):
    owl_graph.bind("snomed", SNOMED)
    owl_graph.bind("res", EX)

    property_uri = EX.hasReportedResistanceIn

    owl_graph.add((
        property_uri,
        rdflib.RDFS.label,
        rdflib.Literal("has reported resistance in")
    ))

    owl_graph.add((
        property_uri,
        rdflib.RDFS.comment,
        rdflib.Literal(
            "CARD reports sequence detections in this taxon "
            "of determinants linked to this antibiotic by ARO. "
            "This does not establish phenotypic resistance "
            "for every isolate."
        )
    ))

    # Create new bacterial concepts
    for microbe, species in new_microbes.items():
        owl_graph.add((microbe, rdflib.RDF.type, rdflib.OWL.Class))
        owl_graph.add((microbe, rdflib.RDFS.label, rdflib.Literal(species)))

    # Add resistance relationships
    for antibiotic, microbe in resistance_pairs:
        owl_graph.add((antibiotic, property_uri, microbe))

    return len(resistance_pairs)


# Run hierarchy extraction, CARD/ARO matching, SNOMED resolution and Turtle export.
def main():
    base_path = Path(__file__).resolve().parent
    aro_path = base_path / "aro.owl"
    card_data_path = base_path / "card_data"
    index_path = card_data_path / "index-for-model-sequences.txt.gz"
    taxonomy_path = card_data_path / "ncbi_taxonomy.json"

    
    if not aro_path.is_file():
        print(f'Downloading ARO ontology to {aro_path} ...')
        urllib.request.urlretrieve(f'https://data.bioontology.org/ontologies/ARO/submissions/23/download?apikey={API_KEY}', str(aro_path))

    if not card_data_path.is_dir():
        card_data_path.mkdir(parents=True, exist_ok=True)

    if not index_path.is_file():
        print(f'Downloading index file to {index_path}. This may take a while! ...')
        with tempfile.TemporaryDirectory() as tempdir:
            genomes_tar = Path(tempdir) / 'ontology-v4.0.2.tar.bz2'
            urllib.request.urlretrieve('https://card.mcmaster.ca/download/6/prevalence-v4.0.2.tar.bz2', genomes_tar)
            print(f'\tDownload complete, extracting. This may take a while! ...')
            with tarfile.open(genomes_tar, 'r:bz2') as tar:
                with open(index_path, 'wb') as f:
                    f.write(tar.extractfile(f'./{index_path.name}').read()) # Current python version doesn't seem to support path parameter for direct extraction

    if not taxonomy_path.is_file():
        print(f'Downloading taxonomy file to {taxonomy_path} ...')
        with tempfile.TemporaryDirectory() as tempdir:
            ontology_tar = Path(tempdir) / 'ontology-v4.0.2.tar.bz2'
            urllib.request.urlretrieve('https://card.mcmaster.ca/download/5/ontology-v4.0.2.tar.bz2', ontology_tar)
            with tarfile.open(ontology_tar, 'r:bz2') as tar:
                with open(taxonomy_path, 'wb') as f:
                    f.write(tar.extractfile(f'./{taxonomy_path.name}').read()) # Current python version doesn't seem to support path parameter for direct extraction

    for path in (aro_path, index_path, taxonomy_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file missing: {path}")
    taxonomy_lookup = load_taxonomy_lookup(taxonomy_path)

    seed_uris = [
        SNOMED[concept_id]
        for concept_id in CONCEPT_IDS.values()
    ]

    # ====== HIERARCHY EXTRACTION ======

    concepts, relationships = collect_hierarchy(seed_uris)
    print(f"\nTotal concepts: {len(concepts)}")
    print(f"Total subclass relationships: {len(relationships)}")

    owl_graph = owlify(concepts, relationships) # TODO: only needs owl graph going forward; can nest

    # ====== ANTIBIOTIC-MICROBE MATCHING ======

    antibiotics = find_antibiotic_seeds(seed_uris, concepts, owl_graph)
    print(f"\nFound {len(antibiotics)} antibacterial seed concepts:")

    for antibiotic_name in antibiotics.values():
        print(f" - {antibiotic_name}")

    aro_graph = rdflib.Graph()

    with (aro_path).open("rb") as file:
        aro_graph.parse(file=file, format="xml")


    results = match_antibiotics(antibiotics, aro_graph, index_path)

    # ===== SNOMED IDENTIFIER RESOLUTION ======
    
    mapped = map_microbes_to_snomed(results, taxonomy_lookup)
    total_species = len(set().union(*results.values()))
    print(f"\nMapped species: {len(mapped)}/{total_species}")
    omitted_pairs = sum(
        species not in mapped
        for species_names in results.values()
        for species in species_names
    )
    print(f"Antibiotic-species associations omitted: {omitted_pairs}")

    # ====== RDF GRAPH ENRICHMENT =======
    
    new_microbes, resistance_pairs = prepare_resistance_relationships(owl_graph, results, mapped)
    
    initial_triples = len(owl_graph)

    resistance_count = add_resistance_relationships(owl_graph, new_microbes, resistance_pairs)

    print(f"\nUnique antibiotic-species relationships: {resistance_count}")
    print(f"Additional RDF triples: {len(owl_graph) - initial_triples}")


    output_path = base_path / "snomed_extended_hierarchy.ttl"
    owl_graph.serialize(destination=output_path, format="turtle")
    print(f"OWL ontology saved to: {output_path}")
    print(f"Total RDF triples: {len(owl_graph)}")


# ====== MAIN ======
if __name__ == "__main__":
    main()
