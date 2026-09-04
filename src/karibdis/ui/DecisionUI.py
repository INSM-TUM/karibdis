import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v


from ipywidgets.widgets.widget_string import LabelStyle

from karibdis.ui.ui_util import SelectionMenu, use_be_busy
from karibdis.utils import *



@reacton.component
def DecisionUI(engine):
    decisions, set_decisions = reacton.use_state(list(engine.open_decisions()))
    def reload():
        set_decisions(list(engine.open_decisions()))

    def decision_label(decision):
        return engine.pkg.label(decision.bindings.get('task', None)) # TODO assumptions XXX

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
            item_equality=lambda decision_a, decision_b : (decision_a.decision_type == decision_b.decision_type) and (decision_a.bindings == decision_b.bindings) and (decision_a.options == decision_b.options),
            collection_name='Decisions'
        )
    return main

@reacton.component
def DecisionBody(engine, current_decision, reload):
    _, be_busy_with = use_be_busy()
    context_case = current_decision.bindings.get('case', None) # TODO assumptions XXX
    context_type = current_decision.decision_type
    label_context = current_decision.bindings.get('activity', None) # TODO assumptions XXX

    options, set_options = reacton.use_state([])

    def load_options():
        set_options([])
        be_busy_with(lambda: current_decision.get_top_k_results(20), on_done=lambda r: set_options(r or []))
    reacton.use_effect(load_options, [current_decision])

    with w.VBox(layout=w.Layout(overflow='scroll', height='60vh', width='100%')) as main:
        v.CardTitle(children=f' {engine.pkg.label(context_type)}' + (f' for {engine.pkg.label(context_case)}' if context_case else '') + (f' {label_context}' if label_context else ''), layout=w.Layout(flex='0 0 auto'))

        for score, option, reasoning in options:
            with w.VBox(layout=w.Layout(border='solid #FAFAFA', margin='0.2%', padding='0.1%', flex='0 0 auto')):
                v.Label(children=f'{", ".join([str(engine.pkg.label(v[-1])) for v in option[-1]])} ({score})', style=LabelStyle(font_weight='bold', width='100%')) # Could use option id bindings instead
                for reason in reasoning:
                    w.Label(value=f'- {reason}') # TODO: Add single scores?
                w.Button(
                    description='Confirm',
                    on_click=lambda option=option: be_busy_with(
                        lambda: engine.handle_decision(current_decision, option),
                        on_done=lambda _: reload(),
                    ),
                )
        if context_case is not None:
            w.Button(
                description='Close Case',
                on_click=lambda: be_busy_with(lambda: engine.close_case(context_case), on_done=lambda _: reload()),
                layout=w.Layout(flex='0 0 auto'),
            )