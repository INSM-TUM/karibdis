
import threading


import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v

from karibdis.ProcessKnowledgeGraph import ProcessKnowledgeGraph
from karibdis.ui.ui_util import SelectionMenu
from karibdis.utils import *
from rdflib import Literal, RDFS, XSD
from rdflib.paths import ZeroOrMore
from karibdis.utils import BASE_PROCESS_ONTOLOGY as BPO
from dataclasses import dataclass


@reacton.component
def TaskExecutionUI(engine): 
    tasks, set_tasks = reacton.use_state(list(engine.open_tasks()))
    def reload():
        set_tasks(list(engine.open_tasks()))

    def task_label(task):
        return engine.pkg.label(task[0])

    def make_task_view(task):
        return TaskBody(engine, task, reload)
    
    with w.VBox() as main:
        with w.HBox():
            w.Button(description="Open new case", on_click=lambda: (engine.open_new_case(), reload()))
        SelectionMenu(
            "Task Execution", 
            tasks, 
            set_tasks, 
            reload, 
            task_label ,  
            make_task_view,
            collection_name='Tasks'
        )
    return main

@reacton.component
def TaskBody(engine, current_task_case, reload):
    
    pkg = engine.pkg

    current_task, current_case = current_task_case
    current_task_ref = reacton.use_ref(None)
    current_task_ref.current = current_task

    current_case_ref = reacton.use_ref(None)  
    current_case_ref.current = current_case
   
    pv_values, set_pv_values = reacton.use_state({})
    pv_values_ref = reacton.use_ref({})
    pv_values_ref.current = pv_values

    focus_attr_ref = reacton.use_ref(None)

    def load_initial_values():
        activity = next(pkg.objects(predicate=BPO.instanceOf, subject=current_task), None)
        initial = {}
        for pv in pkg.objects(subject=activity, predicate=BPO.writesValue):
            existing = _load_existing_values(pkg, current_case, pv)
            meta = get_attr(pkg, pv)
            initial[pv] = existing if existing else [EMPTY_ENTITY if meta.is_entity else _compute_default(meta)]
        set_pv_values(initial)
    reacton.use_effect(load_initial_values, [current_task_case])

    def add_pv_to_form(pv):
        if pv not in pv_values_ref.current:
            meta = get_attr(pkg, pv)
            existing = _load_existing_values(pkg, current_case, pv)
            new_vals = existing if existing else [EMPTY_ENTITY if meta.is_entity else _compute_default(meta)]
            if not meta.is_entity and meta.attr_type != XSD.boolean:
                focus_attr_ref.current = pv
            set_pv_values({**pv_values_ref.current, pv: new_vals})
                        
    # --- Handlers ---
    def _make_handlers():
        def on_submit_click():
            for pv, vals in pv_values_ref.current.items():
                meta = get_attr(pkg, pv)
                for ev in list(pkg.objects(subject=current_case_ref.current, predicate=pv)):
                    pkg.remove((current_case_ref.current, pv, ev))
                for val in vals:
                    if val is not None and val != EMPTY_ENTITY:
                        pkg.add((current_case_ref.current, pv, val if meta.is_entity else Literal(val, datatype=meta.attr_type)))
            engine.complete_task(current_task_ref.current)
            reload()
        
        def on_widget_change(pv, idx):
            def handler(new_value):
                current = pv_values_ref.current
                new_vals = list(current[pv])
                new_vals[idx] = new_value
                set_pv_values({**current, pv: new_vals})
            return handler

        def on_delete_instance(pv, idx):
            def handler(*_):
                current = pv_values_ref.current
                new_vals = [v for i, v in enumerate(current[pv]) if i != idx]
                set_pv_values({**current, pv: new_vals})
            return handler

        def on_delete_attribute(pv):
            def handler(*_):
                set_pv_values({k: v for k, v in pv_values_ref.current.items() if k != pv})
            return handler

        def on_add_entity_select(pv):
            def handler(new_value):
                if new_value is None or new_value == EMPTY_ENTITY:
                    return
                current = pv_values_ref.current
                new_vals = [v for v in current[pv] if v != EMPTY_ENTITY] + [new_value]
                set_pv_values({**current, pv: new_vals})
            return handler

        def on_add_instance(pv):
            def handler(*_):
                current = pv_values_ref.current
                focus_attr_ref.current = pv
                set_pv_values({**current, pv: current[pv] + [_compute_default(get_attr(pkg, pv))]})
            return handler

        return on_submit_click, on_widget_change, on_delete_instance, on_delete_attribute, on_add_entity_select, on_add_instance

    on_submit_click, on_widget_change, on_delete_instance, on_delete_attribute, on_add_entity_select, on_add_instance = reacton.use_memo(_make_handlers, [])

    _GRID_COLS = '2fr 3fr 1fr auto'  # Attribute | Value | Type | Actions
    _DATA_PAD  = '0.5em 0.75em 0.5em 0.75em'
    _HDR_PAD   = '0.5em 0.75em 0.8em 0.75em'  # Extra bottom padding for descenders
    _HDR_BG    = '#f5f5f5'
    _HDR_SEP   = '2px solid #dddddd'  # header-to-data separator
    _COL_SEP   = '1px solid #e0e0e0'  # column dividers in header only
    _ROW_SEP   = '1px solid #f0f0f0'  # very subtle row separator for data

    def _hdr(last=False):
        return w.Layout(padding=_HDR_PAD, background_color=_HDR_BG, font_weight='bold',
                        border_bottom=_HDR_SEP,
                        border_right=(None if last else _COL_SEP))

    _data_cell = w.Layout(padding=_DATA_PAD)

    with w.VBox(layout=w.Layout(flex='1 1 auto', min_width='0')) as main:
        v.CardTitle(children=f'{pkg.label(next(pkg.objects(predicate = BPO.instanceOf, subject = current_task), None))} for {pkg.label(current_case)}')

        with w.GridBox(layout=w.Layout(
            width='100%',
            border='1px solid #dddddd',
            grid_template_columns=_GRID_COLS, flex_flow='row dense',
        )):
            # Header row — same grid tracks as data, so columns align perfectly
            # w.Label(value='Attribute', layout=_hdr())
            # w.Label(value='Value',     layout=_hdr())
            # w.Label(value='Type',      layout=_hdr())
            # w.Label(value='Actions',   layout=_hdr(last=True))

            for pv, vals in pv_values.items():
                meta = get_attr(pkg, pv)

                w.Label(value=meta.attr_name, layout=_data_cell)

                with w.VBox(layout=w.Layout(padding=_DATA_PAD, width='100%', border_bottom=_ROW_SEP, justify_content='center',overflow='hidden')):
                    if meta.is_entity:
                        EntityAttributeRow(
                            pkg, pv, meta, vals,
                            on_widget_change, on_delete_instance,
                            on_add_entity_select,
                        )
                    else:
                        should_focus = focus_attr_ref.current == pv
                        if should_focus:
                            focus_attr_ref.current = None
                        ScalarAttributeRow(
                            pv, meta, vals,
                            on_widget_change, on_delete_instance,
                            on_add_instance,
                            focus_last=should_focus,
                        )

                w.Label(value=str(pkg.label(meta.attr_type)), layout=_data_cell)

                with w.HBox(layout=w.Layout(width='100%', justify_content='center', align_items='center')):
                    w.Button(
                        description='×',
                        layout=w.Layout(width='36px', height='36px'),
                        button_style='danger',
                        on_click=on_delete_attribute(pv),
                    )

        AddProcessValueUI(pkg, list(pv_values.keys()), add_pv_to_form)
        w.Button(description="Submit", on_click=on_submit_click, layout=w.Layout(flex='0 0 auto'))
    return main

@reacton.component
def AddProcessValueUI(pkg, attributes, add_pv_to_form):

    remaining_options, set_remaining_options = reacton.use_state([])

    def update_remaining_options():
        all_pvs = list(pkg.subjects(predicate=RDF.type, object=BPO.ProcessValue))
        new_options = [(pkg.label(pv), pv) for pv in set(all_pvs) - set(attributes)]
        set_remaining_options(new_options)

    reacton.use_effect(update_remaining_options, [attributes])

    def on_select(new_value):
        if new_value is None or new_value == EMPTY_ENTITY:
            return
        try:
            add_pv_to_form(new_value)
        except Exception as e:
            print(f"Error adding ProcessValue: {e}")

    with w.VBox() as main:
        if remaining_options:
            w.Dropdown(
                value=EMPTY_ENTITY,
                options=[("Add a process value", EMPTY_ENTITY)] + remaining_options,
                on_value=on_select,
            )
        else:
            w.Label(value="No other process values available to add.")
    return main


# =========================== HELPERS ===========================
    
def _load_existing_values(pkg: ProcessKnowledgeGraph, case: URIRef, attr: URIRef):
    """Returns all existing graph values for a non-functional attribute."""
    existing_values = list(pkg.objects(subject=case, predicate=attr))
    return [val.toPython() if isinstance(val, Literal) else val for val in existing_values]


# =========================== DATA TYPES ===========================
@dataclass(frozen=True)
class Attr:
    attr_uri: URIRef
    attr_type: URIRef | None
    is_functional: bool
    is_entity: bool
    attr_name: str

def get_attr(pkg: ProcessKnowledgeGraph, attr_uri: URIRef) -> Attr:
    attr_type = pkg.value(predicate=BPO.dataType, subject=attr_uri, default=None)
    return Attr(
        attr_uri=attr_uri,
        attr_type=attr_type,
        is_functional=(attr_uri, RDF.type, OWL.FunctionalProperty) in pkg,
        is_entity=attr_type is not None and attr_type not in XSD,
        attr_name=pkg.label(attr_uri),
    )

def _compute_default(meta: Attr) -> object:
    """Returns a sensible default value for a given XSD type."""
    if meta.is_entity:
        return EMPTY_ENTITY
    return {
        XSD.integer: 0,
        XSD.float:   0.0,
        XSD.boolean: False,
    }.get(meta.attr_type, "")

# =========================== CONSTANTS ===========================

EMPTY_ENTITY = URIRef("urn:karibdis:empty")

# Layout widths
INPUT_WIDTH    = '100%'   # fills the flex Value column
CHIP_BTN_WIDTH = '32px'   # icon button, always fixed


# =========================== WIDGET FACTORY ===========================

def make_scalar_widget(attr_type, default_value, placeholder, on_change, autofocus=False, style=None):
    """Factory: returns the correct input widget for a given XSD type."""
    if style is None:
        style = "min-width: 0; margin: 0px;"
    if attr_type == XSD.integer:
        def int_handler(val):
            try:
                on_change(int(val) if val else 0)
            except (ValueError, TypeError):
                pass
        return v.TextField(
            v_model=str(default_value), type="number", placeholder=placeholder,
            autofocus=autofocus, on_v_model=int_handler, dense=True, style_=style, full_width=True,
        )
    if attr_type == XSD.float:
        _debounce_timer = [None]

        def float_handler(val):
            if _debounce_timer[0] is not None:
                _debounce_timer[0].cancel()
            # on_change(val) # This would make sense, but leads to behavior where the debount timer is not properly canceled

            def fire():
                try:
                    on_change(float(val) if val else 0.0)
                except (ValueError, TypeError):
                    pass

            _debounce_timer[0] = threading.Timer(0.8, fire)
            _debounce_timer[0].start()
        return v.TextField(
            v_model=str(default_value), type="number", step="any", placeholder=placeholder,
            autofocus=autofocus, on_v_model=on_change, dense=True, style_=style, full_width=True,
        )
    if attr_type == XSD.boolean:
        return w.Checkbox(value=default_value, description=placeholder,
                        on_value=on_change)
    # XSD.string and fallback
    return v.TextField(
        v_model=default_value or "", placeholder=placeholder,
        autofocus=autofocus, on_v_model=on_change, dense=True, style_=style,
    )


# =========================== ATTRIBUTE ROW COMPONENTS ===========================

@reacton.component
def ScalarAttributeRow(attr, meta, vals, on_widget_change, on_delete_instance, on_add_instance, focus_last=False):
    is_boolean = meta.attr_type == XSD.boolean
    is_string = meta.attr_type == XSD.string
    effective_vals = vals[:1] if is_boolean and not meta.is_functional else vals

    for idx, val in enumerate(effective_vals):
        is_last = idx == len(effective_vals) - 1
        placeholder = "Empty String" if is_string else ""
        autofocus = focus_last and is_last
        if meta.is_functional or is_boolean:
            make_scalar_widget(
                meta.attr_type, val, placeholder,
                on_widget_change(attr, idx),
                autofocus=autofocus,
            )
        else:
            with w.HBox(layout=w.Layout(width='100%', flex_flow='row', align_items='center')):
                with w.HBox(layout = w.Layout(flex= '1 1 auto', display= 'block') ):
                    make_scalar_widget(
                        meta.attr_type, val, placeholder,
                        on_widget_change(attr, idx),
                        autofocus=autofocus,
                    )
                w.Button(
                    description='×',
                    layout=w.Layout(width='32px', height='32px', flex='0 0 auto', margin='0 0 0 auto'),
                    button_style='',
                    style=w.ButtonStyle(button_color='#d0d0d0'),
                    on_click=on_delete_instance(attr, idx),
                )

    # Always show "Add value…" placeholder for non-functional, non-boolean types
    if not is_boolean and not meta.is_functional:
        w.Button(
            description='Add a new value',
            layout=w.Layout(width='100%', height='30px'),
            button_style='',
            style=w.ButtonStyle(button_color='#e8e8e8', text_color='#999999', font_style='italic'),
            on_click=on_add_instance(attr),
        )
        
        
    
@reacton.component
def EntityAttributeRow(pkg, attr, meta, vals, on_widget_change, on_delete_instance, on_add_entity_select):
    options = list(pkg.subjects(predicate=RDF.type / (RDFS.subClassOf * ZeroOrMore), object=meta.attr_type))
    labels = [str(pkg.label(option)) for option in options]
    dropdown_options = list(zip(labels, options))
    options_with_empty = [("Select a value", EMPTY_ENTITY)] + dropdown_options

    _dropdown_style = {'description_width': '0px'}
    if meta.is_functional:
        current_val = vals[0] if vals else EMPTY_ENTITY
        w.Dropdown(
            value=current_val,
            options=options_with_empty,
            layout=w.Layout(width='100%'),
            style=_dropdown_style,
            on_value=on_widget_change(attr, 0),
        )
    else:
        visible_instances = [(idx, v) for idx, v in enumerate(vals) if v != EMPTY_ENTITY]
        already_selected = {v for _, v in visible_instances}
        remaining_options = [
            (lbl, val) for lbl, val in dropdown_options if val not in already_selected
        ]

        with w.VBox(layout=w.Layout(width='100%', overflow='hidden', grid_gap='4px')):
            for idx, chip_value in visible_instances:
                with w.HBox(layout=w.Layout(width='100%')):
                    w.Label(value=str(pkg.label(chip_value)), layout=w.Layout(flex='1 1 auto'))
                    w.Button(
                        description='×',
                        layout=w.Layout(width=CHIP_BTN_WIDTH, height='32px', margin='0 0 0 auto'),
                        button_style='',
                        style=w.ButtonStyle(button_color='#d0d0d0'),
                        on_click=on_delete_instance(attr, idx),
                    )
            if remaining_options:
                w.Dropdown(
                    value=EMPTY_ENTITY,
                    options=[("Add a new value", EMPTY_ENTITY)] + remaining_options,
                    layout=w.Layout(width='100%'),
                    style=_dropdown_style,
                    on_value=on_add_entity_select(attr),
                )