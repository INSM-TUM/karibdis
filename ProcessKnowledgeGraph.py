from rdflib import Graph, Literal, RDF, URIRef, Namespace
from urllib.parse import quote, unquote
from utils import *
from pandas import notna

class ProcessKnowledgeGraph(Graph):
    #TODO add default attribute aliases
    def __init__(self, attribute_aliases=default_attribute_aliases, namespace=Namespace('http://example.org/'), case_attributes=set(), ignore_attributes=set(), entity_attributes=set()):
        super(ProcessKnowledgeGraph, self).__init__()
        self.namespace = namespace
        self.attribute_aliases = attribute_aliases

        self.case_attributes = set(case_attributes)
        self.ignore_attributes = set(ignore_attributes).union(set([Keys.CASE, Keys.ID])) # These two are handled differently
        self.entity_attributes = set(entity_attributes).union(set([Keys.CASE]))

        self.namespace_relations = self.namespace + 'relations/'
        self.bind('relation', self.namespace_relations, override=True)
        self.namespace_types = self.namespace + 'types/'
        self.bind('type', self.namespace_types, override=True)
         
    def type_name(self, attr : str | Keys):
        return quote(getattr(attr, 'type_name', None) or self.attribute_aliases.get(attr, (attr, attr))[0])

    def namespace_for_instances(self, etype : str | Keys):
        type_instances_namespace = self.namespace + 'instances/'+self.type_name(etype)+'s/'
        if (self.type_name(etype), URIRef(type_instances_namespace)) not in self.namespaces():
            self.bind(self.type_name(etype), type_instances_namespace, override=True)
            
        return type_instances_namespace
    
    def relationship_name(self, attr : str | Keys):
        return quote(getattr(attr, 'relationship_name', None) or self.attribute_aliases.get(attr, (attr, attr))[1])
    
    def entity_type_node(self, etype : str | Keys):
        return URIRef(self.namespace_types+self.type_name(etype))
    
    def entity_instance_node(self, etype : str | Keys, eid):
        return URIRef(self.namespace_for_instances(etype)+quote(eid))
    
    def attribute_relation(self, attr : str | Keys):
        return URIRef(self.namespace_relations+self.relationship_name(attr))
    
    def entity_triple(self, etype : str | Keys, eid):
        return (self.entity_instance_node(etype, eid), RDF.type, self.entity_type_node(etype))

    def case_tail(self, case):
        return next(iter(set(self.objects(subject=case, predicate=~self.attribute_relation(Keys.CASE))) - set(self.objects(subject=case, predicate=~self.attribute_relation(Keys.CASE) / ~self.attribute_relation(Keys.DIRECTLY_FOLLOWED_BY)))), None)

    def unassigned_tasks(self):
        return set(self.objects(predicate=~self.attribute_relation(Keys.CASE))) - set(self.subjects(predicate=self.attribute_relation('Keys.RESOURCE')))

    def available_resources(self):
        return set(self.subjects(predicate=self.attribute_relation('available'), object=Literal(True)))
        
    def valid_resources(self, task_node):
        return set(self.objects(subject=task_node, predicate=self.attribute_relation(Keys.ACTIVITY) / self.attribute_relation(Keys.CAN_BE_EXECUTED_BY))) # TODO use rule engine

    def update_availability(self, is_available=lambda resource_node: True):
        self.remove((None, self.attribute_relation('available'), None))
        for resource_node in self.subjects(predicate=RDF.type, object=self.entity_type_node(Keys.RESOURCE)):
            self.add((resource_node, self.attribute_relation('available'), Literal(is_available(resource_node))))

    def handle_assignment(self, task_node, resource_node):
        self.add((task_node, self.attribute_relation('Keys.RESOURCE'), resource_node))
        self.set_node_attribute(resource_node, 'available', Literal(False))
            
    # Can be overriden, currently assumes entities as dicts
    def get_entity_attr(self, entity, attr):
        return entity[attr]

    # Can be overriden, currently assumes entities as dicts
    def get_entity_attr_list(self, entity):
        return entity.keys()

    def is_entity_known(self, entity_node):
        # Reasoning: If the node was already added, a rdf:type relation must exist
        return (entity_node, None, None) in self

    def set_node_attribute(self, entity_node, attr, value):
        if attr in self.entity_attributes:
            attr_node = self.entity_instance_node(attr, value)
            if not self.is_entity_known(attr_node):
                self.add(self.entity_triple(attr, value))
        else:
            attr_node = Literal(value)

        attr_triple = (entity_node, self.attribute_relation(attr), attr_node)
        if attr_triple not in self:
            self.remove((entity_node, self.attribute_relation(attr), None)) # Override previous value; TODO: What about multi-value attributes?
            self.add(attr_triple)

        return attr_triple

    def translate_event(self, event):
        # Add basic node
        node = self.entity_instance_node('task', self.get_entity_attr(event, Keys.ID))
        self.add((node, RDF.type, self.entity_type_node('task')))

        # Connect to case node an case tail
        currentCase = self.get_entity_attr(event, Keys.CASE)
        case_node = self.entity_instance_node(Keys.CASE, currentCase)
        current_tail = self.case_tail(case_node)
        self.set_node_attribute(node, Keys.CASE, currentCase)
        if current_tail:
            # Connect to to preceding node
            self.add((current_tail, self.attribute_relation(Keys.DIRECTLY_FOLLOWED_BY), node))

        # Add event attributes
        for attr in self.get_entity_attr_list(event):
            value = self.get_entity_attr(event, attr)
            target = node if (attr not in self.case_attributes) else case_node
            if notna(value) and (attr not in self.ignore_attributes): 
                self.set_node_attribute(target, attr, value)

    def lazy_load_resources(self, resources, roles, activities, can_role_execute, can_resource_execute):
            # XXX check if lazy init works here
            # TODO magic strings here
        
        for activity in activities: # TODO refactor "Add if not known pattern"
            activity_node = self.entity_instance_node(Keys.ACTIVITY, activity)
            if not self.is_entity_known(activity_node):
                self.add(self.entity_triple(Keys.ACTIVITY, activity))
                
        for resource in resources:
            resource_node = self.entity_instance_node(Keys.RESOURCE, resource)
            if not self.is_entity_known(resource_node):
                self.add(self.entity_triple(Keys.RESOURCE, resource))

            # Reset direct executability
            self.remove((None, self.attribute_relation(Keys.CAN_BE_EXECUTED_BY), resource_node))
            for activity in activities:
                if can_resource_execute and (can_resource_execute(resource, activity)):
                    self.add((self.entity_instance_node(Keys.ACTIVITY, activity), self.attribute_relation(Keys.CAN_BE_EXECUTED_BY), self.entity_instance_node(Keys.RESOURCE, resource)))
        
        for role, associated_resources in roles.items():
            role_node = self.entity_instance_node(Keys.ROLE, role)
            if not self.is_entity_known(role_node):
                self.add(self.entity_triple(Keys.ROLE, role))
                
            for activity in activities:
                if can_role_execute and (can_role_execute(role, activity)):
                    self.add((self.entity_instance_node(Keys.ACTIVITY, activity), self.attribute_relation(Keys.CAN_BE_EXECUTED_BY), role_node))
            for resource in associated_resources:
                    self.add((self.entity_instance_node(Keys.RESOURCE, resource), self.attribute_relation(Keys.ROLE), role_node))