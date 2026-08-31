import time

from IPython.display import display
from playwright.sync_api import Page, expect

from karibdis.ui.toast import ToastHost, toast, _dispatch

def _wait_registered(timeout=5.0):
    """Block until the mounted ToastHost has published its push() into the dispatcher."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _dispatch["push"] is not None:
            return
        time.sleep(0.02)
    raise AssertionError("ToastHost never registered its dispatcher (did it mount?)")


def test_toast_appears_on_blank_screen(solara_test, page_session: Page):
    display(ToastHost())
    _wait_registered()

    toast("An error occurred", "error", timeout=30)
    expect(page_session.get_by_text("An error occurred")).to_be_visible()


def test_toasts_stack(solara_test, page_session: Page):
    display(ToastHost())
    _wait_registered()

    toast("info", "info", timeout=30)
    toast("warning", "warning", timeout=30)
    toast("success", "success", timeout=30)

    expect(page_session.get_by_text("info")).to_be_visible()
    expect(page_session.get_by_text("warning")).to_be_visible()
    expect(page_session.get_by_text("success")).to_be_visible()


def test_toast_manual_dismiss(solara_test, page_session: Page):
    display(ToastHost())
    _wait_registered()

    toast("dismiss me", "error", timeout=30)
    alert = page_session.locator(".v-alert", has_text="dismiss me")
    expect(alert).to_be_visible()

    page_session.locator(".v-alert", has_text="dismiss me").get_by_role("button").click()
    expect(page_session.get_by_text("dismiss me")).not_to_be_visible()


def test_toast_auto_dismiss(solara_test, page_session: Page):
    display(ToastHost())
    _wait_registered()

    toast("will be auto-dismissed", "info", timeout=1.0)
    expect(page_session.get_by_text("will be auto-dismissed")).to_be_visible()
    
    expect(page_session.get_by_text("will be auto-dismissed")).not_to_be_visible(timeout=5000)
