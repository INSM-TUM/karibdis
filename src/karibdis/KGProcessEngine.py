import queue
from pyshacl import validate
from rdflib import RDF, RDFS, Literal, URIRef, Namespace
# from warnings import deprecated
from random import shuffle
from pyshacl.consts import SH_ValidationResult, SH_resultSeverity, SH_value, SH_sourceShape, SH_resultMessage, SH_Info
import numbers
import datetime

from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO, de_urify

class KGProcessEngine:
    def __init__(self, pkg):
        self.pkg = pkg
        self.event_queue = queue.Queue()
        self.deduce()

    def handle_event_root(self, event): # This needs to be called somewhere
        self.queue_event(event)
        while not self.event_queue.empty():
            self.handle_event(self.event_queue.get())

    def handle_event(self, event):
        print(event)
        if event.get('knowledge_updated', True):
            removed, added = self.deduce(event)
            if len(removed) > 0 or len(added) > 0:
                self.queue_event({'knowledge_updated': True, 'removed': removed, 'added': added})
            else:
                pass
                # TODO self.infer_decisions()

        # TODO temp
        added_tasks = list(filter(lambda triple : triple[1] == BPO.instanceOf, event.get('added', set())))
        for s, p, o in added_tasks:
            triple_to_add = (s, BPO.completedAt, Literal(datetime.datetime.now()))
            self.pkg.add(triple_to_add)
            self.queue_event({'knowledge_updated': True, 'removed': set(), 'added': {triple_to_add}})
                        

    def queue_event(self, event):
        self.event_queue.put(event)
            
    def deduce(self, event=dict()): 
        # TODO currently no optimization based on event payload
        # TODO currently only allows addition
        before = set(self.pkg)

        r = validate(self.pkg,
                        shacl_graph=self.pkg, # TODO replace with appropriate partition
                        ont_graph=None,
                        abort_on_first=False,
                        allow_infos=True,
                        allow_warnings=True,
                        meta_shacl=True,
                        advanced=True,
                        js=False,
                        debug=False,
                        inplace=True)
        removed = set()
        added = set(self.pkg) - before

        return removed, added
    
    def open_new_case(self, id=None): # TODO allow selecting case type
        if id is None:  
            num_current_case = len(set(self.pkg.subjects(object=BPO.Case, predicate=RDF.type)))
            id = URIRef(Namespace('http://example.org/')['Case_'+str(num_current_case+1)])  # TODO conceive better namespace scheme
        new_case = (id, RDF.type, BPO.Case)
        self.pkg.add(new_case)
        self.handle_event_root({'knowledge_updated': True, 'added': {new_case}, 'removed': set()})


    def close_case(self, case_node):
        to_set = (case_node, BPO.isClosed, Literal(True))
        self.pkg.add(to_set)
        # TODO clean up undecided tasks
        self.handle_event_root({'knowledge_updated': True, 'added': {to_set}, 'removed': set()}) # TODO code duplication!


    def complete_task(self, task_node):
        to_set = (task_node, BPO.completedAt, Literal(datetime.datetime.now()))
        self.pkg.add(to_set)
        self.handle_event_root({'knowledge_updated': True, 'added': {to_set}, 'removed': set()})

    
    def open_decisions(self):
        open_next_activities_query = """
            PREFIX : <http://infs.cit.tum.de/karibdis/baseontology/>

            SELECT ?task ?case
            WHERE {
                ?case a :Case .
                ?task :partOf ?case .
                FILTER NOT EXISTS { ?task :instanceOf ?any }
                FILTER NOT EXISTS {
                    ?case :isClosed true
                }
            }"""

        open_next_activities = self.pkg.query(open_next_activities_query)
        for task, case in open_next_activities:
            yield Decision(self, task, BPO.instanceOf, {'case' : case, 'target_type': BPO.Activity})
    
    def handle_decision(self, decision_to_make, decision_result):
        triple_to_add = (decision_to_make.subject, decision_to_make.predicate, decision_result)
        self.pkg.add(triple_to_add)
        self.queue_event({'knowledge_updated': True, 'added': {triple_to_add}, 'deleted': set()})
    
    def infer_decisions(self):
        open_decisions = self.open_decisions()
        for decision in open_decisions:
            decision_result = self.request_decision(decision)
            if decision_result != None:
                return decision_result# The current decision might have changed things, so rerun the whole deduction and inference
    

    def request_decision(self, decision_to_make):
        decision_result = self.try_automated_decision(decision_to_make)
        if decision_result == None:
            decision_result = self.human_decision(decision_to_make)

        if decision_result != None:
            self.handle_decision(decision_to_make, decision_result)

        return decision_result
        
    def try_automated_decision(self, decision_to_make):
        # TODO Implement logic to determine if a decision can be automated
        return None

    # @deprecated("For development purpose only")
    def random_decision(self, decision_to_make):
        import random
        import datetime
        subject, predicate, context = decision_to_make.subject, decision_to_make.predicate, decision_to_make.context
        # TODO Implement decision request logic
        decision = random.choice(list(decision_to_make.get_options()) + [None])
            
        # self.pkg.add((subject, BPO.completedAt, Literal(datetime.datetime.now())))

        return decision
    
    def human_decision(self, decision_to_make):
        print('The following options are recommended:')
        top_options = decision_to_make.get_top_k_results(k=5) # Get all options, even the ones that are not allowed
        for index, (score, option, reasoning) in enumerate(top_options):
            option_label = next(self.pkg.objects(predicate=RDFS.label, subject=option), option)
            sep = '\n -\t'
            print(f'{index}: {option_label}, score: {score}, considering: {sep}{sep.join(reasoning)}')
        print('Type the index of the option to select. Type -1 to not perform any decision.')
        selection = input()
        selected_index = int(selection) if selection != '' else 0
        if selected_index >= 0 and selected_index < len(top_options):
            selected = (score, option, reasoning) = top_options[selected_index]
            if score != float('-inf'):
                return option
            else:
                print('Warning: This option is considered a bad choice by the system. Conform (y/N)?')
                confirm = input()
                if confirm.lower() == 'y':
                    return option
                else:
                    print('Decision not confirmed.')
                    return None
        else:
            return None
        
    def open_tasks(self):
        open_tasks_query = """
            PREFIX : <http://infs.cit.tum.de/karibdis/baseontology/>

            SELECT ?task ?case
            WHERE {
                ?case a :Case .
                ?task :partOf ?case .
                ?task :instanceOf ?any .
                FILTER NOT EXISTS { ?task :completedAt ?time }
                FILTER NOT EXISTS { ?case :isClosed true}
            }"""

        open_tasks = self.pkg.query(open_tasks_query)
        for task, case in open_tasks:
            yield (task, case)
    

class Decision:
    def __init__(self, engine, subject, predicate, context):
        self.engine = engine
        self.graph_to_check = engine.pkg
        self.shacl_graph = engine.pkg # TODO replace with appropriate partition
        self.ontology = None # TODO replace with appropriate ontology partition
        self.subject = subject
        self.predicate = predicate
        self.context = context

        self.use_hypothetical = True # TODO make this configurable, e.g. via context

    # Return the top k options for the given decision as ordered list of triples (score, option, results_text)
    def get_top_k_results(self, k=-1, threshold=float('-inf')):
        verdicts = []
        options = self.get_options()
        shuffle(options)
                
        for option in options:
            test_result = self.test_option(option)
            conforms, results_graph, results_text = test_result
            # print(results_text)
            score, verdict = self.calculate_score(test_result)
            if score >= threshold:
                verdicts.append((score, option, verdict))

        verdicts.sort(reverse=True, key=lambda x : x[0]) # Only sort by score, no secondary 
        if k < 1:
            k = len(verdicts)
        return verdicts[:k]

    def get_options(self):
        target_type = self.context.get('target_type', BPO.Activity)
        if target_type == BPO.Activity:
            return list(self.engine.pkg.subjects(predicate=RDF.type, object=BPO.Activity))
        elif target_type == BPO.Resource:
            return list(self.graph_to_check.available_resources()) # TODO method currently not implemented anymore

    def calculate_score(self, test_result):
        conforms, results_graph, results_text = test_result
        
        verdict = []
        score = 0

        for result in results_graph.subjects(predicate=RDF.type, object=SH_ValidationResult):
            severity = next(results_graph.objects(predicate=SH_resultSeverity, subject=result))
            if severity == SH_Info :
                # Method A: Get value dynamically as result from query 
                value = next(results_graph.objects(predicate=SH_value, subject=result), None)
                
                # Method B: Get static value from constraint spec 
                # if value == None or not isinstance(value.toPython(), numbers.Number): # TODO remove this deprecated method B
                #   source_constraint = next(results_graph.objects(predicate=SH_sourceShape, subject=result))
                #    value = next(self.shacl_graph.objects(predicate=URIRef('http://foobar.org/value'), subject=source_constraint))# TODO magic string
                    
                score += value.toPython()
            else:
                score += float('-inf')
            message = next(results_graph.objects(predicate=SH_resultMessage, subject=result))
            verdict.append(de_urify(message))
            # print('Ah, interesting: '+message)
        return score, verdict
    
    def test_option(self, option):
        hypothetical = (
            (self.subject,
            self.predicate + ('__hypothetical' if self.use_hypothetical else ''), #TODO magic string
            option)
        )
    
        assert hypothetical not in self.graph_to_check
        try:
            self.graph_to_check.add(hypothetical)
            
            r = validate(self.graph_to_check,
                shacl_graph=self.shacl_graph,
                ont_graph=self.ontology,
                inference=None, # TODO 'both',
                abort_on_first=False,
                allow_infos=True,
                allow_warnings=True,
                meta_shacl=True,
                advanced=True,
                js=False,
                debug=False,
                focus_nodes=[self.subject])
        finally:
            self.graph_to_check.remove(hypothetical)
        
        # display(r)
        # print(results_text)
        return r