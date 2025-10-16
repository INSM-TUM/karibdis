import time

import reacton
import reacton.ipywidgets as w
from IPython.display import display

import playwright.sync_api
from playwright.sync_api import expect

from karibdis.Application import *

def test_app_runs(solara_test, page_session: playwright.sync_api.Page):
    app = JupyterApplication()
    display(app.base_view())
    expect(page_session.get_by_text('Knowledge Modeling')).to_be_visible()
    expect(page_session.get_by_text('Process Execution')).to_be_visible()
    expect(page_session.get_by_text('Explore Graph')).to_be_visible()
