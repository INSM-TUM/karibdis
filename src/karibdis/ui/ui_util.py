import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v
from ipywidgets.widgets.widget_string import LabelStyle
from IPython.display import HTML
from IPython.display import display, Javascript

import base64
import ipywidgets
import threading
import uuid
from pyparsing import ParseException
import json

from karibdis.utils import *


def _run_on_thread(executable, on_done, on_finish):
    """Runs `executable` on a daemon thread, then applies `on_done(result)` and 
    finally `on_finish()` to clear the busy state -- in that order, so the outcome
    lands in the same frame the overlay disappears."""
    def _worker():
        result = None
        try:
            result = executable()
        except Exception as e:
            print(f'Error in background task: {e}')
        if on_done is not None:
            on_done(result)
        on_finish()

    threading.Thread(target=_worker, daemon=True).start()

_busy_context = reacton.create_context((False, None))


def use_be_busy():
    """Hook for any component doing slow work: returns (is_busy, be_busy_with) from the
    nearest enclosing busy scope. Route calls through be_busy_with(executable,
    on_done=None) and the enclosing scope will show the spinner and block the input."""
    return _busy_context.use()


def use_busy():
    """Hook for a component that owns a busy scope and must also trigger work from its own
    render scope. Pass the returned runner to BusyOverlay(be_busy_with=...) so descendants share it."""
    busy, set_busy = reacton.use_state(False)
    busy_ref = reacton.use_ref(False)

    def _make_runner():
        def be_busy_with(executable, on_done=None):
            if busy_ref.current:  # re-entrant trigger while busy: ignore
                return
            busy_ref.current = True
            set_busy(True)

            def _finish():
                busy_ref.current = False
                set_busy(False)

            _run_on_thread(executable, on_done, _finish)
        return be_busy_with

    # Memoised so the provided context value only changes when `busy` does.
    return busy, reacton.use_memo(_make_runner, [])


@reacton.component
def BusyOverlay(is_busy, render_content, be_busy_with=None, spinner=True,
                size=48, color='primary', opacity=0.6, z_index=5):
    """A busy scope with externally supplied state. Everything `render_content` creates is
    blocked while `is_busy`, and descendants get (is_busy, be_busy_with) from use_be_busy()."""
    if be_busy_with is not None:
        _busy_context.provide((is_busy, be_busy_with))

    style = 'position:relative; width:100%;' + (' pointer-events:none;' if is_busy else '')
    with v.Html(tag='div', style_=style) as main:
        render_content()
        with v.Overlay(
            contained=True,
            model_value=is_busy,
            persistent=True,
            no_click_animation=True,
            scrim='white',
            opacity=opacity,
            z_index=z_index,
            content_class='w-100 h-100 d-flex align-center justify-center',
        ):
            if spinner:
                v.ProgressCircular(indeterminate=True, size=size, width=6, color=color)
    return main


@reacton.component
def BusyExempt(render_content):
    """An island inside a busy scope that stays interactive while everything around it is
    blocked. Re-enables pointer events and lifts above the scrim."""
    with v.Html(tag='div', style_='pointer-events:auto; position:relative; z-index:6; width:fit-content;') as main:
        render_content()
    return main


@reacton.component
def SelectionMenu(title, items, set_items, reload, item_label, make_item_view, item_equality = lambda a,b : a is b, collection_name='items', lock_selection_while_busy=False):
    current_item, set_current_item = reacton.use_state(next(iter(items), None))
    reacton.use_effect(lambda: set_current_item(next(iter(items), None)), [items])

    busy_items, set_busy_items = reacton.use_state([])

    def _prune_stale_busy():
        set_busy_items(lambda old: [b for b in old if any(item_equality(b, it) for it in items)])
    reacton.use_effect(_prune_stale_busy, [items])

    def be_busy_with_item(item, executable, on_done=None):
        if any(item_equality(item, b) for b in busy_items):
            return
        set_busy_items(lambda old: old + [item])
        _run_on_thread(executable, on_done,
                       lambda: set_busy_items(lambda old: [b for b in old if not item_equality(b, item)]))

    current_is_busy = current_item is not None and any(item_equality(current_item, b) for b in busy_items)
    selection_locked = lock_selection_while_busy and current_is_busy

    def render_menu():
        with v.Card():
            v.CardTitle(children=title)
            with v.CardText():
                if len(items) > 0 and current_item is not None:
                    with w.HBox(layout=w.Layout(width='100%', align_items='flex-start')):
                        with w.VBox():
                            for item in items:
                                item_busy = any(item_equality(item, b) for b in busy_items)
                                w.Button(
                                    description=item_label(item) + (' ⏳' if item_busy else ''),
                                    on_click=lambda item=item: set_current_item(item),
                                    style=w.ButtonStyle(button_color='#DDEEFF' if item_equality(item, current_item) else None)
                                )
                        # The pane is its own busy scope, bound to the selected item.
                        BusyOverlay(
                            current_is_busy,
                            lambda: make_item_view(current_item),
                            be_busy_with=lambda executable, on_done=None, _item=current_item: be_busy_with_item(_item, executable, on_done),
                        )
                else:
                    w.Label(value=f'No {collection_name} to select')

        w.Button(description=f'Reload {collection_name}', on_click=reload, layout=w.Layout(flex='0 0 auto'))

    with w.VBox() as main:
        BusyOverlay(selection_locked, render_menu, spinner=False, opacity=0.15)
    return main


@reacton.component
def GraphViz(graph, color_func=None, max_nodes=600):
    """Shared graph visualization -- handles the empty and too-large cases. Blocking/dimming
    is the caller's business: put it inside a busy scope."""
    with w.VBox() as main:
        if len(graph) == 0:
            w.Label(value='No data to visualize.')
        elif len(graph.all_nodes()) > max_nodes:
            w.Label(value=f'Too many nodes ({len(graph.all_nodes())}) to visualize.')
        elif color_func is not None:
            display(draw_graph(graph, color_func=color_func))
        else:
            display(draw_graph(graph))
    return main


@reacton.component
def TextEditor(importer, init_value, set_editing):
    with w.VBox(layout = ipywidgets.Layout(width='100%', height='98%')) as main:
        text_value, set_text_value = reacton.use_state(init_value)
        text = w.Textarea(
            layout = ipywidgets.Layout(width='98%'),
            value = text_value,
            rows = len(text_value.split('\n')),
            on_value=set_text_value
        )
        def accept_edit(b=None):
            if text_value != init_value:
                importer.reload_from_text(text_value)
            else:
                print('No changes')
            set_editing(False)

        button_accept = w.Button(description='Accept Edit', on_click=accept_edit, layout=w.Layout(flex='0 0 auto'))
        button_cancel = w.Button(description='Cancel Edit', on_click=lambda: set_editing(False), layout=w.Layout(flex='0 0 auto'))
    return main


def QueryBox(graph, initial_query=None):
    # TODO consider adding namespaces per default
    default_initial_query = ''' 
SELECT ?subject ?predicate ?object
WHERE {
    ?subject ?predicate ?object . 
    FILTER("true") .
} 
'''  
    current_result, set_current_result = reacton.use_state(None)
    error_msg, set_error_msg = reacton.use_state('')
    current_result_size, set_current_result_size = reacton.use_state(0)
    dirty, set_dirty = reacton.use_state(True)
    query, _set_query = reacton.use_state(initial_query if initial_query else default_initial_query) 
    def set_query(value):
        set_dirty(True)
        _set_query(value)  

    def place_box():
        with w.VBox():
            if error_msg:
                w.Label(value=f'Error: {error_msg}', style=LabelStyle(text_color='red')) 
            w.Textarea(
                layout = w.Layout(width='98%'),
                value = query,
                on_value=set_query,
                rows = len(query.split('\n')) + 2
            )

    def run_query():
        try:
            query_result = graph.query(query)
            set_current_result_size(len(query_result))
            set_dirty(False)
            set_current_result(query_result)
            set_error_msg('')
        except ParseException as e:
            set_error_msg('Invalid Query')
            print(e)
        # print(query_result)

    return place_box, current_result, current_result_size, dirty, run_query



def download(data, title = "Download file", filename = "file"):
    b64 = base64.b64encode(data.encode())
    payload = b64.decode()
    html = '<a download="{filename}" href="data:text/csv;base64,{payload}" target="_blank">{title}</a>'
    html = html.format(payload=payload,title=title,filename=filename)
    return HTML(html)



# Attention: Veeeeery hacky
def format_query(queries, callback, output=None):
#    try:
#        async with async_timeout.timeout(2):
            
            bridge = ipywidgets.Textarea()
            classname = 'x' + str(uuid.uuid4()).replace('-', '')
            bridge.add_class(classname)
            
            js = Javascript("""
            // https://stackoverflow.com/a/61511955
            function waitForElm(selector) {
                return new Promise(resolve => {
                    if (document.querySelector(selector)) {
                        return resolve(document.querySelector(selector));
                    }
            
                    const observer = new MutationObserver(mutations => {
                        if (document.querySelector(selector)) {
                            observer.disconnect();
                            resolve(document.querySelector(selector));
                        }
                    });
            
                    // If you get "parameter 1 is not of type 'Node'" error, see https://stackoverflow.com/a/77855838/492336
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                });
            }
            
            
            (async () => {
                if (!window.spfmt) {
                    await import("https://cdn.jsdelivr.net/gh/sparqling/sparql-formatter@v1.0.2/dist/spfmt.js");
                }
                console.log(window.spfmt)
                const queries = """+ json.dumps(queries) +""";
                console.log(queries)
                let formatted = [];
                try {
                    formatted = queries.map(x => window.spfmt.format(x));
                    console.log("Formatted queries:\\n", formatted);
                } catch(e) {
                    formatted = 'ERROR: ' + e;
                }
                const elm = await waitForElm('."""+classname+"""');
                const input = elm.getElementsByClassName('widget-input')[0]
                input.value = JSON.stringify(formatted);
                input.dispatchEvent(new Event("input", { bubbles: true }));
            })();
            """)

            
            if output is not None:
                with output:
                    display(ipywidgets.Label('foo2'))
                    display(js)
                    display(ipywidgets.Label('foo3'))
                    display(bridge)
            else:
                display(bridge, js)
            
            def handle_value(x):
                value = x['new']
                bridge.close()
                #future.set_result(json.loads(value))
                callback(json.loads(value))
                if output is not None:
                    output.clear_output()
            
            bridge.observe(handle_value, 'value')
#    except asyncio.TimeoutError:
#        return query
