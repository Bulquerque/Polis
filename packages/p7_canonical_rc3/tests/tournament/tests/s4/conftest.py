from __future__ import annotations

import pytest

from .factories import execution_config, make_bundle


@pytest.fixture
def valid_bundle():
    return make_bundle()


@pytest.fixture
def config():
    return execution_config()
