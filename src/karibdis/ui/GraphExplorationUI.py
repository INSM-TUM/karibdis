from IPython.display import display


import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v

from rdflib import Graph
import threading

from karibdis.ui.ui_util import QueryBox
from karibdis.utils import *



@reacton.component
def GraphViz(graph):
    with w.VBox() as main:
        graph_viz = draw_graph(graph)
        display(graph_viz)
    return main

@reacton.component
def GraphExplorationUI(graph): 
    reload, set_reload = reacton.use_state(False)
    place_box, current_result, current_result_size, dirty, run_query = QueryBox(graph)
    current_graph, set_current_graph = reacton.use_state(Graph())

    def update_subgraph():
        _current_graph = Graph()
        copy_namespaces(_current_graph, graph)
        _current_graph += current_result or []
        set_current_graph(_current_graph)
    reacton.use_effect(update_subgraph, [current_result])

    def do_reload():
        # TODO seems like duplicate of busy with
        set_reload(True)
        run_query()
        set_reload(False)
    # See https://github.com/widgetti/reacton/blob/f92d4709e9e981a10cc3ffcead116d78eb10adfe/docs/testing.md?plain=1#L83
    reacton.use_side_effect(lambda : threading.Thread(target=do_reload).start(), [])

    
    with w.VBox() as main:
        v.CardTitle(children='Graph Exploration')
        
        if len(current_graph.all_nodes()) < 600:
            if len(current_graph.all_nodes()) > 0:
                GraphViz(current_graph)
            else: 
                w.Label(value=f'Empty Graph.')
        else:
            w.Label(value=f'Too many nodes ({len(current_graph.all_nodes())}) to visualize.')

        if not reload:
            place_box()
            w.Button(description="Reload Graph", on_click=lambda: do_reload())
        else:
            w.Label(value="Reloading...")
    return main