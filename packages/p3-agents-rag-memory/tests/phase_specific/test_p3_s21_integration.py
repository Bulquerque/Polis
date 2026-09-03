from __future__ import annotations

import pytest

from .p3_s21_helpers import run_through_m06


@pytest.mark.asyncio
async def test_p3_s21_all_six_wrappers_integrate() -> None:
    result = await run_through_m06()
    structured = result[-1]["structured_belief_proposal_panel"]
    assert structured["records"][0]["payload"]["score"] == 1.0
