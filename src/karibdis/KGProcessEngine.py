import queue
from pyshacl import validate
from rdflib import RDF, RDFS, Literal, URIRef, Namespace
# from warnings import deprecated
from random import shuffle
from pyshacl.consts import SH_ValidationResult, SH_resultSeverity, SH_value, SH_sourceShape, SH_resultMessage, SH_Info
import numbers
import datetime
from abc import ABC, abstractmethod

from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO, de_urify
from karibdis import get_logger

### ==== Abstract Strategy Class ====
class AutomationStrategy(ABC):
    @abstractmethod
    def select_options(self, decision):
        pass

class NeverStrategy(AutomationStrategy):
    def select_options(self, decision):
        return []
    
class UnambiguousSingleChoiceStrategy(AutomationStrategy):
    def __init__(self, x=0, y=float("-inf")):
        if not x > y:
            raise ValueError("x must be greater than y.")
        self.x = x
        self.y = y
    
    
    # UnambiguousSingleChoice : 
    # With parameters x,y, select {o} iff 
    # S(o) > x 
    # and S(o') <= y for all o' != o. 
    # Default x,y = (0, -∞)
    def select_options(self, decision):
        results = decision.get_top_k_results()
        
        if results:
            #get_top_k_results() sorts options from highest to lowest score
            #it's enough to check that the highest score is greater than x and the next highest score is at most y
            top_score, top_option, _ = results[0]
            
            options_above_y = (len(results) != 1 and results[1][0] > self.y)
            
            if top_score > self.x and not options_above_y:
                return [top_option]
        
        return []

class KGProcessEngine:
    def __init__(self, pkg, automation_strategy=None):
        self.pkg = pkg
        self.event_queue = queue.Queue()
        self.set_automation_strategy(automation_strategy) 
        self.deduce()

    def handle_event_root(self, event): # This needs to be called somewhere
        self.queue_event(event)
        while not self.event_queue.empty():
            self.handle_event(self.event_queue.get())

    def handle_event(self, event):
        get_logger().debug(event)
        if event.get('knowledge_updated', True):
            removed, added = self.deduce(event)
            if len(removed) > 0 or len(added) > 0:
                self.queue_event({'knowledge_updated': True, 'removed': removed, 'added': added})
            else:
                self.infer_decisions()

                
                        

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
                        meta_shacl=False, # TODO add central shape validation to decision option evaluation
                        advanced=True,
                        js=False,
                        debug=False,
                        inplace=True)
        removed = set()
        added = set(self.pkg) - before

        return removed, added

    def deduce_chained(self):
        self.handle_event_root({'knowledge_updated': True})

    
    def open_new_case(self, id=None): # TODO allow selecting case type
        if id is None:  
            num_current_case = len(set(self.pkg.subjects(object=BPO.Case, predicate=RDF.type)))
            id = URIRef(Namespace('http://example.org/')['Case_'+str(num_current_case+1)])  # TODO conceive better namespace scheme
        new_case = (id, RDF.type, BPO.Case)
        self.pkg.add(new_case)
        arrival = (id, BPO.arrivedAt, Literal(datetime.datetime.now()))
        self.pkg.add(arrival)
        self.handle_event_root({'knowledge_updated': True, 'added': {new_case, arrival}, 'removed': set()})
        return id


    def close_case(self, case_node):
        to_set = (case_node, BPO.closedAt, Literal(datetime.datetime.now()))
        self.pkg.add(to_set)
        # TODO clean up undecided tasks
        self.handle_event_root({'knowledge_updated': True, 'added': {to_set}, 'removed': set()}) # TODO code duplication!


    def complete_task(self, task_node):
        get_logger().info('Completing task '+str(task_node))
        to_set = (task_node, BPO.completedAt, Literal(datetime.datetime.now()))
        self.pkg.add(to_set)
        self.handle_event_root({'knowledge_updated': True, 'added': {to_set}, 'removed': set()})

    
    def open_decisions(self):
        decision_types = self.pkg.query('''
        SELECT ?dtype ?openDecisionQuery ?optionsQuery ?effectQuery WHERE {
            ?dtype rdf:type :DecisionType .
            ?dtype :hasDecisionInstanceQuery ?openDecisionQuery .
            ?dtype :hasDecisionOptionQuery ?optionsQuery .
            ?dtype :hasOptionEffectQuery ?effectQuery .
        }
        ''')
        for type in decision_types:
            open_decisions = self.pkg.query(type.openDecisionQuery).bindings
            for decision_instance in open_decisions:
                option_ids = self.pkg.query(type.optionsQuery, initBindings=decision_instance).bindings
                option_effects = [list(self.pkg.query(type.effectQuery, initBindings={**decision_instance, **option})) for option in option_ids]
                yield Decision(self, type.dtype, decision_instance, list(zip(option_ids, option_effects)))


    def handle_decision(self, decision_to_make, *decision_result):
        if not decision_result:
            return
        get_logger().info(f'Made decision {str(decision_to_make.decision_type)}, {str(decision_to_make.bindings)}--> {str(decision_result)}')
        # option_id, effect = decision_result
        effects = [
            triple
            for option_id, effect in decision_result
            for triple in effect
        ]
        self.pkg += effects
        self.queue_event({'knowledge_updated': True, 'added': effects, 'deleted': set()})
    
    def infer_decisions(self):
        if self.automation_strategy is None:
            return []
        
        automated_options = []
        #iterate through open decisions, determine which options should be selected, attempt automatic decision making for each one
        for decision in self.open_decisions():
            selected_options = self.automation_strategy.select_options(decision)
            
            if len(selected_options) > 0:
                self.handle_decision(decision, *selected_options)
                automated_options.extend(selected_options)
        
        #no decisions were automated, or no open decisions exist
        return automated_options
        
        
    # @deprecated("For development purpose only")
    def random_decision(self, decision_to_make):
        import random
        import datetime
        subject, predicate, context = decision_to_make.subject, decision_to_make.predicate, decision_to_make.context
        # TODO Implement decision request logic
        decision = random.choice(list(decision_to_make.get_options()) + [None])
            
        # self.pkg.add((subject, BPO.completedAt, Literal(datetime.datetime.now())))

        return decision
    
    # @deprecated("For development purpose only")
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
                FILTER NOT EXISTS { ?case :closedAt ?anytime}
            }"""

        open_tasks = self.pkg.query(open_tasks_query)
        for task, case in open_tasks:
            yield (task, case)

    def set_automation_strategy(self, strategy):
        if strategy is not None and not isinstance(strategy, AutomationStrategy):
            raise TypeError("Invalid automation strategy")
        self.automation_strategy = strategy


    
class Decision:
    def __init__(self, engine, decision_type, bindings, options):
        self.engine = engine
        self.graph_to_check = engine.pkg
        self.shacl_graph = engine.pkg # TODO replace with appropriate partition
        self.ontology = None # TODO replace with appropriate ontology partition
        self.decision_type = decision_type
        self.bindings = bindings
        self.options = options

        self.use_hypothetical = True # TODO make this configurable, e.g. via context

    # Return the top k options for the given decision as ordered list of triples (score, option, results_text)
    def get_top_k_results(self, k=-1, threshold=float('-inf')):
        verdicts = []
        options = self.get_options()
        shuffle(options)
                
        for option in options:
            score, verdict = self.evaluate_option(option)
            if score >= threshold:
                verdicts.append((score, option, verdict))

        verdicts.sort(reverse=True, key=lambda x : x[0]) # Only sort by score, no secondary 
        if k < 1:
            k = len(verdicts)
        return verdicts[:k]
    

    def get_options(self):
        return self.options # TODO revisit notion of recalculating!


    def evaluate_option(self, option):
        test_result = self.test_option(option)
        # print(results_text)
        return self.calculate_score(test_result)

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
            verdict.append(de_urify(message, self.graph_to_check))
            # print('Ah, interesting: '+message)
        return score, verdict
    
    def test_option(self, option):
        option_id, effect = option
        hypothetical = [
            (subject,
            predicate + ('__hypothetical' if self.use_hypothetical else ''), #TODO magic string
            object) 
        for subject, predicate, object in effect]
        for hypothetical_triple in hypothetical:
            assert hypothetical_triple not in self.graph_to_check
        try:
            self.graph_to_check += hypothetical # TODO allow also effects that remove things
            
            r = validate(self.graph_to_check,
                shacl_graph=self.shacl_graph,
                ont_graph=self.ontology,
                inference=None, # TODO 'both',
                abort_on_first=False,
                allow_infos=True,
                allow_warnings=True,
                meta_shacl=False, # TODO add central shape validation to decision option evaluation
                advanced=True,
                inplace=True,
                js=False,
                debug=False,
                focus_nodes=[*self.bindings.values()])
        finally:
            self.graph_to_check -= hypothetical
        
        # display(r)
        # print(results_text)
        return r