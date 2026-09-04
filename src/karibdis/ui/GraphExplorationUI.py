import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v

from rdflib import Graph

from karibdis.ui.ui_util import QueryBox, use_busy, BusyOverlay, GraphViz
from karibdis.utils import *



@reacton.component
def GraphExplorationUI(graph):
    place_box, current_result, current_result_size, dirty, run_query = QueryBox(graph)
    current_graph, set_current_graph = reacton.use_state(Graph())
    is_busy, be_busy_with = use_busy()

    def update_subgraph():
        _current_graph = Graph()
        copy_namespaces(_current_graph, graph)
        _current_graph += current_result or []
        set_current_graph(_current_graph)
    reacton.use_effect(update_subgraph, [current_result])

    reacton.use_effect(lambda: be_busy_with(run_query), [])

    def render_view():
        with w.VBox():    
            v.CardTitle(children='Graph Exploration')
            GraphViz(current_graph)
            place_box()
            w.Button(description="Reload Graph", on_click=lambda: be_busy_with(run_query))
            
    with w.VBox() as main:
        BusyOverlay(is_busy, render_view, be_busy_with=be_busy_with)
    return main
