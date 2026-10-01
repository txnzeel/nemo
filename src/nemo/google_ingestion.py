"""Bounded read-only Google report extraction; staging is not canonical event data."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

SERVICES = ("ads", "ga4", "search_console")
MAX_BYTES = 8 * 1024 * 1024
GA_DIMENSIONS = ["date", "sessionDefaultChannelGroup", "deviceCategory"]


def integer(value):
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("expected nonnegative integer")
    result = int(value)
    if result > 2**63 - 1:
        raise ValueError("integer exceeds int64")
    return result


def text(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("missing or oversized dimension")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Google redirects are not permitted")


def post(url, body, headers):
    """Only called with internally constructed endpoints; errors never echo response bodies."""
    request = Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with build_opener(NoRedirect).open(request, timeout=45) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("report page too large")
        result = json.loads(raw, parse_float=Decimal)
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("invalid report")
        return result
    except (URLError, OSError, ValueError):
        raise ValueError(
            "Google request failed; verify access, quota and report contract"
        ) from None


def extract(service, account, start, end, *, max_pages=20, transport=post):
    """Dates are inclusive in each provider's own timezone. No analytical activation."""
    if service not in SERVICES or type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError("invalid service or page bound")
    if (
        date.fromisoformat(start).isoformat() != start
        or date.fromisoformat(end).isoformat() != end
        or date.fromisoformat(end) < date.fromisoformat(start)
    ):
        raise ValueError("invalid inclusive date window")
    if service != "search_console" and not re.fullmatch(r"[0-9]{1,20}", account):
        raise ValueError("numeric account/property ID required, without separators")
    if service == "search_console" and not re.fullmatch(
        r"(?:https?://|sc-domain:)[^\s?#]+", account
    ):
        raise ValueError("exact Search Console site property required")
    token = os.environ.get("NEMO_GOOGLE_" + service.upper() + "_ACCESS_TOKEN")
    if not token:
        raise ValueError("service access token is not configured")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    body = {}
    if service == "ads":
        developer = os.environ.get("NEMO_GOOGLE_ADS_DEVELOPER_TOKEN")
        if not developer:
            raise ValueError("Ads developer token is not configured")
        headers["developer-token"] = developer
        manager = os.environ.get("NEMO_GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        if manager:
            if not re.fullmatch(r"[0-9]{1,20}", manager):
                raise ValueError("invalid manager ID")
            headers["login-customer-id"] = manager
        url = f"https://googleads.googleapis.com/v25/customers/{account}/googleAds:search"
        body = {
            "query": "SELECT customer.currency_code, customer.time_zone, campaign.id, "
            "campaign.name, campaign.advertising_channel_type, segments.date, segments.device, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros FROM campaign "
            f"WHERE segments.date BETWEEN '{start}' AND '{end}' "
            "ORDER BY segments.date, campaign.id, segments.device"
        }
    elif service == "ga4":
        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{account}:runReport"
        body = {
            "dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [{"name": name} for name in GA_DIMENSIONS],
            "metrics": [{"name": "sessions"}],
            "orderBys": [{"dimension": {"dimensionName": name}} for name in GA_DIMENSIONS],
            "limit": "10000",
            "offset": "0",
            "returnPropertyQuota": True,
        }
    else:
        url = "https://www.googleapis.com/webmasters/v3/sites/" + quote(account, safe="")
        url += "/searchAnalytics/query"
        body = {
            "startDate": start,
            "endDate": end,
            "dimensions": ["date", "query", "device"],
            "type": "web",
            "dataState": "final",
            "rowLimit": 25000,
            "startRow": 0,
        }
    rows, metadata, seen, tokens = [], [], set(), set()
    timezone = "America/Los_Angeles" if service == "search_console" else None
    total = None
    for _page_number in range(max_pages):
        page = transport(url, dict(body), dict(headers))
        if not isinstance(page, dict) or "error" in page:
            raise ValueError("invalid Google report page")
        raw_rows = page.get("results" if service == "ads" else "rows", [])
        if not isinstance(raw_rows, list):
            raise ValueError("invalid rows")
        if service == "ga4":
            if [h["name"] for h in page["dimensionHeaders"]] != GA_DIMENSIONS or [
                h["name"] for h in page["metricHeaders"]
            ] != ["sessions"]:
                raise ValueError("GA4 report schema changed")
            count = integer(page.get("rowCount", 0))
            if total is not None and count != total:
                raise ValueError("GA4 report changed during pagination")
            total = count
            meta = page["metadata"]
            zone = text(meta["timeZone"])
            ZoneInfo(zone)
            if timezone is not None and zone != timezone:
                raise ValueError("report timezone changed")
            timezone = zone
            metadata.append(
                {
                    key: meta[key]
                    for key in (
                        "timeZone",
                        "subjectToThresholding",
                        "samplingMetadatas",
                        "dataLossFromOtherRow",
                        "schemaRestrictionResponse",
                        "emptyReason",
                        "dataTruncationReasons",
                    )
                    if key in meta
                }
            )
        for raw in raw_rows:
            if service == "ads":
                customer, segment, campaign, metrics = (
                    raw["customer"],
                    raw["segments"],
                    raw["campaign"],
                    raw["metrics"],
                )
                zone = text(customer["timeZone"])
                ZoneInfo(zone)
                if customer["currencyCode"] != "INR":
                    raise ValueError("only INR mapping supported; no implicit FX")
                if timezone is not None and zone != timezone:
                    raise ValueError("report timezone changed")
                timezone = zone
                micros = integer(metrics.get("costMicros", "0"))
                if micros % 10000:
                    raise ValueError("sub-paise spend needs an explicit reconciliation policy")
                row = {
                    "date": segment["date"],
                    "campaign_id": str(integer(campaign["id"])),
                    "campaign_name": text(campaign["name"]),
                    "source_channel": text(campaign["advertisingChannelType"]),
                    "source_device": text(segment["device"]),
                    "impressions": integer(metrics.get("impressions", "0")),
                    "clicks": integer(metrics.get("clicks", "0")),
                    "spend_paise": micros // 10000,
                }
                grain = (row["date"], row["campaign_id"], row["source_device"])
            elif service == "ga4":
                dims, values = raw["dimensionValues"], raw["metricValues"]
                if len(dims) != 3 or len(values) != 1:
                    raise ValueError("invalid GA4 row shape")
                day = text(dims[0]["value"])
                if not re.fullmatch(r"[0-9]{8}", day):
                    raise ValueError("invalid GA4 date")
                row = {
                    "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                    "source_channel": text(dims[1]["value"]),
                    "source_device": text(dims[2]["value"]),
                    "reported_sessions": integer(values[0]["value"]),
                }
                grain = tuple(row[k] for k in ("date", "source_channel", "source_device"))
            else:
                if len(raw["keys"]) != 3:
                    raise ValueError("invalid Search Console dimensions")
                position = Decimal(str(raw["position"]))
                if not position.is_finite() or position < 0:
                    raise ValueError("invalid position")
                row = {
                    "date": text(raw["keys"][0]),
                    "query": text(raw["keys"][1]),
                    "source_device": text(raw["keys"][2]),
                    "impressions": integer(raw["impressions"]),
                    "clicks": integer(raw["clicks"]),
                    "reported_position": str(position),
                }
                timezone = "America/Los_Angeles"
                grain = (row["date"], row["query"], row["source_device"])
            day = date.fromisoformat(row["date"])
            if not date.fromisoformat(start) <= day <= date.fromisoformat(end) or grain in seen:
                raise ValueError("out-of-window or duplicate report grain")
            seen.add(grain)
            rows.append(row)
        if len(rows) > 100000:
            raise ValueError("row bound exceeded; split extraction window")
        if service == "ads":
            token = page.get("nextPageToken")
            if not token:
                break
            if not isinstance(token, str) or token in tokens:
                raise ValueError("repeated or invalid page token")
            tokens.add(token)
            body["pageToken"] = token
        elif service == "ga4":
            if len(rows) > total:
                raise ValueError("GA4 rows exceed declared count")
            if len(rows) == total:
                break
            if not raw_rows:
                raise ValueError("GA4 page is incomplete")
            body["offset"] = str(len(rows))
        else:
            if len(raw_rows) < 25000:
                break
            body["startRow"] = len(rows)
    else:
        raise ValueError("page bound exceeded; no partial report published")
    result = {
        "schema_version": "google-report-stage-1",
        "source": service,
        "account": account,
        "start_inclusive": start,
        "end_inclusive": end,
        "timezone": timezone,
        "pages": _page_number + 1,
        "rows": rows,
        "metadata": metadata,
        "coverage": "returned_queries_only" if service == "search_console" else "returned_report",
        "canonical_activation": False,
        "limitations": [
            "Aggregate reports cannot fabricate customers, sessions, events or orders.",
            "Provider date boundaries are preserved; cross-source daily joins require review.",
            "Successful extraction does not certify completeness, attribution or causal effects.",
        ],
    }
    result["revision_id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=SERVICES)
    parser.add_argument("--account", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    temporary = None
    try:
        result = extract(args.service, args.account, args.start, args.end, max_pages=args.max_pages)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
        temporary.replace(args.output)
        print(
            json.dumps(
                {
                    "status": "staged",
                    "rows": len(result["rows"]),
                    "canonical_activation": False,
                    "revision_id": result["revision_id"],
                }
            )
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(
            '{"status":"error","message":"Extraction failed; no staged report published"}',
            file=sys.stderr,
        )
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
