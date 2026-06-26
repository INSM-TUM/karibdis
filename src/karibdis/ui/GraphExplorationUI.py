from IPython.display import display


import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v

from karibdis.ui.ui_util import QueryBox
from karibdis.utils import *



@reacton.component
def GraphViz(graph):
    with w.VBox() as main:
        graph_viz = draw_graph(graph)
        display(graph_viz)
    return main

@reacton.component
def GraphExplorationUI(graph): # TODO don't populate until shown
    reload, set_reload = reacton.use_state(True)
    place_box, current_result, current_result_size, dirty, run_query = QueryBox(graph)
    current_graph, set_current_graph = reacton.use_state(graph)

    def update_subgraph():
        _current_graph = Graph()
        copy_namespaces(_current_graph, graph)
        _current_graph += current_result
        set_current_graph(_current_graph)
    reacton.use_effect(update_subgraph, [current_result])
    
    with w.VBox() as main:
        v.CardTitle(children='Graph Exploration')
        
        if len(current_graph.all_nodes()) < 600:
            GraphViz(current_graph)
        else:
            w.Label(value=f'Too many nodes ({len(current_graph.all_nodes())}) to visualize.')

        if not reload:
            place_box()
        else:
            w.Label(value="Reloading...")
            run_query()
            set_reload(False)
        w.Button(description="Reload Graph", on_click=lambda: set_reload(True))
    return main