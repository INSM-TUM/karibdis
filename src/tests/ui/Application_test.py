import time

import reacton
import reacton.ipywidgets as w
from IPython.display import display

import playwright.sync_api
from playwright.sync_api import Page, expect

from karibdis.Application import *

def test_app_runs(solara_test, page_session: Page):
    app = JupyterApplication()
    display(app.base_view())
    tablist = page_session.get_by_role('tablist')
    expect(tablist.get_by_text('Knowledge Modeling')).to_be_visible()
    expect(tablist.get_by_text('Decisionmaking')).to_be_visible()
    expect(tablist.get_by_text('Task Execution')).to_be_visible()
    expect(tablist.get_by_text('Explore Graph')).to_be_visible()