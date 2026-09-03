from __future__ import annotations

import pytest

from .p3_s21_helpers import run_through_m02


@pytest.mark.asyncio
async def test_m02_wrapper_contract() -> None:
    result = await run_through_m02()
    output = result[-1]
    assert "validated_tool_call_request_panel" in output
