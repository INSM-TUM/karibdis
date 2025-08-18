import sys
import re
from urllib.parse import quote, unquote
from rdflib.namespace import Namespace, DefinedNamespace, ClosedNamespace
from rdflib.term import URIRef
from rdflib import Graph, OWL, RDF, RDFS, Literal, BNode
import importlib.resources
from sentence_transformers import CrossEncoder, SentenceTransformer, util

BASE_URL = 'http://infs.cit.tum.de/karibdis/'
BASE_ONTOLOGY_FILE = importlib.resources.path('karibdis', 'base_ontology.ttl')

class BASE_PROCESS_ONTOLOGY(DefinedNamespace):

    _fail = True
    
    Task : URIRef
    directlyFollowedBy : URIRef
    activatedAt : URIRef
    plannedAt : URIRef
    startedAt : URIRef
    completedAt : URIRef

    Activity : URIRef
    instanceOf : URIRef

    Case : URIRef
    partOf : URIRef
    isClosed : URIRef

    Resource : URIRef
    performedBy : URIRef
    isAvailable : URIRef
    Role : URIRef
    hasRole : URIRef
    canBeExecutedBy : URIRef

    ProcessValue : URIRef
    writesValue : URIRef
    dataType : URIRef

    _NS = Namespace(BASE_URL + 'baseontology/')


flatten = lambda xs: [y for ys in xs for y in ys]

def load_ontology_namespaces(ontology_file, namespace_uri):
    g = Graph()
    g.parse(ontology_file, format="turtle")

    local_names = set(map(lambda term : str(term).replace(namespace_uri, ""), filter(lambda term: str(term).startswith(namespace_uri), flatten(list(g)))))
        
    return ClosedNamespace(namespace_uri, local_names)

def is_properly_defined(namespace, ontology_file):
    namespace_from_file = load_ontology_namespaces(ontology_file, str(namespace))
    return set(BASE_PROCESS_ONTOLOGY.__annotations__.keys()) == set(namespace_from_file._ClosedNamespace__uris.keys())

def diff_def(namespace, ontology_file):
    namespace_from_file = load_ontology_namespaces(ontology_file, str(namespace))
    ids_from_file = set(namespace_from_file._ClosedNamespace__uris.keys())
    ids_from_class = set(BASE_PROCESS_ONTOLOGY.__annotations__.keys())
    return sorted(ids_from_class - ids_from_file), sorted(ids_from_file - ids_from_class)

if not is_properly_defined(BASE_PROCESS_ONTOLOGY, BASE_ONTOLOGY_FILE):
     print(f'BASE_PROCESS_ONTOLOGY is not properly defined. Please check the ontology file. \nDiff: {diff_def(BASE_PROCESS_ONTOLOGY, BASE_ONTOLOGY_FILE)}', file=sys.stderr)

def uri_to_id(uri):
    return unquote(uri.split('/')[-1]) # TODO this assumes a specific id translation; replace

def de_urify(string):
    def replace_uri(uri_match):
        uri = uri_match.group(1)
        return '\'' + uri_to_id(uri) + '\''
    return re.sub(r"'(http://example.org.*?)'", replace_uri, string) # TODO this assumes a specific id translation; replace


def nodes_in_dist(graph, nodes, dist, filter_func=lambda x: not x.startswith(OWL) and not x.startswith(RDF) and not x.startswith(RDFS)):
    triples = set()
    for node in nodes:
        triples |= set(graph.triples((node, None, None)))
        triples |= set(graph.triples((None, None, node)))
    if dist > 1:
        neighborhood = set([x[0] for x in triples]) | set([x[2] for x in triples]) 
        neighborhood = set(filter(filter_func, neighborhood)) 
        print(neighborhood)
        triples |= nodes_in_dist(graph, neighborhood, dist-1)
    return triples

def rename_identifier(g: Graph, old_uri: URIRef, new_uri: URIRef):
    # Collect all affected triples
    to_add = []
    to_remove = []
    
    for s, p, o in g:
        if s == old_uri or o == old_uri:
            new_s = new_uri if s == old_uri else s
            new_o = new_uri if o == old_uri else o
            to_remove.append((s, p, o))
            to_add.append((new_s, p, new_o))
    
    # Apply changes
    for triple in to_remove:
        g.remove(triple)
    for triple in to_add:
        g.add(triple)
    

def copy_namespaces(graph_to, graph_from, filter_func=lambda x: True):
    for label, uri in graph_from.namespaces():
        if filter_func(uri):
            graph_to.bind(label, uri, override=True)


def namespace_string(graph):
    return graph.serialize(format='ttl').split('\n\n')[0]


from IPython.display import Markdown, display
def printmd(string):
    display(Markdown(string))

def unwrap_markdown_code(text : str):
    if text.startswith('```'):
       return '\n'.join(filter(lambda line : not line.startswith('```'), text.split('\n'))) 
    else:
        return text


def graph_annotations_properties(graph, whitelist=set(), blacklist=set()):
    annotation_properties = set(graph.subjects(predicate=RDF.type, object=OWL.AnnotationProperty))
    rdfs_annotations = {RDFS.label, RDFS.comment, RDFS.seeAlso, RDFS.subClassOf, RDF.type}
    return (annotation_properties - blacklist) | rdfs_annotations | whitelist

def textualize_graph(graph, annotation_properties=None, filter_func=None):
    
    if annotation_properties is None:
        annotation_properties = graph_annotations_properties(graph)

    #_iter_annotations = iter(annotation_properties)
    #annotation_path = next(_iter_annotations) # TODO assumes at least one Annotation property!
    #for annotation_relation in _iter_annotations:
    #    annotation_path |= annotation_relation
        
    def textualize_node_old(node):
        annotation_facts = filter(lambda triple: triple[1] in annotation_properties, graph.triples((node, None, None))) # Should be graph.triples((node, annotation_path, None)), but returned triples have weird path
        g = Graph()
        copy_namespaces(g, graph)
        g += annotation_facts
        context = '\n\n'.join(g.serialize(format='ttl').split('.\n\n')[1:]).strip() # Remove namespaces
        return node, context

    def strip_uri(uri):
        try:
            return graph.namespace_manager.qname(uri).split(':')[-1]
        except:
            return str(uri)

    def textualize_node(node):
        annotation_facts = list(filter(lambda triple: triple[1] in annotation_properties, graph.triples((node, None, None)))) # Should be graph.triples((node, annotation_path, None)), but returned triples have weird path
        context = ''
        label = next(filter(lambda triple: triple[1] == RDFS.label, annotation_facts), None)
        context = str(label[2]) if label else strip_uri(node)
        clazz = next(filter(lambda triple: triple[1] == RDF.type, annotation_facts), None)
        context += f' a {strip_uri(clazz[2])}' if clazz else ''
        for s,p,o in annotation_facts:
            if p not in [RDFS.label, RDF.type]:
                o_str = strip_uri(o).replace('\n', ' ')
                context += f'\n{strip_uri(p)}: {o_str}'
                
        return node, context

    entities = filter(lambda term: 
                      not isinstance(term, Literal) 
                      and not isinstance(term, BNode) 
                      and not term in OWL
                      and not term in RDF
                      and not term in RDFS
                      and (filter_func is None or filter_func(term)), 
                    graph.all_nodes())
    
    return dict(map(textualize_node, entities))

# def graph_alignment(addition_graph, target_graph, addition_node_filter=None, target_node_filter=None, addition_text_params={}, target_text_params={}):
def graph_alignment(addition_texts, target_texts):
    source_ids, source_texts_list = zip(*addition_texts.items())
    target_ids, target_texts_list = zip(*target_texts.items())

    # Fast BiEncoder Pre-ranking
    bi_encoder = SentenceTransformer("all-MiniLM-L6-v2")
    target_embeddings = bi_encoder.encode(target_texts_list, convert_to_tensor=True)
    source_embeddings = bi_encoder.encode(source_texts_list, convert_to_tensor=True)
    cosine_scores = util.cos_sim(source_embeddings, target_embeddings)

    # High-quality CrossEncoder re-ranking
    cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    def top_k_nodes(i, top_k=10, top_k_outer=20):
        source_id = source_ids[i]
        top_scores, top_indices = cosine_scores[i].topk(top_k_outer, sorted=True)
        top_values = [target_texts_list[index] for index in top_indices]
        ranks = cross_encoder.rank(source_texts_list[i], top_values, top_k=top_k, return_documents=True)

        # The following holds:
        #for i, rank in enumerate(ranks):
        #    assert target_texts_list[top_indices[rank['corpus_id']]] == rank['text']
        
        indices_in_collection = [top_indices[rank['corpus_id']].item() for rank in ranks]
        top_ids = [target_ids[index] for index in indices_in_collection]


        return ranks, top_ids  
    
    results = {}
    for i, source_id in enumerate(source_ids):
        print(f'{i}/{len(addition_texts)}', end='\r')
        ranks, indices_in_collection = top_k_nodes(i)
        results[source_id] = ranks, indices_in_collection

    return results


from rdflib import RDF
from rdflib.extras.external_graph_libs import rdflib_to_networkx_multidigraph
import networkx as nx
import matplotlib.pyplot as plt, matplotlib.colors
from yfiles_jupyter_graphs import GraphWidget


def color_by_type(rdf_graph):
    types = set(rdf_graph.objects(predicate=RDF.type))
    colors = map(matplotlib.colors.rgb2hex, plt.get_cmap('jet')([x / len(types) for x in range(0, len(types))]))
    color_map = dict(zip(types, colors))

    node_colors = dict()
    for node, p, typ in rdf_graph.triples((None, RDF.type, None)):
        node_colors[node] = color_map[typ]
    return node_colors


def draw_graph(graph, color_func=color_by_type):

    def edge_attrs(subject, predicate, objectt):
        return {'label' : predicate.n3(graph.namespace_manager)}

    def node_label(uri):
        return uri.n3(graph.namespace_manager)

    
    dg = rdflib_to_networkx_multidigraph(graph, edge_attrs=edge_attrs, transform_s=node_label, transform_o=node_label)
    nx.set_node_attributes(dg, values='#BBBBBB', name='color')

    for node, color in color_func(graph).items():
        dg.nodes[node_label(node)]['color'] = color

    widget = GraphWidget(graph = dg)
    widget.edge_label_mapping = 'label'
    widget.node_color_mapping = 'color'
    widget.show()