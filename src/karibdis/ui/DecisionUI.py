import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v


from ipywidgets.widgets.widget_string import LabelStyle

from karibdis.ui.ui_util import SelectionMenu
from karibdis.utils import *



@reacton.component
def DecisionUI(engine):
    decisions, set_decisions = reacton.use_state(list(engine.open_decisions()))
    def reload():
        set_decisions(list(engine.open_decisions()))

    def decision_label(decision):
        return engine.pkg.label(decision.subject)

    def make_decision_view(decision):
        return DecisionBody(engine, decision, reload)
    
    with w.VBox() as main:
        with w.HBox():
            w.Button(description="Open new case", on_click=lambda: (engine.open_new_case(), reload()))
        SelectionMenu(
            "Decisionmaking", 
            decisions, 
            set_decisions, 
            reload, 
            decision_label ,  
            make_decision_view, 
            item_equality=lambda decision_a, decision_b : (decision_a.subject == decision_b.subject) and (decision_a.predicate == decision_b.predicate),
            collection_name='Decisions'
        )
    return main

@reacton.component
def DecisionBody(engine, current_decision, reload):
    context_case = current_decision.context.get('case', None)
    context_type = current_decision.context.get('target_type', None)
    label_context = current_decision.context.get('label_context', None)
    with w.VBox(layout=w.Layout(overflow='scroll', height='60vh', width='100%')) as main:
        options, set_options = reacton.use_state([])
        reacton.use_effect(lambda: set_options(current_decision.get_top_k_results(20)), [current_decision])
        v.CardTitle(children=f' Decide {engine.pkg.label(context_type)}' + (f' for {engine.pkg.label(context_case)}' if context_case else '') + (f' {label_context}' if label_context else ''), layout=w.Layout(flex='0 0 auto'))

        for score, option, reasoning in options:
            with w.VBox(layout=w.Layout(border='solid #FAFAFA', margin='0.2%', padding='0.1%', flex='0 0 auto')):  
                v.Label(children=f'{engine.pkg.label(option)} ({score})', style=LabelStyle(font_weight='bold', width='100%'))
                for reason in reasoning:
                    w.Label(value=f'- {reason}') # TODO: Add single scores?
                w.Button(description='Confirm', on_click=lambda option=option: [engine.handle_decision(current_decision, option), reload()])
        if context_case is not None:
            w.Button(description='Close Case', on_click=lambda: [engine.close_case(context_case), reload()], layout=w.Layout(flex='0 0 auto'))