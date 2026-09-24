"""Source-neutral paid/organic query review; no causal or execution claims."""

import argparse
import json
import sqlite3
import sys
import unicodedata
from datetime import date
from importlib.resources import files
from pathlib import Path

from nemo.economics_inputs import read_table
from nemo.experiment_design import digest, encode
from nemo.observations import _integer, _text, open_snapshot


def normalize(query):
    return " ".join(unicodedata.normalize("NFKC", query).casefold().split())


def ratio(numerator, denominator):
    return None if denominator == 0 else {"numerator": numerator, "denominator": denominator}


def _contract(manifest):
    contract = manifest.get("search_contract")
    if not isinstance(contract, dict) or contract.get("version") != "1":
        raise ValueError("search rows require search_contract version 1")
    for key in ("scope", "brand_classification", "coverage"):
        _text(contract, key)
    if contract["coverage"] not in ("returned_queries", "complete_queries"):
        raise ValueError("invalid query coverage")
    if type(contract.get("conversions_complete")) is not bool:
        raise ValueError("conversions_complete must be explicit")
    if contract["conversions_complete"]:
        for key in ("conversion_definition", "conversion_window"):
            _text(contract, key)
    return contract


def _rows(snapshot, manifest, source):
    rows = read_table(source, manifest, "search_performance")
    if rows is None:
        if "search_contract" in manifest:
            raise ValueError("declared search contract requires search_performance")
        return None, None
    contract = _contract(manifest)
    campaigns = {
        row[0]
        for row in snapshot.connection.execute("select campaign_id from campaigns where is_paid")
    }
    seen = set()
    for row in rows:
        surface = row.get("surface")
        query = _text(row, "query")
        day = date.fromisoformat(_text(row, "business_date"))
        if not normalize(query) or query != normalize(query):
            raise ValueError("query must be normalized")
        if surface not in ("paid", "organic") or row.get("device") not in snapshot.contract.devices:
            raise ValueError("invalid search surface/device")
        if not snapshot.start <= day < snapshot.end:
            raise ValueError("search date outside snapshot")
        grain = (day, surface, query, row["device"])
        if grain in seen:
            raise ValueError("duplicate search grain")
        seen.add(grain)
        if row.get("brand_segment") not in ("brand", "nonbrand", "unknown"):
            raise ValueError("invalid brand segment")
        impressions, clicks = _integer(row, "impressions"), _integer(row, "clicks")
        if clicks > impressions:
            raise ValueError("search clicks exceed impressions")
        for key in ("campaign_ids", "keywords", "landing_pages"):
            values = row.get(key)
            if (
                not isinstance(values, list)
                or any(not isinstance(v, str) or not v for v in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError(f"invalid {key}")
        if surface == "paid":
            _integer(row, "spend_paise")
            if not row["campaign_ids"] or not set(row["campaign_ids"]) <= campaigns:
                raise ValueError("unknown paid campaign")
            if row.get("position_sum_micros") is not None:
                raise ValueError("paid rank is unsupported")
            if contract["conversions_complete"]:
                _integer(row, "reported_conversions")
            elif row.get("reported_conversions") is not None:
                raise ValueError("conversions require complete declared reporting")
        else:
            if row["campaign_ids"] or row["keywords"]:
                raise ValueError("organic rows cannot contain paid campaign/keywords")
            if row.get("spend_paise") is not None or row.get("reported_conversions") is not None:
                raise ValueError("organic spend/conversions must be unknown")
            position = _integer(row, "position_sum_micros")
            if (impressions == 0 and position != 0) or position < impressions * 1_000_000:
                raise ValueError("invalid weighted organic position")
    return rows, contract


def report(
    observations, *, min_spend_paise=100000, min_paid_clicks=30, min_organic_impressions=1000
):
    source = Path(observations)
    thresholds = {
        "min_spend_paise": min_spend_paise,
        "min_paid_clicks": min_paid_clicks,
        "min_organic_impressions": min_organic_impressions,
    }
    for key in thresholds:
        if _integer(thresholds, key) == 0:
            raise ValueError("review thresholds must be positive")
    with open_snapshot(source) as snapshot:
        payload = (source / "manifest.json").read_bytes()
        if digest(payload) != snapshot.manifest_sha256:
            raise ValueError("snapshot changed during read")
        manifest = json.loads(payload)
        rows, contract = _rows(snapshot, manifest, source)
        groups = {}
        for row in rows or []:
            key = (row["query"], row["device"])
            group = groups.setdefault(key, {"paid": [], "organic": []})
            group[row["surface"]].append(row)
        results, reviews = [], []
        for (query, device), group in sorted(groups.items()):
            item = {"query": query, "device": device}
            labels = {r["brand_segment"] for rs in group.values() for r in rs}
            item["brand_segment"] = next(iter(labels)) if len(labels) == 1 else "mixed"
            for surface, values in group.items():
                impressions = sum(r["impressions"] for r in values)
                clicks = sum(r["clicks"] for r in values)
                stats = {
                    "rows": len(values),
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": ratio(clicks, impressions),
                    "campaign_ids": sorted({v for r in values for v in r["campaign_ids"]}),
                    "keywords": sorted({v for r in values for v in r["keywords"]}),
                    "landing_pages": sorted({v for r in values for v in r["landing_pages"]}),
                }
                if surface == "paid":
                    spend = sum(r["spend_paise"] for r in values)
                    stats.update(
                        spend_paise=spend,
                        cpc_paise=ratio(spend, clicks),
                        reported_conversions=sum(r["reported_conversions"] for r in values)
                        if contract["conversions_complete"] and values
                        else None,
                    )
                else:
                    stats["mean_position"] = ratio(
                        sum(r["position_sum_micros"] for r in values), impressions * 1_000_000
                    )
                item[surface] = stats
            paid, organic = item["paid"], item["organic"]
            shared = sorted(
                {r["business_date"] for r in group["paid"] if r["impressions"]}
                & {r["business_date"] for r in group["organic"] if r["impressions"]}
            )
            item["overlap_dates"] = shared
            reasons = []
            if (
                paid["spend_paise"] >= min_spend_paise
                and paid["clicks"] >= min_paid_clicks
                and paid["reported_conversions"] == 0
            ):
                reasons.append("review_intent_and_negative_keyword_candidate")
            if (
                organic["impressions"] >= min_organic_impressions
                and organic["clicks"] * 100 < organic["impressions"] * 2
            ):
                reasons.append("review_organic_intent_snippet_and_rank")
            if shared:
                reasons.append("test_paid_organic_cannibalization_hypothesis")
            if reasons:
                reviews.append(
                    {
                        "query": query,
                        "device": device,
                        "claim_type": "diagnostic_hypothesis",
                        "reasons": reasons,
                        "action": "manual_review_only",
                        "incremental_value_paise": None,
                    }
                )
            results.append(item)
        result = {
            "schema_version": "1",
            "claim_type": "descriptive_search_measurement",
            "status": "measured" if rows else "not_assessed",
            "scope": {
                "dataset_id": snapshot.contract.dataset_id,
                "mode": snapshot.contract.mode,
                "start": snapshot.start.isoformat(),
                "end_exclusive": snapshot.end.isoformat(),
            },
            "contract": contract,
            "thresholds": thresholds,
            "queries": results,
            "reviews": reviews,
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "search_sha256": manifest["tables"].get("search_performance", {}).get("sha256"),
                "code_sha256": digest(
                    files("nemo").joinpath("search_intelligence.py").read_bytes()
                ),
            },
            "limitations": [
                "Returned queries may omit privacy-filtered traffic; absent rows are not zero.",
                "Source-reported conversions are not canonical orders or incremental outcomes.",
                "Keyword/page lists do not allocate query totals to their members.",
                "Overlap is a hypothesis; no causal cannibalization or profit is established.",
                "Review thresholds are heuristics, not validated economic recommendations.",
            ],
        }
        result["revision_id"] = digest(encode(result))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report(args.observations)
        with args.output.open("xb") as stream:
            stream.write(encode(result))
        print(json.dumps({"status": result["status"], "output": str(args.output)}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
