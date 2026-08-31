import uuid
import threading

import reacton
import reacton.ipyvuetify as v

_dispatch = {"push": None}

def toast(message, kind="error", timeout=6.0):
    """Show an app-wide toast.
    `kind` is a Vuetify alert type: 'error' | 'warning' | 'info' | 'success'.
    Falls back to a console print if no ToastHost is mounted yet.
    """
    fn = _dispatch["push"]
    if fn is not None:
        fn(str(message), kind, timeout)
    else:
        print(f"[toast:{kind}] {message}")


@reacton.component
def ToastItem(message, kind):
    """A single toast item. Auto-dismisses after a timeout, or can be dismissed by the user."""
    return v.Alert(type=kind, dense=True, closable=True, class_='ma-0',
                   style_='pointer-events:auto;min-width:300px;max-width:460px;',
                   children=[message])


@reacton.component
def ToastHost():
    """App-wide toast overlay. Mount exactly ONE at the app root. On mount it registers
    its push() into the module dispatcher so `toast(...)` works from anywhere."""
    toasts, set_toasts = reacton.use_state([])

    def remove(tid):
        set_toasts(lambda cur: [t for t in cur if t['id'] != tid])

    def push(message, kind='error', timeout=6.0):
        tid = uuid.uuid4().hex
        set_toasts(lambda cur: cur + [dict(id=tid, message=message, type=kind)])
        t = threading.Timer(timeout, lambda: remove(tid))   # auto-dismiss
        t.daemon = True
        t.start()

    def _register():
        _dispatch["push"] = push
        return lambda: _dispatch.update(push=None)          # cleanup on unmount
    reacton.use_effect(_register, [])                       # once, on mount

    with v.Html(tag='div',
                style_='position:fixed;bottom:24px;left:50%;'
                       'transform:translateX(-50%);z-index:99999;'
                       'display:flex;flex-direction:column;gap:8px;'
                       'align-items:center;pointer-events:none;') as main:
        for t in toasts:
            ToastItem(t['message'], t['type'])
    return main