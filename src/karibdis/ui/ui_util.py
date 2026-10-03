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

from karibdis.ui.toast import toast
from karibdis.utils import *


_SCRIM_Z = 5
_EXEMPT_Z = _SCRIM_Z + 1
_SCRIM_OPACITY = 0.6
_SPINNER_SIZE = 48
_SPINNER_COLOR = 'primary'


def _run_in_background(executable, clear_busy):
    """Runs `executable` on a daemon thread and clears the busy state afterwards, whatever
    happens. Failures are surfaced as a toast rather than a print, which is invisible
    under Voila. `executable` runs off the render thread: calling reacton state setters
    from it is fine, touching widgets directly is not."""
    def _worker():
        try:
            executable()
        except Exception as e:
            toast(f'Background task failed: {e}', kind='error')
        finally:
            clear_busy()

    threading.Thread(target=_worker, daemon=True).start()


def _run_inline(executable):
    """Fallback used when no busy scope is mounted, so every component stays renderable
    on its own (in tests, notebooks, or as a standalone widget). No thread, no overlay."""
    executable()


_busy_context = reacton.create_context((False, _run_inline))


def use_busy():
    """Hook for any component doing slow work: returns (is_busy, be_busy_with) from the
    nearest enclosing BusyScope. Route slow work through be_busy_with(executable) and the
    scope shows the spinner and blocks input until it returns. Outside a scope the
    executable simply runs inline."""
    return _busy_context.use()


@reacton.component
def _Scrim(is_busy, render_content, scrim=True):
    """Blocks clicks on whatever `render_content` creates while `is_busy`, and dims it
    unless `scrim=False`. Knows nothing about who started the work."""
    style = 'position:relative; width:100%;' + (' pointer-events:none;' if is_busy else '')
    with v.Html(tag='div', style_=style) as main:
        render_content()
        if scrim:
            with v.Overlay(
                contained=True,
                model_value=is_busy,
                persistent=True,
                no_click_animation=True,
                scrim='white',
                opacity=_SCRIM_OPACITY,
                z_index=_SCRIM_Z,
                content_class='w-100 h-100 d-flex align-center justify-center',
            ):
                v.ProgressCircular(indeterminate=True, size=_SPINNER_SIZE, width=6, color=_SPINNER_COLOR)
    return main


@reacton.component
def _BusyOverlay(is_busy, render_content, be_busy_with):
    """A busy scope over caller-owned state: draws the scrim and publishes
    (is_busy, be_busy_with) to descendants. Use BusyScope unless you own the state."""
    _busy_context.provide((is_busy, be_busy_with))
    return _Scrim(is_busy, render_content)


@reacton.component
def BusyScope(render_content):
    """Marks a region as one unit of work. Everything `render_content` creates is blocked
    and dimmed while work started via use_busy() inside it is running."""
    busy, set_busy = reacton.use_state(False)
    busy_ref = reacton.use_ref(False)

    def _make_runner():
        def be_busy_with(executable):
            if busy_ref.current:  # re-entrant trigger while busy: ignore
                return
            busy_ref.current = True
            set_busy(True)

            def _clear():
                busy_ref.current = False
                set_busy(False)

            _run_in_background(executable, _clear)
        return be_busy_with

    return _BusyOverlay(busy, render_content, reacton.use_memo(_make_runner, []))


@reacton.component
def BusyExempt(render_content):
    """An island inside a busy scope that stays interactive while everything around it is
    blocked. Re-enables pointer events and lifts above the scrim."""
    style = f'pointer-events:auto; position:relative; z-index:{_EXEMPT_Z}; width:fit-content;'
    with v.Html(tag='div', style_=style) as main:
        render_content()
    return main


@reacton.component
def SelectionMenu(title, items, reload, item_label, make_item_view, item_equality = lambda a,b : a is b, collection_name='items', lock_selection_while_busy=False):
    current_item, set_current_item = reacton.use_state(next(iter(items), None))
    reacton.use_effect(lambda: set_current_item(next(iter(items), None)), [items])

    busy_items, set_busy_items = reacton.use_state([])

    def _prune_stale_busy():
        set_busy_items(lambda old: [b for b in old if any(item_equality(b, it) for it in items)])
    reacton.use_effect(_prune_stale_busy, [items])

    def be_busy_with_item(item, executable):
        if any(item_equality(item, b) for b in busy_items):
            return
        set_busy_items(lambda old: old + [item])
        _run_in_background(
            executable,
            lambda: set_busy_items(lambda old: [b for b in old if not item_equality(b, item)]))

    current_is_busy = current_item is not None and any(item_equality(current_item, b) for b in busy_items)
    selection_locked = lock_selection_while_busy and current_is_busy

    def render_menu():
        with v.Card(flat=True):
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
                        _BusyOverlay(
                            current_is_busy,
                            lambda: make_item_view(current_item),
                            lambda executable, _item=current_item: be_busy_with_item(_item, executable),
                        )
                else:
                    w.Label(value=f'No {collection_name} to select')

        w.Button(description=f'Reload {collection_name}', on_click=reload, layout=w.Layout(flex='0 0 auto'))

    with w.VBox() as main:
        _Scrim(selection_locked, render_menu, scrim=False)
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
