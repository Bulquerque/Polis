from __future__ import annotations

import pytest

from .p3_s21_helpers import run_through_m05


@pytest.mark.asyncio
async def test_m05_wrapper_contract() -> None:
    result = await run_through_m05()
    output = result[-1]
    assert "raw_belief_proposal_panel" in output
