"""Business invariants: these assertions are independent of sampling probabilities."""

import random
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from nemo.contracts import SimulationConfig
from nemo.simulation import BUSINESS_TIMEZONE, generate


@pytest.fixture(scope="module", params=[42, 91, 1234])
def world(request):
    # Full 18-month reference world plus independent short worlds.
    config = SimulationConfig(seed=request.param)
    if request.param != 42:
        config = replace(config, end_date=date(2025, 2, 1))
    return generate(config)


def test_identity_relationships_and_customer_first_seen(world):
    def indexed(rows, key):
        result = {getattr(row, key): row for row in rows}
        assert len(result) == len(rows)
        return result

    customers = indexed(world.customers, "customer_id")
    products = indexed(world.products, "product_id")
    campaigns = indexed(world.campaigns, "campaign_id")
    sessions = indexed(world.sessions, "session_id")
    orders = indexed(world.orders, "order_id")
    items = indexed(world.order_items, "order_item_id")
    indexed(world.events, "event_id")
    indexed(world.refunds, "refund_id")
    first_seen = {}
    for session in world.sessions:
        assert session.customer_id in customers
        first_seen.setdefault(session.customer_id, session.started_at)
        assert session.device in {"android", "ios", "desktop"}
        if session.channel == "paid_search":
            assert session.campaign_id in campaigns
        else:
            assert session.channel in {"organic_search", "direct"}
            assert session.campaign_id is None
    assert {row.customer_id: row.first_seen_at for row in world.customers} == first_seen
    assert len(first_seen) < len(world.sessions)  # repeat visits actually occur
    for order in world.orders:
        assert order.session_id in sessions
        assert order.customer_id == sessions[order.session_id].customer_id
    for item in world.order_items:
        assert item.order_id in orders
        assert item.product_id in products
    for event in world.events:
        assert event.session_id in sessions
        if event.order_id is not None:
            assert orders[event.order_id].session_id == event.session_id
    assert all(refund.order_item_id in items for refund in world.refunds)


def test_money_reconciles_at_line_order_and_refund_grains(world):
    totals = Counter()
    products = {row.product_id: row for row in world.products}
    items = {row.order_item_id: row for row in world.order_items}
    for item in world.order_items:
        assert type(item.amount_paise) is int
        assert item.quantity > 0
        assert item.unit_price_paise == products[item.product_id].unit_price_paise
        assert item.amount_paise == item.quantity * item.unit_price_paise > 0
        totals[item.order_id] += item.amount_paise
    assert {row.order_id: row.amount_paise for row in world.orders} == totals
    refund_amounts, refund_quantities = Counter(), Counter()
    for refund in world.refunds:
        item = items[refund.order_item_id]
        assert type(refund.amount_paise) is int
        assert refund.quantity > 0
        assert refund.amount_paise == refund.quantity * item.unit_price_paise > 0
        refund_amounts[item.order_item_id] += refund.amount_paise
        refund_quantities[item.order_item_id] += refund.quantity
    for item_id, amount in refund_amounts.items():
        assert amount <= items[item_id].amount_paise
        assert refund_quantities[item_id] <= items[item_id].quantity
    assert world.refunds  # the tested worlds exercise refunds, not a vacuous bound


def test_paid_clicks_bound_landing_sessions(world):
    paid_sessions = Counter(
        (row.started_at.astimezone(BUSINESS_TIMEZONE).date(), row.campaign_id, row.device)
        for row in world.sessions
        if row.channel == "paid_search"
    )
    keys = set()
    for row in world.ad_performance:
        key = (row.business_date, row.campaign_id, row.device)
        assert key not in keys
        keys.add(key)
        assert 0 <= paid_sessions[key] <= row.clicks <= row.impressions
        assert row.spend_paise == row.clicks * row.unit_click_price_paise
    assert paid_sessions.keys() <= keys
    assert len(keys) == (world.config.end_date - world.config.start_date).days * 2 * 3


def test_funnel_has_legal_paths_and_exact_order_correspondence(world):
    grouped = defaultdict(list)
    for event in world.events:
        grouped[event.session_id].append(event)
    allowed = {
        ("session_started",),
        ("session_started", "checkout_started"),
        ("session_started", "checkout_started", "payment_attempted", "payment_failed"),
        (
            "session_started",
            "checkout_started",
            "payment_attempted",
            "payment_succeeded",
            "purchase",
        ),
    }
    purchases = Counter()
    for session in world.sessions:
        events = grouped[session.session_id]
        assert tuple(row.name for row in events) in allowed
        assert events[0].occurred_at == session.started_at
        assert all(a.occurred_at < b.occurred_at for a, b in zip(events, events[1:], strict=False))
        if events[-1].name == "purchase":
            assert events[-2].order_id == events[-1].order_id is not None
            purchases[events[-1].order_id] += 1
        else:
            assert all(row.order_id is None for row in events)
    assert purchases == Counter({row.order_id: 1 for row in world.orders})
    succeeded = {
        row.order_id: row.occurred_at for row in world.events if row.name == "payment_succeeded"
    }
    assert succeeded == {row.order_id: row.paid_at for row in world.orders}


def test_timestamps_respect_business_window_and_refund_order(world):
    start = datetime.combine(world.config.start_date, time(), BUSINESS_TIMEZONE).astimezone(UTC)
    end = datetime.combine(world.config.end_date, time(), BUSINESS_TIMEZONE).astimezone(UTC)
    for rows, attribute in (
        (world.customers, "first_seen_at"),
        (world.sessions, "started_at"),
        (world.events, "occurred_at"),
        (world.orders, "paid_at"),
        (world.refunds, "refunded_at"),
    ):
        stamps = [getattr(row, attribute) for row in rows]
        assert stamps == sorted(stamps)
        assert all(stamp.tzinfo == UTC and start <= stamp < end for stamp in stamps)
    orders = {row.order_id: row for row in world.orders}
    items = {row.order_item_id: row for row in world.order_items}
    for refund in world.refunds:
        assert orders[items[refund.order_item_id].order_id].paid_at < refund.refunded_at


def test_default_is_eighteen_calendar_months():
    config = SimulationConfig()
    assert config.start_date == date(2025, 1, 1)
    assert config.end_date == date(2026, 7, 1)
    assert (config.end_date - config.start_date).days == 546


def test_seed_is_reproducible_changes_world_and_preserves_global_random_state():
    config = SimulationConfig(end_date=date(2025, 1, 8))
    random.seed(783)
    before = random.getstate()
    first = generate(config)
    assert random.getstate() == before
    assert first == generate(config)
    assert first.sessions != generate(replace(config, seed=43)).sessions


def test_zero_traffic_is_a_valid_empty_business():
    world = generate(
        SimulationConfig(
            end_date=date(2025, 1, 2),
            paid_impressions_per_campaign_day=0,
            organic_sessions_per_day=0,
            direct_sessions_per_day=0,
        )
    )
    assert not any(
        (
            world.sessions,
            world.customers,
            world.events,
            world.orders,
            world.order_items,
            world.refunds,
        )
    )
    assert all(
        row.impressions == row.clicks == row.spend_paise == 0 for row in world.ad_performance
    )


def test_all_failed_payments_never_create_sales():
    world = generate(SimulationConfig(end_date=date(2025, 1, 15), payment_success_probability=0))
    assert any(row.name == "payment_failed" for row in world.events)
    assert not world.orders and not world.order_items and not world.refunds
    assert not any(row.name in {"purchase", "payment_succeeded"} for row in world.events)


def test_all_successful_attempts_produce_one_order_each():
    world = generate(SimulationConfig(end_date=date(2025, 1, 15), payment_success_probability=1))
    assert world.orders
    assert not any(row.name == "payment_failed" for row in world.events)
    assert sum(row.name == "payment_attempted" for row in world.events) == len(world.orders)


def test_refunds_are_censored_at_cutoff_and_can_be_partial_or_full():
    one_day = generate(SimulationConfig(end_date=date(2025, 1, 2), refund_probability=1))
    assert one_day.orders
    assert not one_day.refunds  # earliest possible refund is tomorrow
    longer = generate(SimulationConfig(end_date=date(2025, 2, 1), refund_probability=1))
    items = {row.order_item_id: row for row in longer.order_items}
    assert any(row.quantity == items[row.order_item_id].quantity for row in longer.refunds)
    assert any(row.quantity < items[row.order_item_id].quantity for row in longer.refunds)
    none = generate(SimulationConfig(end_date=date(2025, 1, 15), refund_probability=0))
    assert none.orders and not none.refunds


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": -1},
        {"seed": True},
        {"seed": 1.5},
        {"start_date": date(2025, 1, 1), "end_date": date(2025, 1, 1)},
        {"end_date": date(2024, 12, 31)},
        {"end_date": date(2040, 1, 1)},
        {"start_date": "2025-01-01"},
        {"start_date": datetime(2025, 1, 1)},
        {"organic_sessions_per_day": -1},
        {"direct_sessions_per_day": True},
        {"paid_impressions_per_campaign_day": 100_001},
        {"payment_success_probability": float("nan")},
        {"refund_probability": float("inf")},
        {"refund_probability": -0.1},
        {"payment_success_probability": 1.1},
    ],
)
def test_invalid_config_fails_at_boundary(changes):
    with pytest.raises(ValueError):
        SimulationConfig(**changes)
