import re
from simulator import EventType
from urllib.parse import quote, unquote

def uri_to_id(uri):
    return unquote(uri.split('/')[-1]) # TODO this assumes a specific id translation; replace

def de_urify(string):
    def replace_url(uri_match):
        uri = uri_match.group(1)
        return '\'' + uri_to_id(uri) + '\''
    return re.sub(r"'(http://example.org.*?)'", replace_uri, string)
    

task_lifecycle_relations = {
    EventType.TASK_ACTIVATE : 'activatedAt',
    EventType.TASK_PLANNED : 'plannedAt',
    EventType.START_TASK : 'startedAt',
    EventType.COMPLETE_TASK : 'completedAt'
}


import enum
class Keys(enum.Enum):

    def __new__(cls, *args, **kwds):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        return obj
    
    def __init__(self, type_name, relationship_name):
        self.type_name = type_name
        self.relationship_name = relationship_name
    
    CASE = 'case', 'partOf'
    TASK = 'c', 'd'
    ACTIVITY = 'activity', 'instanceOf'
    RESOURCE = 'resource', 'performedBy'
    ROLE = 'role', 'hasRole'

    ID = None, 'id'
    DIRECTLY_FOLLOWED_BY = None, 'directlyFollowedBy'
    CAN_BE_EXECUTED_BY = None, 'canBeExecutedBy'
    

default_attribute_aliases = {
    'concept:name' : Keys.ACTIVITY,
    'case:concept:name' : Keys.CASE,
    'org:resource' : Keys.RESOURCE,
#    'OfferID' : ('offer', 'offer') #TODO
}

def copy_namespaces(graph_to, graph_from, filter_func=lambda x: True):
    for label, uri in graph_from.namespaces():
        if filter_func(uri):
            graph_to.bind(label, uri, override=True)


def namespace_string(graph):
    return graph.serialize(format='ttl').split('\n\n')[0]


from IPython.display import Markdown, display
def printmd(string):
    display(Markdown(string))


from rdflib import RDF
from rdflib.extras.external_graph_libs import rdflib_to_networkx_multidigraph
import networkx as nx
import matplotlib.pyplot as plt, matplotlib.colors
from yfiles_jupyter_graphs import GraphWidget
def draw_graph(graph):

    def edge_attrs(subject, predicate, objectt):
        return {'label' : predicate.n3(graph.namespace_manager)}

    def node_label(uri):
        return uri.n3(graph.namespace_manager)

    
    dg = rdflib_to_networkx_multidigraph(graph, edge_attrs=edge_attrs, transform_s=node_label, transform_o=node_label)
    nx.set_node_attributes(dg, values='#BBBBBB', name='color')

    types = set(graph.objects(predicate=RDF.type))
    colors = map(matplotlib.colors.rgb2hex, plt.get_cmap('jet')([x / len(types) for x in range(0, len(types))]))
    color_map = dict(zip(types, colors))

    for node, p, typ in graph.triples((None, RDF.type, None)):
        dg.nodes[node_label(node)]['color'] = color_map[typ]

    widget = GraphWidget(graph = dg)
    widget.edge_label_mapping = 'label'
    widget.node_color_mapping = 'color'
    widget.show()