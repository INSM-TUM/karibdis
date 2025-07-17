import re
from urllib.parse import quote, unquote
from rdflib.namespace import Namespace, DefinedNamespace
from rdflib.term import URIRef

BASE_URL = 'http://infs.cit.tum.de/karibdis/baseontology/'

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

    Resource : URIRef
    performedBy : URIRef
    isAvailable : URIRef
    Role : URIRef
    hasRole : URIRef
    canBeExecutedBy : URIRef

    ProcessValue : URIRef
    writesValue : URIRef
    dataType : URIRef

    _NS = Namespace(BASE_URL)


def uri_to_id(uri):
    return unquote(uri.split('/')[-1]) # TODO this assumes a specific id translation; replace

def de_urify(string):
    def replace_uri(uri_match):
        uri = uri_match.group(1)
        return '\'' + uri_to_id(uri) + '\''
    return re.sub(r"'(http://example.org.*?)'", replace_uri, string) # TODO this assumes a specific id translation; replace



    

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