import time

def wait_for(assertion_statement, timeout=5.0, poll_interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            assertion_statement()
        except AssertionError:
            pass
        finally:
            time.sleep(poll_interval)
            continue
    assertion_statement()  # one last try, will raise if it fails