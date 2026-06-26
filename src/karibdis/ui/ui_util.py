import reacton
import reacton.ipywidgets as w
import reacton.ipyvuetify as v
from ipywidgets.widgets.widget_string import LabelStyle
from IPython.display import HTML
from IPython.display import display, Javascript

import base64
import ipywidgets
import uuid
from pyparsing import ParseException
import json

from karibdis.utils import *



@reacton.component
def SelectionMenu(title, items, set_items, reload, item_label, make_item_view, item_equality = lambda a,b : a is b, collection_name='items'):
    with w.VBox() as main:
        
        with v.Card(): 
            v.CardTitle(children=title)
            with v.CardText():
                current_item, set_current_item = reacton.use_state(next(iter(items), None))
                reacton.use_effect(lambda: set_current_item(next(iter(items), None)), [items])
                if len(items) > 0 and current_item is not None:
                    with w.HBox(layout=w.Layout(width='100%', align_items='flex-start')):
                        with w.VBox():
                            for item in items:
                                w.Button(
                                    description=item_label(item), 
                                    on_click=lambda item=item: set_current_item(item),
                                    style=w.ButtonStyle(button_color='#DDEEFF' if item_equality(item, current_item) else None)
                                )
                        make_item_view(current_item)
                else:
                    w.Label(value=f'No {collection_name} to select')
                    
        w.Button(description=f'Reload {collection_name}', on_click=reload, layout=w.Layout(flex='0 0 auto'))
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
