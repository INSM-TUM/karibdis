import pytest 
from rdflib import Graph, Namespace

from karibdis.KGProcessEngine import (
    AutomationStrategy,
    NeverStrategy,
    UnambiguousSingleChoiceStrategy,
    KGProcessEngine,
    Decision
)

EX = Namespace("http://example.org/test/")

TRIPLE_A = (EX.a, EX.p, EX.b)
TRIPLE_B = (EX.c, EX.p, EX.d)

@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(
        KGProcessEngine,
        "deduce",
        lambda self, event=None: (set(), set())
    )
    return KGProcessEngine(Graph())

@pytest.fixture
def decision(engine):
    return Decision(engine, EX.DecisionType, {}, [])

def make_results(scores):
    return [
        (score, option, [])
        for score, option in scores
    ]

class TestAutomationStrategies:
    
    def test_abstract_strategy(self):
        with pytest.raises(TypeError):
            AutomationStrategy()
    def test_never_strategy(self, decision):
        assert NeverStrategy().execute(decision) == []
    
    @pytest.mark.parametrize(
        "scores, x, y, expected",
        [
            ([], 0, float("-inf"), []),
            ([(5, "A")], 0, float("-inf"), ["A"]),
            ([(0, "A")], 0, float("-inf"), []),
            
            ([(5, "A"), (float("-inf"), "B")], 0, float("-inf"), ["A"]),
            
            ([(5, "A"), (2, "B")], 0, float("-inf"), []),
            
            ([(8, "A"), (2,"B"), (-1, "C")], 3, 2, ["A"]),
            
            ([(8, "A"), (5, "B")], 3, 2, []),
            
            ([(8, "A"), (2, "B")], 0, 5, ["A"]),
            
            ([(2, "A"), (-1, "B")], 0, 5, ["A"]),
            
            ([(5, "A"), (5, "B")], 0, 2, [])
        ]
    )
    def test_unambiguous_single_choice(self, decision, monkeypatch, scores, x, y, expected):
        monkeypatch.setattr(
            decision,
            "get_top_k_results",
            lambda:make_results(scores)
        )
        
        strategy = UnambiguousSingleChoiceStrategy(x=x, y=y)
        
        assert strategy.execute(decision) == expected

    def test_default_thresholds(self):
        strategy = UnambiguousSingleChoiceStrategy()
        
        assert strategy.x == 0
        assert strategy.y == float("-inf")

class TestKGProcessEngine:
    def test_default_strategy(self, engine):
        assert engine.automation_strategy is None
        
    def test_set_automation_strategy(self, engine):
        strategy = NeverStrategy()
        
        engine.set_automation_strategy(strategy)
        
        assert engine.automation_strategy is strategy
        
        strategy = UnambiguousSingleChoiceStrategy()
        
        engine.set_automation_strategy(strategy)
        
        assert engine.automation_strategy is strategy
        
        engine.set_automation_strategy(None)
        
        assert engine.automation_strategy is None
    
    def test_invalid_strategy(self, engine):
        with pytest.raises(TypeError):
            engine.set_automation_strategy("invalid")
        with pytest.raises(TypeError):
            engine.set_automation_strategy(NeverStrategy)
            
        assert engine.automation_strategy is None
    
    def test_no_automation_strategy(self, engine, decision):
        assert engine.try_automated_decision(decision) == []
        assert engine.infer_decisions() == []
    
    def test_handle_single_decision_result(self, engine, decision):
        option = (EX.OptionA, [TRIPLE_A])
        
        engine.handle_decision(decision, option)
        
        assert TRIPLE_A in engine.pkg
        assert engine.event_queue.qsize() == 1
        
        event = engine.event_queue.get_nowait()
        assert event["knowledge_updated"] is True
        assert set(event["added"]) == {TRIPLE_A}
    
    def test_handle_multiple_decision_result(self, engine, decision):
        option_a = (EX.OptionA, [TRIPLE_A])
        option_b = (EX.OptionB, [TRIPLE_B])
        
        engine.handle_decision(decision, option_a, option_b)
        
        assert TRIPLE_A in engine.pkg
        assert TRIPLE_B in engine.pkg 
        assert engine.event_queue.qsize() == 1
        
        event = engine.event_queue.get_nowait()
        
        assert set(event["added"]) == {TRIPLE_A, TRIPLE_B}
        
    def test_handle_no_decision_results(self, engine, decision):
        engine.handle_decision(decision)
        
        assert len(engine.pkg) == 0
        assert engine.event_queue.empty()
    
    def test_automate_decision(self, engine, decision):
        option_a = (EX.OptionA, [TRIPLE_A])
        option_b = (EX.OptionB, [TRIPLE_B])
        
        applied = engine.automate_decision(
            decision, [option_a, option_b]
        )
        
        assert applied == [option_a, option_b]
        assert TRIPLE_A in engine.pkg
        assert TRIPLE_B in engine.pkg
        assert engine.event_queue.qsize() == 1
    
    def test_overlapping_effects(self, engine, decision):
        option_a = (EX.OptionA, [TRIPLE_A])
        option_b = (EX.OptionB, [TRIPLE_A])
        option_c = (EX.OptionC, [TRIPLE_B])
        
        applied = engine.automate_decision(
            decision, [option_a, option_b, option_c]
        )
        
        assert applied == [option_a, option_c]
        assert set(engine.pkg) == {TRIPLE_A, TRIPLE_B}
        assert engine.event_queue.qsize() == 1
    
    def test_existing_effects(self, engine, decision):
        engine.pkg.add(TRIPLE_A)
        
        option = (EX.OptionA, [TRIPLE_A])
        
        applied = engine.automate_decision(decision, [option])
        
        assert applied == []
        assert set(engine.pkg) == {TRIPLE_A}
        assert engine.event_queue.empty()
    
    def test_infer_decision(self, engine, decision, monkeypatch):
        option_a = (EX.OptionA, [TRIPLE_A])
        option_b = (EX.OptionB, [TRIPLE_B])
        
        monkeypatch.setattr(
            decision,
            "get_top_k_results",
            lambda: make_results([
                (5, option_a),
                (float("-inf"), option_b)
            ])
        )
        
        monkeypatch.setattr(engine, "open_decisions", lambda: iter([decision]))
        
        engine.set_automation_strategy(UnambiguousSingleChoiceStrategy())
        
        applied = engine.infer_decisions()
        
        assert applied == [option_a]
        assert TRIPLE_A in engine.pkg
        assert TRIPLE_B not in engine.pkg
        assert engine.event_queue.qsize() == 1
    
    def test_infer_decision_without_selection(self, engine, decision, monkeypatch):
        monkeypatch.setattr(engine, "open_decisions", lambda: iter([decision]))
        
        engine.set_automation_strategy(NeverStrategy())
        
        assert engine.infer_decisions() == []
        assert engine.event_queue.empty()
    
    
    def test_infer_decisions_continues_if_no_effect_applied(
        self, engine, monkeypatch
    ):
        option_a = (EX.OptionA, [TRIPLE_A])
        option_b = (EX.OptionB, [TRIPLE_B])

        # The first option introduces no new knowledge.
        engine.pkg.add(TRIPLE_A)

        first_decision = Decision(
            engine, EX.DecisionType, {}, []
        )
        second_decision = Decision(
            engine, EX.DecisionType, {}, []
        )

        monkeypatch.setattr(
            first_decision,
            "get_top_k_results",
            lambda: make_results([(5, option_a)])
        )

        monkeypatch.setattr(
            second_decision,
            "get_top_k_results",
            lambda: make_results([(5, option_b)])
        )

        monkeypatch.setattr(
            engine,
            "open_decisions",
            lambda: iter([first_decision, second_decision])
        )

        engine.set_automation_strategy(
            UnambiguousSingleChoiceStrategy()
        )

        applied = engine.infer_decisions()

        assert applied == [option_b]
        assert TRIPLE_A in engine.pkg
        assert TRIPLE_B in engine.pkg
        assert engine.event_queue.qsize() == 1

        
        
                
                