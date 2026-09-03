from __future__ import annotations

import pytest

from .p3_s21_helpers import run_through_m04


@pytest.mark.asyncio
async def test_m04_wrapper_contract() -> None:
    result = await run_through_m04()
    output = result[-1]
    assert "validated_tool_result_panel" in output
