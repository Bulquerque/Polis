from __future__ import annotations

import os
import sys

import pytest


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus: int, config) -> None:
    """Terminate after pytest has reported the completed result.

    Some optional numerical backends leave teardown workers alive after the
    terminal summary. The test session is complete at this hook, so a forced
    exit prevents CI from hanging without masking the pytest exit status.
    """
    terminalreporter.write_line(f"PYTEST TERMINAL STATUS: {exitstatus}")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(int(exitstatus))
