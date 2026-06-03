import threading
import importlib

# Utility class for asynchronous import of heavy libs
# Auto-generated code, use with caution

def async_import(name):
    return AsyncModuleProxy(name)

class AsyncModuleProxy:
    def __init__(self, module_name):
        self._module_name = module_name
        self._module = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

        # Start background import immediately
        threading.Thread(target=self._load_module, daemon=True).start()

    def _load_module(self):
        #print(f'Start aynchronous import of module "{self._module_name}".')
        module = importlib.import_module(self._module_name)
        with self._lock:
            self._module = module
            self._ready.set()
            #print(f'Module "{self._module_name}" imported asynchronously.')

    def _get_module(self):
        self._ready.wait()  # Blocks only if import not finished
        return self._module

    def __getattr__(self, item):
        module = self._get_module()
        return getattr(module, item)