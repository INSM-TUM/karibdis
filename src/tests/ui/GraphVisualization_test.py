from types import SimpleNamespace

from IPython.display import display, Markdown 
from playwright.sync_api import Page, expect
from rdflib import Graph, Namespace
import ipywidgets as widgets

from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.ui.KnowledgeModelingUI import (ValidationView, visualize_addition_graph)


EX = Namespace("http://example.org/visualization_test/")

EXISTING_COLOR = "#BBBBBB"
ADDITION_COLOR = "#99AA00"

AB = (EX.A, EX.relatedTo, EX.B)
BC = (EX.B, EX.relatedTo, EX.C)
AC = (EX.A, EX.relatedTo, EX.C)
CD = (EX.C, EX.relatedTo, EX.D)
DE = (EX.D, EX.relatedTo, EX.E)

NODES = {EX.A, EX.B, EX.C, EX.D, EX.E}

EXISTING_TRIPLES = {AB, BC}
ADDITION_TRIPLES = {AB, AC, CD, DE}

def get_field(item, name):
    """Access a yfiles node or edge record"""
    return item[name] if isinstance(item, dict) else getattr(item, name)

def assert_graph_colors(importer, existing_nodes, existing_edges):
    graph = importer.addition_graph
    widget = visualize_addition_graph(importer)

    assert widget.node_color_mapping == "color"
    assert widget.edge_color_mapping == "edge_color"
    assert widget.edge_label_mapping == "label"
    def label(term):
        return term.n3(graph.namespace_manager)
    
    node_labels = {}
    actual_nodes = {}
    
    for node in widget.nodes:
        properties = get_field(node, "properties")
        node_label = properties.get("yf_label") or properties.get("label")
        
        assert node_label is not None
        node_labels[get_field(node, "id")] = node_label
        actual_nodes[node_label] = properties["color"]
    expected_nodes = {
        label(node): EXISTING_COLOR if node in existing_nodes else ADDITION_COLOR for node in NODES
    }
    
    assert len(widget.nodes) == len(NODES)
    assert actual_nodes == expected_nodes
    
    actual_edges = {}
    
    for edge in widget.edges:
        properties = get_field(edge, "properties")
        
        subject = node_labels[get_field(edge, "start")]
        object_ = node_labels[get_field(edge, "end")]
        predicate = properties["label"]
        
        actual_edges[(subject, predicate, object_)] = properties.get("edge_color")
        
    expected_edges = {
        (label(s), label(p), label(o)):
            EXISTING_COLOR if (s, p, o) in existing_edges else ADDITION_COLOR for s, p, o in ADDITION_TRIPLES
    }
    
    assert len(widget.edges) == len(ADDITION_TRIPLES)
    assert actual_edges == expected_edges


def test_validation_graph_colors(solara_test, page_session: Page):
    
    pkg = ProcessKnowledgeGraph()
    pkg.bind("ex", EX)
    
    addition_graph = Graph()
    addition_graph.bind("ex", EX)
    
    for triple in EXISTING_TRIPLES:
        pkg.add(triple)
    
    for triple in ADDITION_TRIPLES:
        addition_graph.add(triple)
    
    importer = SimpleNamespace(pkg=pkg, addition_graph=addition_graph,)
    
    assert BC in pkg
    assert set(addition_graph) == ADDITION_TRIPLES
    
    stages = [
        (
            "Before insertion",
            None,
            {EX.A, EX.B, EX.C},
            {AB},
        ),
        (
            "After inserting C -> D",
            CD,
            {EX.A, EX.B, EX.C, EX.D},
            {AB, CD},
        ),
        (
            "After inserting D -> E",
            DE,
            NODES,
            {AB, CD, DE},
        ),
    ]
    
    output = widgets.Output()
    display(output)
    
    for title, triple, existing_nodes, existing_edges in stages:
        if triple is not None:
            pkg.add(triple)
            assert triple in pkg
        assert set(pkg) & ADDITION_TRIPLES == existing_edges
        assert set(pkg.all_nodes()) & NODES == existing_nodes
        
        with output:
            output.clear_output(wait=True)
            display(Markdown(f"### {title}"))
            display(ValidationView(importer, lambda: None))

        expect(
            page_session.get_by_role("button", name="Accept")
        ).to_be_visible()

        assert_graph_colors(importer, existing_nodes, existing_edges)
        
        #uncomment to inspect the graphs generated in each stage in browser
        # page_session.pause()
    