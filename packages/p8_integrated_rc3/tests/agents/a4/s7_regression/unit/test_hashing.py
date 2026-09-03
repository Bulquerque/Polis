from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.foundation.errors import ContractIntegrityError
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256


def test_hash_is_order_independent_for_mapping():
    assert content_sha256({"a":1,"b":2}) == content_sha256({"b":2,"a":1})


def test_decimal_and_datetime_are_canonical():
    assert content_sha256({"x":Decimal("1.00")}) == content_sha256({"x":Decimal("1")})
    dt=datetime(2026,1,1,tzinfo=timezone.utc)
    assert content_sha256({"t":dt}) == content_sha256({"t":dt})


def test_naive_datetime_rejected():
    with pytest.raises(ContractIntegrityError):
        content_sha256({"t":datetime(2026,1,1)})
