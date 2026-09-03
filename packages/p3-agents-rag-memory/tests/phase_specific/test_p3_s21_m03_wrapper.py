from __future__ import annotations

import pytest

from .p3_s21_helpers import run_through_m03


@pytest.mark.asyncio
async def test_m03_wrapper_contract() -> None:
    result = await run_through_m03()
    output = result[-1]
    assert "raw_tool_result_panel" in output
