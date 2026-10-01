"""Offline provider contract checks; no assertion of live account verification."""

import copy
import json
from decimal import Decimal
from io import BytesIO

import pytest

from nemo import google_ingestion as google


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    for service in google.SERVICES:
        monkeypatch.setenv("NEMO_GOOGLE_" + service.upper() + "_ACCESS_TOKEN", "test-only")
    monkeypatch.setenv("NEMO_GOOGLE_ADS_DEVELOPER_TOKEN", "test-developer")
    monkeypatch.delenv("NEMO_GOOGLE_ADS_LOGIN_CUSTOMER_ID", raising=False)


def ads_row(day="2026-01-01"):
    return {
        "customer": {"currencyCode": "INR", "timeZone": "Asia/Kolkata"},
        "campaign": {"id": "12", "name": "Brand", "advertisingChannelType": "SEARCH"},
        "segments": {"date": day, "device": "MOBILE"},
        "metrics": {"impressions": "100", "clicks": "5", "costMicros": "9007199254750000"},
    }


def ga_page():
    return {
        "dimensionHeaders": [{"name": n} for n in google.GA_DIMENSIONS],
        "metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}],
        "rowCount": 1,
        "metadata": {"timeZone": "Asia/Kolkata", "subjectToThresholding": True},
        "rows": [
            {
                "dimensionValues": [{"value": v} for v in ["20260101", "Paid Search", "mobile"]],
                "metricValues": [{"value": "25"}],
            }
        ],
    }


def run(service, transport, **kwargs):
    return google.extract(
        service,
        "sc-domain:example.com" if service == "search_console" else "123",
        "2026-01-01",
        "2026-01-02",
        transport=transport,
        **kwargs,
    )


def test_ads_paging_money_and_provenance():
    calls = []

    def transport(url, body, headers):
        assert url == "https://googleads.googleapis.com/v25/customers/123/googleAds:search"
        assert headers["developer-token"] == "test-developer"
        assert "cost_micros" in body["query"]
        calls.append(body)
        return (
            {"results": [ads_row()], "nextPageToken": "second"}
            if len(calls) == 1
            else {"results": [ads_row("2026-01-02")]}
        )

    result = run("ads", transport)
    assert calls[1]["pageToken"] == "second"
    assert result["rows"][0]["spend_paise"] == 900719925475
    assert result["timezone"] == "Asia/Kolkata"
    assert result["canonical_activation"] is False and result["pages"] == 2
    assert "test-developer" not in json.dumps(result)
    assert "test-only" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["currency", "fraction", "duplicate", "outside", "token", "bound"])
def test_ads_rejects_unsafe_or_incomplete_mapping(kind):
    row = ads_row()
    page = {"results": [row]}
    if kind == "currency":
        row["customer"]["currencyCode"] = "USD"
    elif kind == "fraction":
        row["metrics"]["costMicros"] = "10001"
    elif kind == "duplicate":
        page["results"].append(copy.deepcopy(row))
    elif kind == "outside":
        row["segments"]["date"] = "2026-01-03"
    else:
        page = {"results": [], "nextPageToken": "same"}
    with pytest.raises(ValueError):
        run("ads", lambda *a: page, max_pages=1 if kind == "bound" else 20)


def test_ga4_aggregates_preserve_thresholds_and_timezone():
    def transport(url, body, headers):
        assert url.endswith("/v1beta/properties/123:runReport")
        assert body["metrics"] == [{"name": "sessions"}]
        assert body["offset"] == "0"
        return ga_page()

    result = run("ga4", transport)
    assert result["rows"][0]["reported_sessions"] == 25
    assert result["metadata"][0]["subjectToThresholding"] is True
    assert "session_id" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["schema", "count", "duplicate", "empty"])
def test_ga4_pagination_validation(kind):
    page = ga_page()
    if kind == "schema":
        page["metricHeaders"][0]["name"] = "activeUsers"
    elif kind == "empty":
        page["rows"] = []
    else:
        page["rowCount"] = 2
    calls = []

    def transport(*args):
        calls.append(args)
        result = copy.deepcopy(page)
        if kind == "count" and len(calls) > 1:
            result["rowCount"] = 3
        return result

    with pytest.raises(ValueError):
        run("ga4", transport)


def test_search_console_returned_query_coverage_and_exact_decimal():
    def transport(url, body, headers):
        assert "sc-domain%3Aexample.com" in url
        assert body["dataState"] == "final" and body["rowLimit"] == 25000
        return {
            "rows": [
                {
                    "keys": ["2026-01-01", "nemo", "MOBILE"],
                    "clicks": Decimal("3.0"),
                    "impressions": Decimal("10.0"),
                    "position": Decimal("1.234567890123456789"),
                }
            ]
        }

    result = run("search_console", transport)
    assert result["timezone"] == "America/Los_Angeles"
    assert result["coverage"] == "returned_queries_only"
    assert result["rows"][0]["reported_position"] == "1.234567890123456789"
    assert result["rows"][0]["clicks"] == 3


@pytest.mark.parametrize("value", [True, -1, "1.5", Decimal("NaN"), 2**63])
def test_exact_integer_contract(value):
    with pytest.raises(ValueError):
        google.integer(value)


def test_missing_credentials_and_invalid_identity_fail_before_network(monkeypatch):
    monkeypatch.delenv("NEMO_GOOGLE_GA4_ACCESS_TOKEN")
    with pytest.raises(ValueError, match="token"):
        run("ga4", lambda *a: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="numeric"):
        google.extract("ads", "../other", "2026-01-01", "2026-01-02")


def test_transport_bounds_redirection_and_safe_errors(monkeypatch):
    class Transport:
        def open(self, request, timeout):
            assert timeout == 45
            return BytesIO(b"x" * (google.MAX_BYTES + 1))

    monkeypatch.setattr(google, "build_opener", lambda *a: Transport())
    with pytest.raises(ValueError, match="Google request failed"):
        google.post("https://googleads.googleapis.com/", {}, {})
    with pytest.raises(ValueError, match="redirects"):
        google.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid")


def test_cli_does_not_publish_partial_output(tmp_path, monkeypatch, capsys):
    target = tmp_path / "report.json"
    target.write_text("previous report")

    def fail(*args, **kwargs):
        raise ValueError("secret-provider-body")

    monkeypatch.setattr(google, "extract", fail)
    assert (
        google.main(
            [
                "ga4",
                "--account",
                "123",
                "--start",
                "2026-01-01",
                "--end",
                "2026-01-02",
                "--output",
                str(target),
            ]
        )
        == 1
    )
    assert target.read_text() == "previous report"
    assert "secret-provider-body" not in capsys.readouterr().err
