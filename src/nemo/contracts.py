"""Versioned source records. Monetary values are tax-exclusive INR integer paise."""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from typing import Literal

SCHEMA_VERSION = "1"
Device = Literal["android", "ios", "desktop"]
Channel = Literal["paid_search", "organic_search", "direct"]
EventName = Literal[
    "session_started",
    "checkout_started",
    "payment_attempted",
    "payment_succeeded",
    "payment_failed",
    "purchase",
]


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    seed: int = 42
    start_date: date = date(2025, 1, 1)
    end_date: date = date(2026, 7, 1)  # exclusive
    paid_impressions_per_campaign_day: int = 600
    organic_sessions_per_day: int = 25
    direct_sessions_per_day: int = 15
    payment_success_probability: float = 0.92
    refund_probability: float = 0.08

    def __post_init__(self) -> None:
        if type(self.start_date) is not date or type(self.end_date) is not date:
            raise ValueError("start_date and end_date must be dates, not timestamps")
        if not 1 <= (self.end_date - self.start_date).days <= 3660:
            raise ValueError("date interval must contain 1 to 3660 days; end is exclusive")
        if self.start_date.year < 2000 or self.end_date.year > 2100:
            raise ValueError("simulation dates must be within 2000–2100")
        for name, maximum in (
            ("seed", 2**63 - 1),
            ("paid_impressions_per_campaign_day", 100_000),
            ("organic_sessions_per_day", 10_000),
            ("direct_sessions_per_day", 10_000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(f"{name} must be an integer between 0 and {maximum}")
        for name in ("payment_success_probability", "refund_probability"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite probability between 0 and 1")


@dataclass(frozen=True, slots=True)
class Customer:
    customer_id: str
    first_seen_at: datetime


@dataclass(frozen=True, slots=True)
class Product:
    product_id: str
    name: str
    unit_price_paise: int


@dataclass(frozen=True, slots=True)
class Campaign:
    campaign_id: str
    name: str


@dataclass(frozen=True, slots=True)
class AdPerformance:
    business_date: date
    campaign_id: str
    device: Device
    impressions: int
    clicks: int
    unit_click_price_paise: int
    spend_paise: int


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    customer_id: str
    started_at: datetime
    channel: Channel
    campaign_id: str | None
    device: Device


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    session_id: str
    occurred_at: datetime
    name: EventName
    order_id: str | None = None


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    session_id: str
    customer_id: str
    paid_at: datetime
    amount_paise: int


@dataclass(frozen=True, slots=True)
class OrderItem:
    order_item_id: str
    order_id: str
    product_id: str
    quantity: int
    unit_price_paise: int
    amount_paise: int


@dataclass(frozen=True, slots=True)
class Refund:
    refund_id: str
    order_item_id: str
    refunded_at: datetime
    quantity: int
    amount_paise: int


TABLES = (
    "customers",
    "products",
    "campaigns",
    "ad_performance",
    "sessions",
    "events",
    "orders",
    "order_items",
    "refunds",
)


@dataclass(frozen=True, slots=True)
class World:
    config: SimulationConfig
    customers: tuple[Customer, ...]
    products: tuple[Product, ...]
    campaigns: tuple[Campaign, ...]
    ad_performance: tuple[AdPerformance, ...]
    sessions: tuple[Session, ...]
    events: tuple[Event, ...]
    orders: tuple[Order, ...]
    order_items: tuple[OrderItem, ...]
    refunds: tuple[Refund, ...]
