"""Healthy, linked business activity. Parameters are assumptions, not fitted estimates."""

from datetime import UTC, datetime, time, timedelta, timezone
from random import Random

from nemo.contracts import (
    AdPerformance,
    Campaign,
    Channel,
    Customer,
    Device,
    Event,
    EventName,
    Order,
    OrderItem,
    Product,
    Refund,
    Session,
    SimulationConfig,
    World,
)

GENERATOR_VERSION = "1"
BUSINESS_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
DEVICES: tuple[Device, ...] = ("android", "ios", "desktop")
DEVICE_WEIGHTS = (0.55, 0.20, 0.25)
CHECKOUT_PROBABILITY: dict[Device, float] = {"android": 0.14, "ios": 0.16, "desktop": 0.19}
PRODUCTS = (
    Product("sku-001", "Hand wash refill", 49_900),
    Product("sku-002", "Laundry concentrate", 79_900),
    Product("sku-003", "Body wash", 59_900),
    Product("sku-004", "Kitchen cleaner", 39_900),
)
CAMPAIGNS = (
    Campaign("campaign-brand", "Search — brand"),
    Campaign("campaign-nonbrand", "Search — nonbrand"),
)


def generate(config: SimulationConfig) -> World:
    """Generate a fixed-date world using only a local PRNG; never consult wall-clock time."""
    rng = Random(config.seed)
    customers: list[Customer] = []
    ads: list[AdPerformance] = []
    sessions: list[Session] = []
    events: list[Event] = []
    orders: list[Order] = []
    items: list[OrderItem] = []
    refunds: list[Refund] = []
    cutoff = datetime.combine(config.end_date, time(), BUSINESS_TIMEZONE).astimezone(UTC)

    def add_event(
        session: Session,
        seconds: int,
        name: EventName,
        order_id: str | None = None,
    ) -> None:
        events.append(
            Event(
                f"event-{len(events) + 1:09d}",
                session.session_id,
                session.started_at + timedelta(seconds=seconds),
                name,
                order_id,
            )
        )

    for day_offset in range((config.end_date - config.start_date).days):
        day = config.start_date + timedelta(days=day_offset)
        midnight = datetime.combine(day, time(), BUSINESS_TIMEZONE).astimezone(UTC)
        traffic_multiplier = (1.15 if day.weekday() >= 5 else 1.0) * rng.uniform(0.85, 1.15)
        arrivals: list[tuple[int, Channel, str | None, Device]] = []
        for campaign_index, campaign in enumerate(CAMPAIGNS):
            for device, weight in zip(DEVICES, DEVICE_WEIGHTS, strict=True):
                impressions = int(
                    config.paid_impressions_per_campaign_day * traffic_multiplier * weight
                )
                clicks = sum(rng.random() < 0.04 for _ in range(impressions))
                unit_click_price = 1_400 + campaign_index * 600
                ads.append(
                    AdPerformance(
                        day,
                        campaign.campaign_id,
                        device,
                        impressions,
                        clicks,
                        unit_click_price,
                        clicks * unit_click_price,
                    )
                )
                for _ in range(clicks):
                    if rng.random() < 0.88:
                        arrivals.append(
                            (
                                rng.randrange(8 * 3600, 21 * 3600),
                                "paid_search",
                                campaign.campaign_id,
                                device,
                            )
                        )
        for channel, daily_sessions in (
            ("organic_search", config.organic_sessions_per_day),
            ("direct", config.direct_sessions_per_day),
        ):
            for _ in range(int(daily_sessions * traffic_multiplier)):
                arrivals.append(
                    (
                        rng.randrange(8 * 3600, 21 * 3600),
                        channel,
                        None,
                        rng.choices(DEVICES, weights=DEVICE_WEIGHTS, k=1)[0],
                    )
                )

        # Timestamp-only stable ordering avoids comparing nullable campaign IDs.
        for seconds, channel, campaign_id, device in sorted(arrivals, key=lambda row: row[0]):
            started_at = midnight + timedelta(seconds=seconds)
            if not customers or rng.random() < 0.65:
                customer = Customer(f"customer-{len(customers) + 1:09d}", started_at)
                customers.append(customer)
            else:
                customer = rng.choice(customers)
            session = Session(
                f"session-{len(sessions) + 1:09d}",
                customer.customer_id,
                started_at,
                channel,
                campaign_id,
                device,
            )
            sessions.append(session)
            add_event(session, 0, "session_started")
            if rng.random() >= CHECKOUT_PROBABILITY[device]:
                continue
            add_event(session, 60, "checkout_started")
            if rng.random() >= 0.90:
                continue
            add_event(session, 120, "payment_attempted")
            if rng.random() >= config.payment_success_probability:
                add_event(session, 150, "payment_failed")
                continue

            order_id = f"order-{len(orders) + 1:09d}"
            paid_at = started_at + timedelta(seconds=150)
            basket: list[OrderItem] = []
            for product in rng.sample(PRODUCTS, k=rng.randint(1, 3)):
                quantity = rng.randint(1, 3)
                item = OrderItem(
                    f"item-{len(items) + 1:09d}",
                    order_id,
                    product.product_id,
                    quantity,
                    product.unit_price_paise,
                    quantity * product.unit_price_paise,
                )
                items.append(item)
                basket.append(item)
                if rng.random() < config.refund_probability:
                    refunded_at = paid_at + timedelta(days=rng.randint(1, 14))
                    refunded_quantity = rng.randint(1, quantity)
                    if refunded_at < cutoff:
                        refunds.append(
                            Refund(
                                f"refund-{len(refunds) + 1:09d}",
                                item.order_item_id,
                                refunded_at,
                                refunded_quantity,
                                refunded_quantity * item.unit_price_paise,
                            )
                        )
            orders.append(
                Order(
                    order_id,
                    session.session_id,
                    customer.customer_id,
                    paid_at,
                    sum(item.amount_paise for item in basket),
                )
            )
            add_event(session, 150, "payment_succeeded", order_id)
            add_event(session, 151, "purchase", order_id)

    return World(
        config,
        tuple(customers),
        PRODUCTS,
        CAMPAIGNS,
        tuple(ads),
        tuple(sessions),
        tuple(sorted(events, key=lambda row: (row.occurred_at, row.event_id))),
        tuple(orders),
        tuple(items),
        tuple(sorted(refunds, key=lambda row: (row.refunded_at, row.refund_id))),
    )
