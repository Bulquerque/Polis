from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.foundation.models import (
    NonEmptyStr, NonNegativeDecimal, PositiveDecimal, StrictModel, TimeAwareModel,
)
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256

SignedDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(gt=0)]


class MonetaryAmount(StrictModel):
    currency: NonEmptyStr
    amount: SignedDecimal


class SealedModel(StrictModel):
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def payload_hash(model: StrictModel) -> str:
    return content_sha256(model.model_dump(mode="python", exclude={"content_sha256"}))


def seal(model: SealedModel):
    return model.model_copy(update={"content_sha256": payload_hash(model)})


class EquityPoint(TimeAwareModel):
    as_of_time: datetime
    nav: SignedDecimal


class FxRate(TimeAwareModel):
    currency: NonEmptyStr
    functional_currency: NonEmptyStr
    rate: PositiveDecimal
    available_at: datetime

    @model_validator(mode="after")
    def validate_pair(self):
        if self.currency == self.functional_currency and self.rate != Decimal("1"):
            raise ValueError("same-currency FX rate must equal 1")
        return self
