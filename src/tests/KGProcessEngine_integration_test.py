import pytest
from rdflib import Graph, Literal, Namespace, RDF
from rdflib.namespace import SH
from karibdis.KGProcessEngine import KGProcessEngine, Decision, UnambiguousSingleChoiceStrategy
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO

EX = Namespace("http://example.org/test/")

@pytest.fixture
def engine():
    #Real RDF graph with a case and two shacl rules
    graph = Graph()
    graph.add((EX.Case, RDF.type, EX.CaseType))
    graph.add((EX.ScoreShape, RDF.type, SH.NodeShape))
    graph.add((EX.ScoreShape, SH.targetNode, EX.Case))
    graph.add((EX.ScoreShape, SH.property, EX.ScoreProperty))
    
    # Informational violations add the proposed value to the option score.
    graph.add((EX.ScoreProperty, RDF.type, SH.PropertyShape))
    graph.add((EX.ScoreProperty, SH.path, EX['score__hypothetical']))
    graph.add((EX.ScoreProperty, SH.maxInclusive, Literal(0)))
    graph.add((EX.ScoreProperty, SH.severity, SH.Info))
    graph.add((EX.ScoreProperty, SH.message, Literal('Option score')))
    graph.add((EX.ScoreShape, SH.property, EX.LimitProperty))
    
    # A non-informational violation disqualifies an option (score = -inf).
    graph.add((EX.LimitProperty, RDF.type, SH.PropertyShape))
    graph.add((EX.LimitProperty, SH.path, EX['score__hypothetical']))
    graph.add((EX.LimitProperty, SH.maxInclusive, Literal(10)))
    graph.add((EX.LimitProperty, SH.severity, SH.Violation))
    graph.add((EX.LimitProperty, SH.message, Literal('Option exceeds the limit')))
    # The real constructor calls real SHACL deduction here.
    return KGProcessEngine(graph)

def make_decision(engine, scores):
    options = [
        (EX[f'Option{i}'], [(EX.Case, EX.score, Literal(score))])
        for i, score in enumerate(scores)
    ]
    
    return Decision(engine, EX.DecisionType, {"case": EX.Case}, options)

@pytest.mark.parametrize('value, expected_score', [(0, 0), (5, 5), (20, float('-inf'))])
def test_shacl_evaluates_real_options(engine, value, expected_score):
    decision = make_decision(engine, [value])
    before = set(engine.pkg)
    score, verdict = decision.evaluate_option(decision.options[0])
    assert score == expected_score
    assert set(engine.pkg) == before
    if value!= 0:
        assert verdict

@pytest.mark.parametrize('scores, x, y, expected', [
    ([5, 20], 0, float('-inf'), EX.Option0),
    ([5, 2], 0, float('-inf'), None),
    ([5, 0], 0, 0, EX.Option0),
    ([5, 2], 3, 2, EX.Option0),
    ([5, 5], 0, 2, None),
    ([0, 20], 0, float('-inf'), None),
    ([], 0, float('-inf'), None),
])
def test_strategy_with_actual_shacl_scores(engine, scores, x, y, expected):
    decision = make_decision(engine, scores)
    before = set(engine.pkg)
    selected = UnambiguousSingleChoiceStrategy(x=x, y=y).execute(decision)
    
    assert [option_id for option_id, _ in selected] == ([] if expected is None else [expected])
    assert set(engine.pkg) == before

def test_automated_option_applies_real_effect(engine):
    decision = make_decision(engine, [5, 20])
    engine.set_automation_strategy(UnambiguousSingleChoiceStrategy())
    selected_options = engine.try_automated_decision(decision)
    applied = engine.automate_decision(decision, selected_options)
    
    assert [option_id for option_id, _ in applied] == [EX.Option0]
    assert (EX.Case, EX.score, Literal(5)) in engine.pkg
    assert (EX.Case, EX.score, Literal(20)) not in engine.pkg
    assert (EX.Case, EX["score__hypothetical"], Literal(5)) not in engine.pkg
    assert engine.event_queue.qsize() == 1
    event = engine.event_queue.get_nowait()
    assert set(event['added']) == {(EX.Case, EX.score, Literal(5))}
    
def test_ambiguous_decision_does_not_apply_effects(engine):
    decision = make_decision(engine, [5, 2])
    engine.set_automation_strategy(UnambiguousSingleChoiceStrategy())
    before = set(engine.pkg)
    selected = engine.try_automated_decision(decision)
    
    assert selected == []
    assert engine.automate_decision(decision, selected) == []
    assert set(engine.pkg) == before
    assert engine.event_queue.empty()

def test_multiple_option_effects_single_event(engine):
    decision = make_decision(engine, [])
    
    a = (EX.OptionA, [(EX.Case, EX.resultA, Literal('A'))])
    b = (EX.OptionB, [(EX.Case, EX.resultB, Literal('B'))])
    
    assert engine.automate_decision(decision, [a, b]) == [a, b]
    assert engine.event_queue.qsize() == 1
    
    engine.handle_event_root({"knowledge_updated": True})
    
    assert engine.event_queue.empty()
    assert a[1][0] in engine.pkg
    assert b[1][0] in engine.pkg



def test_sparql_decision_discovery_and_event_loop(engine):
    graph = engine.pkg
    # open_decisions() uses ':DecisionType', so bind that prefix.
    graph.bind('', BPO)
    graph.bind('ex', EX)
    open_query = '''PREFIX ex: <http://example.org/test/>
SELECT ?case WHERE { ?case a ex:CaseType . FILTER NOT EXISTS { ?case ex:score ?existing . } }'''
    options_query = '''PREFIX ex: <http://example.org/test/>
SELECT ?option WHERE { ?option a ex:DecisionOption . }'''
    effect_query = '''PREFIX ex: <http://example.org/test/>
SELECT ?subject ?predicate ?object WHERE {
  ?option ex:scoreValue ?object .
  BIND(?case AS ?subject)
  BIND(ex:score AS ?predicate)
}'''
    graph.add((EX.DecisionType,RDF.type,BPO.DecisionType))
    graph.add((EX.DecisionType,BPO.hasDecisionInstanceQuery,Literal(open_query)))
    graph.add((EX.DecisionType,BPO.hasDecisionOptionQuery,Literal(options_query)))
    graph.add((EX.DecisionType,BPO.hasOptionEffectQuery,Literal(effect_query)))
    for name, score in [(EX.OptionA, 5), (EX.OptionB, 20)]:
        graph.add((name,RDF.type,EX.DecisionOption))
        graph.add((name,EX.scoreValue,Literal(score)))

    ds=list(engine.open_decisions())
    assert len(ds)==1