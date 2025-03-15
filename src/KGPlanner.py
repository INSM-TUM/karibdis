from rdflib import Graph, Literal, RDF, URIRef, Namespace
from ProcessKnowledgeGraph import ProcessKnowledgeGraph
from SHACLAllocator import SHACLAllocator 
from simulator import EventType
from utils import *
from datetime import timedelta




def task_id(task):
    return 'task-' + str(task.id)

def case_id(task):
    return 'case-' + str(task.case_id)

class KGPlanner:

    def __init__(self):
        self.graph = ProcessKnowledgeGraph(entity_attributes=['ApplicationType', 'LoanGoal', Keys.ACTIVITY], case_attributes=['ApplicationType', 'LoanGoal'])
        self.allocator = SHACLAllocator(self.graph)

    def plan(self, available_resources_list, unassigned_tasks_list, resource_pool):

        self.update_pool(available_resources_list, resource_pool)
        self.graph.update_availability(lambda resource_node: uri_to_id(resource_node) in available_resources_list)
        
        assignments = []
        assert set(map(lambda task: self.graph.entity_instance_node('task', task_id(task)), unassigned_tasks_list)) == self.graph.unassigned_tasks()

            
        # assign the first unassigned task to the first available resource, the second task to the second resource, etc.
        for task in self.graph.unassigned_tasks():

            _task_label = uri_to_id(next(self.graph.objects(predicate=self.graph.attribute_relation(Keys.ACTIVITY), subject=task)))
            if len(set(resource_pool[_task_label]) & set(available_resources_list)) > 1:
                _case = uri_to_id(next(self.graph.objects(predicate=self.graph.attribute_relation(Keys.CASE), subject=task)))
                print(f"\n{_case} Task: {_task_label} Available: {available_resources_list} Allowed: {set(resource_pool[_task_label]) & set(available_resources_list)}")
                
            assert set(map(lambda resource: self.graph.entity_instance_node(Keys.RESOURCE, resource), available_resources_list)) == self.graph.available_resources()
            (score, resource, reasoning) = self.allocator.get_resource(task, threshold=0) # TODO kind magic number
            if resource:
                assignments.append((next((_task for _task in unassigned_tasks_list if self.graph.entity_instance_node('task', task_id(_task)) == task)), uri_to_id(resource)))
                # if len(available_resources_list) > 1:
                  #  print(f"Assign {str(assignments[-1][0])} {assignments[-1][1]} out of {len(potential_resources)} / {len(available_resources_list)}")
                available_resources_list.remove(uri_to_id(resource))
                self.graph.handle_assignment(task, resource)
                print(f"Assigning: {uri_to_id(resource)} to {uri_to_id(task)} considering the following: \n {reasoning}")

                self.simulate_preference(task, resource)

        return assignments

    def update_pool(self, available_resources_list, resource_pool):
        self.graph.lazy_load_resources(available_resources_list, dict(), set(resource_pool.keys()), None, lambda resource, activity: resource in resource_pool[activity])

    def initialize_pool(self, resource_pool): #deprecated
        self.resource_pool = resource_pool
        resources = set().union(*resource_pool.values())
        self.graph.load_resources(resources, dict(), set(resource_pool.keys()), None, lambda resource, activity: resource in resource_pool[activity])
        self.has_initialized = True

    def report(self, event):
        
        if event.lifecycle_state == EventType.TASK_ACTIVATE:
            self.add_task(event.task)

        if event.lifecycle_state in task_lifecycle_relations:
            task_node = self.graph.entity_instance_node('task', task_id(event.task))
            timestamp = (event.initial_time + timedelta(hours=event.timestamp))
            self.graph.add((task_node, self.graph.attribute_relation(task_lifecycle_relations[event.lifecycle_state]), Literal(timestamp)))

    def add_task(self, task):
        self.graph.translate_event({Keys.CASE : case_id(task), Keys.ID : task_id(task), Keys.ACTIVITY : task.task_type} | task.data)

    def simulate_preference(self, task, resource):
        existing_preference = next(self.graph.objects(predicate=self.graph.attribute_relation('likes'), subject=resource), None)
        if not existing_preference:
            application_type = next(self.graph.objects(predicate=self.graph.attribute_relation(Keys.CASE) / self.graph.attribute_relation('ApplicationType'), subject=task))
            existing_preferent = next(self.graph.subjects(predicate=self.graph.attribute_relation('likes'), object=application_type), None)
            if not existing_preferent:
                self.graph.add((resource, self.graph.attribute_relation('likes'), application_type))
                print(f"{uri_to_id(resource)} now likes application type {uri_to_id(application_type)}")

