"""Validate canonical observations independently of their producer."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

from nemo.canonical import SourceContract, source_contract

BUSINESS_ZONE = timezone(timedelta(hours=5, minutes=30))
REQUIRED_TABLES = ("customers", "campaigns", "ad_performance", "sessions", "orders")
CHANNELS = ("paid_search", "organic_search", "direct")
DEVICES = ("android", "ios", "desktop")
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE customers(customer_id TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL);
CREATE TABLE campaigns(campaign_id TEXT PRIMARY KEY, name TEXT NOT NULL,
 channel TEXT NOT NULL, is_paid INTEGER NOT NULL);
CREATE TABLE ad_performance(
 business_date TEXT NOT NULL, campaign_id TEXT REFERENCES campaigns, device TEXT NOT NULL,
 impressions INTEGER NOT NULL, clicks INTEGER NOT NULL, spend_paise INTEGER NOT NULL,
 PRIMARY KEY(business_date, campaign_id, device));
CREATE TABLE sessions(
 session_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers,
 started_at TEXT NOT NULL, business_date TEXT NOT NULL, channel TEXT NOT NULL,
 campaign_id TEXT REFERENCES campaigns, device TEXT NOT NULL, is_paid INTEGER NOT NULL);
CREATE TABLE orders(
 order_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions,
 customer_id TEXT NOT NULL REFERENCES customers, paid_at TEXT NOT NULL,
 business_date TEXT NOT NULL, amount_paise INTEGER NOT NULL);
CREATE INDEX orders_session ON orders(session_id);
CREATE INDEX orders_customer ON orders(customer_id, paid_at, order_id);
"""


@dataclass
class Snapshot:
    connection: sqlite3.Connection
    start: date
    end: date
    manifest_sha256: str
    table_hashes: dict[str, str]
    contract: SourceContract


def _text(row: dict, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a nonempty string")
    return value


def _integer(row: dict, key: str) -> int:
    value = row.get(key)
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError(f"{key} must be a nonnegative 64-bit integer")
    return value


def _timestamp(row: dict, key: str, start: date, end: date) -> tuple[str, str]:
    value = datetime.fromisoformat(_text(row, key))
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{key} must be timezone-aware UTC")
    business_date = value.astimezone(BUSINESS_ZONE).date()
    if not start <= business_date < end:
        raise ValueError(f"{key} is outside the observation window")
    return value.astimezone(UTC).isoformat(timespec="microseconds"), business_date.isoformat()


def _record(table: str, row: dict, start: date, end: date, contract: SourceContract) -> tuple:
    if table == "customers":
        stamp, _ = _timestamp(row, "first_seen_at", start, end)
        return _text(row, "customer_id"), stamp
    if table == "campaigns":
        channel = "paid_search" if contract.schema_version == "1" else _text(row, "channel")
        if channel not in contract.channels:
            raise ValueError("unknown campaign channel")
        return (
            _text(row, "campaign_id"),
            _text(row, "name"),
            channel,
            int(contract.channels[channel]),
        )
    if table in ("sessions", "ad_performance"):
        if row.get("device") not in contract.devices:
            raise ValueError("unknown device")
    if table == "ad_performance":
        day = date.fromisoformat(_text(row, "business_date"))
        if not start <= day < end:
            raise ValueError("ad business_date outside observation window")
        impressions, clicks = _integer(row, "impressions"), _integer(row, "clicks")
        if contract.schema_version == "1" and clicks > impressions:
            raise ValueError("clicks cannot exceed impressions in schema 1")
        return (
            day.isoformat(),
            _text(row, "campaign_id"),
            row["device"],
            impressions,
            clicks,
            _integer(row, "spend_paise"),
        )
    if table == "sessions":
        stamp, day = _timestamp(row, "started_at", start, end)
        if row.get("channel") not in contract.channels:
            raise ValueError("unknown channel")
        if contract.channels[row["channel"]]:
            _text(row, "campaign_id")
        elif contract.schema_version == "1" and row.get("campaign_id") is not None:
            raise ValueError("non-paid sessions cannot have a paid campaign")
        return (
            _text(row, "session_id"),
            _text(row, "customer_id"),
            stamp,
            day,
            row["channel"],
            row.get("campaign_id"),
            row["device"],
            int(contract.channels[row["channel"]]),
        )
    stamp, day = _timestamp(row, "paid_at", start, end)
    amount = _integer(row, "amount_paise")
    if amount == 0:
        raise ValueError("paid order amount must be positive")
    return (
        _text(row, "order_id"),
        _text(row, "session_id"),
        _text(row, "customer_id"),
        stamp,
        day,
        amount,
    )


@contextmanager
def open_snapshot(directory: Path):
    """Verify and load a public observations directory; never inspect its parent/private files."""
    raw_manifest = (directory / "manifest.json").read_bytes()
    manifest = json.loads(raw_manifest)
    expected = {
        "currency": "INR",
        "money_unit": "paise",
        "amount_basis": "tax_exclusive_merchandise",
        "business_timezone": "Asia/Kolkata",
        "timestamp_timezone": "UTC",
    }
    if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in expected.items()):
        raise ValueError("unsupported observation schema, mode, currency, or units")
    contract = source_contract(manifest)
    try:
        window = manifest["observation_window"]
        start = date.fromisoformat(window["start_date_inclusive"])
        end = date.fromisoformat(window["end_date_exclusive"])
        tables = manifest["tables"]
        if start >= end or not isinstance(tables, dict):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("manifest requires a valid observation_window and tables") from error
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        hashes = {}
        for table in REQUIRED_TABLES:
            details = tables.get(table)
            if not isinstance(details, dict) or type(details.get("rows")) is not int:
                raise ValueError(f"missing/invalid manifest entry for {table}")
            payload = (directory / f"{table}.jsonl").read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if digest != details.get("sha256"):
                raise ValueError(f"checksum mismatch: {table}")
            lines = payload.splitlines()
            if len(lines) != details["rows"]:
                raise ValueError(f"row count mismatch: {table}")
            for number, line in enumerate(lines, 1):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("record must be an object")
                    values = _record(table, row, start, end, contract)
                    placeholders = ",".join("?" for _ in values)
                    connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)
                except (ValueError, TypeError, sqlite3.IntegrityError) as error:
                    raise ValueError(f"{table} row {number}: {error}") from error
            hashes[table] = digest
        invalid_order = connection.execute("""
            SELECT 1 FROM orders o JOIN sessions s USING(session_id)
            WHERE o.customer_id <> s.customer_id OR o.paid_at < s.started_at LIMIT 1
        """).fetchone()
        invalid_customer = connection.execute("""
            SELECT 1 FROM sessions s JOIN customers c USING(customer_id)
            WHERE c.first_seen_at > s.started_at LIMIT 1
        """).fetchone()
        invalid_campaign = connection.execute("""
            SELECT 1 FROM sessions s JOIN campaigns c USING(campaign_id)
            WHERE s.channel <> c.channel OR s.is_paid <> c.is_paid
            UNION ALL
            SELECT 1 FROM ad_performance a JOIN campaigns c USING(campaign_id)
            WHERE c.is_paid <> 1
        """).fetchone()
        if invalid_order or invalid_customer or invalid_campaign:
            raise ValueError("customer/session/order identity or chronology mismatch")
        yield Snapshot(
            connection, start, end, hashlib.sha256(raw_manifest).hexdigest(), hashes, contract
        )
    finally:
        connection.close()
