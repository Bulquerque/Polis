from __future__ import annotations

from enum import StrEnum


class ExecutionMode(StrEnum):
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class SecurityType(StrEnum):
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    FUTURE = "FUTURE"
    ETF = "ETF"
    CRYPTO = "CRYPTO"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PositionIntent(StrEnum):
    BUY_TO_OPEN = "BUY_TO_OPEN"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"
    NO_PHYSICAL_TRADE = "NO_PHYSICAL_TRADE"


class IntentType(StrEnum):
    OPEN = "OPEN"
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    HEDGE = "HEDGE"
    LIFECYCLE = "LIFECYCLE"


class RiskRole(StrEnum):
    PROTECTIVE = "PROTECTIVE"
    RISK_REDUCING = "RISK_REDUCING"
    NEUTRAL = "NEUTRAL"
    RISK_INCREASING = "RISK_INCREASING"


class AuthorizationStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    PARTIALLY_AUTHORIZED = "PARTIALLY_AUTHORIZED"


class StructureType(StrEnum):
    SINGLE = "SINGLE"
    COMBO = "COMBO"
    LEGGING = "LEGGING"
    BLOCKED = "BLOCKED"


class OrderClass(StrEnum):
    SIMPLE = "SIMPLE"
    MLEG = "MLEG"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(StrEnum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    OPG = "OPG"
    CLS = "CLS"


class Urgency(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


class OrderEventType(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    CANCEL = "CANCEL"
    REJECT = "REJECT"
    EXPIRE = "EXPIRE"
    REPLACE = "REPLACE"


class MarketEventType(StrEnum):
    QUOTE = "QUOTE"
    TRADE = "TRADE"
    VENUE_STATUS = "VENUE_STATUS"


class VenueState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"


class RuntimeControlMode(StrEnum):
    NORMAL = "NORMAL"
    HOLD_NO_NEW_RISK = "HOLD_NO_NEW_RISK"
    CANCEL_OPEN_ORDERS = "CANCEL_OPEN_ORDERS"
    CLOSE_ONLY = "CLOSE_ONLY"
    RISK_REDUCTION_ONLY = "RISK_REDUCTION_ONLY"
    HEDGE_ONLY = "HEDGE_ONLY"
    CONTROLLED_FLATTEN = "CONTROLLED_FLATTEN"
    HALT = "HALT"


class CapabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


class CostQuality(StrEnum):
    QUALIFIED = "QUALIFIED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ReceiptStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    PARTIAL = "PARTIAL"
    NO_ACTION_VALID = "NO_ACTION_VALID"
