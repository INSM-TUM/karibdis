from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.KGProcessEngine import KGProcessEngine

class KnowledgeGraphBPMS: 

    def __init__(self, pkg=None, engine=None):
        self.pkg = pkg if pkg != None else ProcessKnowledgeGraph()
        self.engine = engine if engine != None else KGProcessEngine(self.pkg)


    def load_from_string(self, data):
        self.pkg -= self.pkg  # Clear current graph
        self.pkg.parse(data=data, format='ttl')