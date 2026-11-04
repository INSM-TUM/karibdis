import pytest
from rdflib import Literal, Namespace, RDF
from rdflib.term import Variable
from rdflib.namespace import SH
from karibdis.KGProcessEngine import KGProcessEngine, Decision, NeverStrategy, UnambiguousSingleChoiceStrategy
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph

EX = Namespace("http://example.org/test/")

@pytest.fixture
def engine():
    #Real RDF graph with a case and two shacl rules
    pkg = ProcessKnowledgeGraph()
    pkg.add((EX.Case, RDF.type, BPO.Case))
    pkg.add((EX.ScoreShape, RDF.type, SH.NodeShape))
    pkg.add((EX.ScoreShape, SH.targetNode, EX.Case))
    pkg.add((EX.ScoreShape, SH.property, EX.ScoreProperty))
    
    pkg.add((EX.ScoreProperty, RDF.type, SH.PropertyShape))
    pkg.add((EX.ScoreProperty, SH.path, EX['score__hypothetical']))
    pkg.add((EX.ScoreProperty, SH.severity, SH.Info))
    pkg.add((EX.ScoreProperty, SH.sparql, EX.ScoreConstraint))
    
    pkg.add((EX.ScoreConstraint, RDF.type, SH.SPARQLConstraint))
    pkg.add((EX.ScoreConstraint, SH.message, Literal('Option score')))
    pkg.add((EX.ScoreConstraint, SH.select, Literal("""
                                                    SELECT $this ?value
                                                    WHERE {
                                                        $this $PATH ?value .
                                                        FILTER(?value > 0)
                                                    }
                                                    """)))
    pkg.add((EX.ScoreShape, SH.property, EX.LimitProperty))
    
    # A non-informational violation disqualifies an option (score = -inf).
    pkg.add((EX.LimitProperty, RDF.type, SH.PropertyShape))
    pkg.add((EX.LimitProperty, SH.path, EX['score__hypothetical']))
    pkg.add((EX.LimitProperty, SH.maxInclusive, Literal(10)))
    pkg.add((EX.LimitProperty, SH.severity, SH.Violation))
    pkg.add((EX.LimitProperty, SH.message, Literal('Option exceeds the limit')))
    # The real constructor calls real SHACL deduction here.
    return KGProcessEngine(pkg)

#Helpers
def make_decision(engine, scores):
    options = [
        (EX[f'Option{i}'], [(EX.Case, EX.score, Literal(score))])
        for i, score in enumerate(scores)
    ]
    
    return Decision(engine, EX.DecisionType, {"case": EX.Case}, options)

def select_and_apply_options(engine, scores):
    decision = make_decision(engine, scores)
    engine.set_automation_strategy(UnambiguousSingleChoiceStrategy())
    before = set(engine.pkg)
    selected = engine.automation_strategy.select_options(decision)
    engine.handle_decision(decision, *selected)
    return selected, before

def register_test_decisions(engine, option_scores):
    graph = engine.pkg
    # open_decisions() uses ':DecisionType', so bind that prefix.
    graph.bind('', BPO)
    graph.bind('ex', EX)
    open_query = '''PREFIX : <http://infs.cit.tum.de/karibdis/baseontology/>
    PREFIX ex: <http://example.org/test/>
    SELECT ?case
    WHERE {
        ?case a :Case .
        FILTER NOT EXISTS {
            ?case ex:score ?existing .
        }
    }'''
    options_query = '''PREFIX ex: <http://example.org/test/>
    SELECT ?option WHERE { ?option a ex:DecisionOption . }'''
    effect_query = '''PREFIX ex: <http://example.org/test/>
    SELECT ?subject ?predicate ?object 
    WHERE {
        ?option ex:scoreValue ?object .
        BIND(?case AS ?subject)
        BIND(ex:score AS ?predicate)
    }'''
    graph.add((EX.DecisionType,RDF.type,BPO.DecisionType))
    graph.add((EX.DecisionType,BPO.hasDecisionInstanceQuery,Literal(open_query)))
    graph.add((EX.DecisionType,BPO.hasDecisionOptionQuery,Literal(options_query)))
    graph.add((EX.DecisionType,BPO.hasOptionEffectQuery,Literal(effect_query)))
    
    for option, score in option_scores:
        graph.add((option, RDF.type, EX.DecisionOption))
        graph.add((option, EX.scoreValue, Literal(score)))


#Tests
expect_no_verdict = (0, 0, [])
expect_5 = (5, 5, ["Option score"])
expect_neg_inf = (20, float("-inf"), ["Option score", "Option exceeds the limit"])
@pytest.mark.parametrize('value, expected_score, expected_verdict', [expect_no_verdict, expect_5, expect_neg_inf])
def test_shacl_evaluates_real_options(engine, value, expected_score, expected_verdict):
    decision = make_decision(engine, [value])
    before = set(engine.pkg)
    score, verdict = decision.evaluate_option(decision.options[0])
    assert score == expected_score
    assert set(engine.pkg) == before
    assert sorted(verdict) == sorted(expected_verdict)

@pytest.mark.parametrize('scores, x, y, expected', [
    ([5, 20], 0, float('-inf'), [EX.Option0]),
    ([5, 2], 0, float('-inf'), []),
    ([5, 2], 3, 2, [EX.Option0]),
    ([5, 5], 3, 2, []),
    ([0, 20], 0, float('-inf'), []),
    ([], 0, float('-inf'), []),
])
def test_strategy_with_actual_shacl_scores(engine, scores, x, y, expected):
    decision = make_decision(engine, scores)
    selected = UnambiguousSingleChoiceStrategy(x=x, y=y).select_options(decision)
    
    assert [option_id for option_id, _ in selected] == expected



def test_automated_option_applies_real_effect(engine):
    selected, before = select_and_apply_options(engine, [5, 20])
    expected_effect = (EX.Case, EX.score, Literal(5))
    
    assert [option_id for option_id, _ in selected] == [EX.Option0]
    assert set(engine.pkg) == before | {expected_effect}
    assert engine.event_queue.qsize() == 1
    event = engine.event_queue.get_nowait()
    assert set(event['added']) == {expected_effect}
    
def test_ambiguous_decision_does_not_apply_effects(engine):
    selected, before = select_and_apply_options(engine, [5, 2])
    
    assert selected == []
    assert set(engine.pkg) == before
    assert engine.event_queue.empty()

def test_multiple_option_effects_single_event(engine):
    decision = make_decision(engine, [])
    
    a = (EX.OptionA, [(EX.Case, EX.resultA, Literal('A'))])
    b = (EX.OptionB, [(EX.Case, EX.resultB, Literal('B'))])
    
    engine.handle_decision(decision, a, b)
    assert engine.event_queue.qsize() == 1
    
    engine.handle_event_root({"knowledge_updated": True})
    
    assert engine.event_queue.empty()
    assert a[1][0] in engine.pkg
    assert b[1][0] in engine.pkg

def test_automated_decision_inference(engine):
    register_test_decisions(engine, [(EX.OptionA, 5), (EX.OptionB, 20)])
    engine.set_automation_strategy(UnambiguousSingleChoiceStrategy())
    before = set(engine.pkg)

    automated = engine.infer_decisions()
    expected_effect = (EX.Case, EX.score, Literal(5))

    #open_decisions() returns option IDs as SPARQL variable bindings.
    assert len(automated) == 1
    option_bindings, effects = automated[0]
    assert option_bindings[Variable('option')] == EX.OptionA
    assert set(effects) == {expected_effect}

    assert set(engine.pkg) == before | {expected_effect}
    assert engine.event_queue.qsize() == 1
    event = engine.event_queue.get_nowait()
    assert event['knowledge_updated'] is True
    assert set(event['added']) == {expected_effect}
    assert engine.event_queue.empty()

@pytest.mark.parametrize('strategy', [None, NeverStrategy()], ids=['none', 'never'])
def test_disabled_automation(engine, strategy):
    register_test_decisions(engine, [(EX.OptionA, 5), (EX.OptionB, 20)])
    
    # assert len(list(engine.open_decisions())) == 1
    engine.set_automation_strategy(strategy)
    before = set(engine.pkg)
    
    assert engine.infer_decisions() == []
    assert set(engine.pkg) == before
    assert engine.event_queue.empty()    
    