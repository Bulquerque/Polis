from datetime import datetime

import pytest

from tests.agents.a4.conftest import NOW
from quant_pipeline.phase_08_portfolio_control.foundation.errors import TemporalIntegrityError
from quant_pipeline.phase_08_portfolio_control.foundation.event_ordering import ScheduledEvent, TimelinePriority, order_timeline


def test_safety_and_venue_precede_submit_at_same_time():
    events = [
        ScheduledEvent(NOW, TimelinePriority.MARKET_DATA, "market", "market"),
        ScheduledEvent(NOW, TimelinePriority.ORDER_SUBMISSION, "submit", "submit"),
        ScheduledEvent(NOW, TimelinePriority.VENUE_STATUS, "venue", "venue"),
        ScheduledEvent(NOW, TimelinePriority.SAFETY_COMMAND, "safety", "safety"),
    ]
    assert [x.payload for x in order_timeline(events)] == ["safety", "venue", "submit", "market"]


def test_duplicate_event_key_is_fatal():
    event = ScheduledEvent(NOW, TimelinePriority.MARKET_DATA, "same", "a")
    with pytest.raises(TemporalIntegrityError, match="duplicate"):
        order_timeline([event, event])


def test_naive_timeline_time_is_fatal():
    event = ScheduledEvent(datetime(2026, 1, 1), TimelinePriority.MARKET_DATA, "naive", "a")
    with pytest.raises(TemporalIntegrityError, match="timezone-aware"):
        order_timeline([event])
