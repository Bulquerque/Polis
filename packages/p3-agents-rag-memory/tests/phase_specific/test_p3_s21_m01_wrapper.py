from __future__ import annotations

import pytest

from .p3_s21_helpers import run_through_m01


@pytest.mark.asyncio
async def test_m01_wrapper_contract() -> None:
    result = await run_through_m01()
    output = result[-1]
    assert "initial_agent_reading_panel" in output
