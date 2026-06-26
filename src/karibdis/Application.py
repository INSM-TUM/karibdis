from abc import ABC
import ipywidgets
from IPython.display import display, clear_output


import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v

from karibdis.ui.DecisionUI import DecisionUI
from karibdis.ui.GraphExplorationUI import GraphExplorationUI
from karibdis.ui.KnowledgeModelingUI import KnowledgeModelingUI
from karibdis.ui.TaskExecutionUI import TaskExecutionUI
from karibdis.ui.ui_util import download
v.ipyvuetify.theme.dark = False




from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.utils import *
from karibdis.KnowledgeGraphBPMS import KnowledgeGraphBPMS

   



# =========================== APPLICATION SHELL ===========================
class Application(ABC):
    def __init__(self):
        pass

class JupyterApplication(ipywidgets.Box):
    def __init__(self, system=KnowledgeGraphBPMS()):
        super().__init__()
        self.system = system
        self.layout = ipywidgets.Layout(width='100%', height='99vh')

    def display(self, obj):
        for child in self.children:
            child.close()
        self.children = [obj]
        display(self)
        
    def base_view(self):
        tabs = [
            ('Knowledge Modeling', reacton.render_fixed(KnowledgeModelingUI(self.system.pkg))[0]),            
            ('Decisionmaking', reacton.render_fixed(DecisionUI(self.system.engine))[0]),
            ('Task Execution', reacton.render_fixed(TaskExecutionUI(self.system.engine))[0]),
            ('Explore Graph', reacton.render_fixed(GraphExplorationUI(self.system.pkg))[0]),
            ('System Actions', reacton.render_fixed(SystemActionsView(self.system))[0]),
        ]
        root = ipywidgets.Tab()
        root.layout = ipywidgets.Layout(width='100%', height='100%')
        root.children = [tab[1] for tab in tabs]
        for tab in root.children:
            tab.layout = ipywidgets.Layout(width='100%')
        root.titles = [tab[0] for tab in tabs]
        return root

    def run(self):
        self.display(self.base_view())

            
    class PrescriptionAndTaskUI2(ipywidgets.VBox):
        def __init__(self):
            super().__init__()
            graph = draw_graph(ProcessKnowledgeGraph())
            
            # Extra Hack. See commend in utils.py 
            with ipywidgets.Output():
                display(graph)
                clear_output()
            self.children = [ipywidgets.Label("Prescription and Task UI"), graph]




# ====================== DEBUG VIEW ===========================

@reacton.component
def SystemActionsView(system):     
    with w.VBox() as main:
        v.CardTitle(children='System Actions')
        
        def load_from_disk(files):
            file = files[0]
            system.pkg -= system.pkg  # Clear current graph
            system.pkg.parse(data=str(file.content,'utf-8'), format='ttl')

        def save_to_disk():
            system.save_to_disk()
            print('Saved PKG to disk.')

        w.FileUpload(
            description = 'Load PKG from Disk',
            accept='.ttl',
            on_accept=lambda **args: print(args),
            multiple=False,
            on_value=load_from_disk
        )
        display(download(system.pkg.serialize(format='ttl'), 'Download PKG', filename='pkg.ttl'))
    return main
