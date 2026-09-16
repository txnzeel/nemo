"""Rule-based attribution with exact money conservation and explicit evidence limits."""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from html import escape
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.journeys import elapsed_us, instant
from nemo.journeys import report as journey_report
from nemo.warehouse import open_warehouse

WARNING = "Attribution is a model of credit assignment, not proof of causation."
MODELS = {
    "first_touch": "earliest touch receives 1",
    "last_touch": "latest touch receives 1; includes Direct",
    "linear": "each of n touches receives 1/n",
    "position_based": "n=1: 1; n=2: 1/2 each; n>=3: 2/5 endpoints, 1/[5(n-2)] interior",
    "time_decay": "normalize 2^(-elapsed_age/half_life); 50-digit Decimal; "
    "scores and normalized credit quantized to 1e-24",
}


def weights(model, touches, half_life_days=7):
    """Return exact normalized fractions; decay scores have declared numerical precision."""
    if model not in MODELS:
        raise ValueError("unknown attribution model")
    if type(half_life_days) is not int or not 1 <= half_life_days <= 3650:
        raise ValueError("half_life_days must be an integer from 1 through 3650")
    n = len(touches)
    if not n:
        return []
    if model == "first_touch":
        return [Fraction(i == 0) for i in range(n)]
    if model == "last_touch":
        return [Fraction(i == n - 1) for i in range(n)]
    if model == "linear" or (model == "position_based" and n <= 2):
        return [Fraction(1, n)] * n
    if model == "position_based":
        return [Fraction(2, 5), *([Fraction(1, 5 * (n - 2))] * (n - 2)), Fraction(2, 5)]
    latest = instant(touches[-1]["started_at"])
    with localcontext() as context:
        context.prec = 50
        denominator = Decimal(half_life_days * 86400 * 1000000)
        scores = [
            int(
                (
                    context.power(
                        Decimal(2),
                        -Decimal(elapsed_us(latest - instant(t["started_at"]))) / denominator,
                    )
                    * Decimal(10**24)
                ).to_integral_value(rounding=ROUND_HALF_UP)
            )
            for t in touches
        ]
    total = sum(scores)
    units = allocate(10**24, [Fraction(score, total) for score in scores])
    return [Fraction(unit, 10**24) for unit in units]


def allocate(amount, shares):
    """Conserve integer paise with largest remainders; input order resolves exact ties."""
    if type(amount) is not int or amount < 0:
        raise ValueError("amount must be nonnegative integer paise")
    if not shares or any(s < 0 for s in shares) or sum(shares) != 1:
        raise ValueError("shares must be nonnegative and sum to one")
    ideals = [amount * s for s in shares]
    floors = [x.numerator // x.denominator for x in ideals]
    priority = sorted(range(len(shares)), key=lambda i: (-(ideals[i] - floors[i]), i))
    for index in priority[: amount - sum(floors)]:
        floors[index] += 1
    return floors


def rational(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def report(warehouse: Path, *, lookback_days=30, half_life_days=7):
    # Validate before touching the warehouse.
    weights("linear", [], half_life_days)
    journeys = journey_report(warehouse, lookback_days=lookback_days)
    with open_warehouse(warehouse) as snapshot:
        if snapshot.manifest_sha256 != journeys["provenance"]["manifest_sha256"]:
            raise ValueError("warehouse changed during attribution; retry on a stable snapshot")
        amounts = dict(
            snapshot.connection.execute(
                "SELECT order_id, amount_paise FROM analytics.fct_orders"
            ).fetchall()
        )
    if set(amounts) != {j["order_id"] for j in journeys["journeys"]}:
        raise ValueError("journey/order population mismatch")
    models = {}
    for model in MODELS:
        channels = defaultdict(lambda: [Fraction(0), 0])
        campaigns = defaultdict(lambda: [Fraction(0), 0])
        orders = []
        for journey in journeys["journeys"]:
            oid = journey["order_id"]
            touches = journey["touches"]
            shares = weights(model, touches, half_life_days) if touches else [Fraction(1)]
            credits = allocate(amounts[oid], shares)
            allocations = []
            for touch, share, money in zip(touches or [None], shares, credits, strict=True):
                channel = touch["channel"] if touch else None
                campaign = touch["campaign_id"] if touch else None
                channels[channel][0] += share
                channels[channel][1] += money
                campaigns[(channel, campaign)][0] += share
                campaigns[(channel, campaign)][1] += money
                allocations.append(
                    {
                        "session_id": touch["session_id"] if touch else None,
                        "channel": channel,
                        "campaign_id": campaign,
                        "conversion_credit": rational(share),
                        "gross_merchandise_credit_paise": money,
                    }
                )
            orders.append(
                {
                    "order_id": oid,
                    "amount_paise": amounts[oid],
                    "status": "assigned" if touches else "unassigned_no_eligible_touch",
                    "history_boundary_limited": journey["history_boundary_limited"],
                    "timestamp_ties": journey["timestamp_ties"],
                    "purchase_session_in_window": journey["purchase_session_in_window"],
                    "allocations": allocations,
                }
            )
        models[model] = {
            "channels": [
                {
                    "channel": key,
                    "conversion_credit": rational(value[0]),
                    "gross_merchandise_credit_paise": value[1],
                }
                for key, value in sorted(
                    channels.items(), key=lambda x: (x[0] is not None, x[0] or "")
                )
            ],
            "campaigns": [
                {
                    "channel": key[0],
                    "campaign_id": key[1],
                    "conversion_credit": rational(value[0]),
                    "gross_merchandise_credit_paise": value[1],
                }
                for key, value in sorted(
                    campaigns.items(), key=lambda x: (x[0][0] or "", x[0][1] or "")
                )
            ],
            "orders": orders,
            "total_conversion_credit": rational(sum((v[0] for v in channels.values()), Fraction())),
            "total_gross_merchandise_credit_paise": sum(v[1] for v in channels.values()),
        }
    channel_keys = {row["channel"] for row in models["linear"]["channels"]}
    comparison = []
    for channel in sorted(channel_keys, key=lambda x: (x is not None, x or "")):
        values = {
            name: next(
                r["gross_merchandise_credit_paise"]
                for r in value["channels"]
                if r["channel"] == channel
            )
            for name, value in models.items()
        }
        comparison.append(
            {
                "channel": channel,
                "gross_merchandise_credit_paise": values,
                "model_range_paise": max(values.values()) - min(values.values()),
                "delta_from_last_touch_paise": {
                    name: value - values["last_touch"] for name, value in values.items()
                },
            }
        )
    return {
        "schema_version": "1",
        "claim_type": "attribution_result",
        "warning": WARNING,
        "dataset_id": journeys["dataset_id"],
        "source_mode": journeys["source_mode"],
        "window": journeys["window"],
        "journey_contract": journeys["contract"],
        "coverage": journeys["total"],
        "half_life_days": half_life_days,
        "money_contract": {
            "version": "1",
            "currency": "INR",
            "unit": "integer_paise",
            "basis": "paid_tax_exclusive_gross_merchandise_before_refunds",
            "allocation": "per_order_per_touch_largest_remainder_ties_in_journey_order",
            "empty_path": "all_conversion_and_money_credit_to_null_unassigned_bucket",
            "conversion_credit": "exact_rational_order_equivalents_not_distinct_customers",
        },
        "model_contracts": [
            {"name": name, "version": "1", "claim_type": "attribution_result", "formula": formula}
            for name, formula in MODELS.items()
        ],
        "total": {"paid_orders": len(amounts), "gross_merchandise_paise": sum(amounts.values())},
        "models": models,
        "channel_comparison": comparison,
        "provenance": {
            "journeys": journeys["provenance"],
            "attribution_code_sha256": hashlib.sha256(
                files("nemo").joinpath("attribution.py").read_bytes()
            ).hexdigest(),
        },
        "limitations": journeys["limitations"]
        + [
            WARNING,
            "Model disagreement is assumption sensitivity, not statistical uncertainty.",
            "Credit is gross merchandise before refunds, not profit or incremental value.",
            "No tracking completeness, attribution accuracy or recommendation gate is certified.",
            "Paise are apportioned per touch before channel/campaign aggregation.",
            "Time-decay scores and credit use 1e-24 resolution; tiny weights may be zero.",
            "No ROAS, CAC, causal estimate or budget recommendation is produced.",
        ],
    }


def rupees(paise):
    return f"{paise // 100:,}.{paise % 100:02d}"


def render_html(result):
    """Standalone comparison; source labels are escaped and no script is embedded."""
    headers = "".join(f"<th>{escape(name.replace('_', ' ').title())}</th>" for name in MODELS)
    rows = []
    for row in result["channel_comparison"]:
        values = row["gross_merchandise_credit_paise"]
        cells = "".join(f"<td>{rupees(values[name])}</td>" for name in MODELS)
        label = "Unassigned (no eligible touch)" if row["channel"] is None else row["channel"]
        rows.append(
            f"<tr><th>{escape(label)}</th>{cells}"
            f"<td class='range'>{rupees(row['model_range_paise'])}</td></tr>"
        )
    coverage = result["coverage"]
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>NEMO Attribution Lab</title>
<style>
body {{font:16px system-ui,sans-serif; margin:2rem; color:#192c3b; background:#f5f8fa}}
main {{max-width:1200px;margin:auto}} h1 {{margin-bottom:.4rem}}
.warning {{border-left:5px solid #c47900;background:#fff3d8;padding:1rem;font-weight:600}}
table {{border-collapse:collapse;width:100%;background:white}}
th,td {{padding:.8rem;border-bottom:1px solid #dce4ea;text-align:right}}
th:first-child {{text-align:left}} .range {{background:#e6eefb;font-weight:bold}}
.scroll {{overflow:auto}} small {{color:#465b6d}} li {{margin:.5rem 0}}
</style><main>
<h1>NEMO · Attribution Lab</h1>
<p class="warning">{escape(WARNING)}</p>
<p>Dataset: {escape(result["dataset_id"])} · Source label: {escape(result["source_mode"])}
 · Lookback: {result["journey_contract"]["lookback_days"]} days
 · Decay half-life: {result["half_life_days"]} days</p>
<p><b>{result["total"]["paid_orders"]:,} paid orders</b> ·
INR {rupees(result["total"]["gross_merchandise_paise"])} gross merchandise receipts</p>
<h2>Same observations, different credit rules</h2>
<p>Amounts below are INR, before refunds. The highlighted range is maximum minus minimum
credit across models; it is sensitivity to assumptions, not a confidence interval.</p>
<div class="scroll"><table><thead><tr><th>Channel</th>{headers}<th>Model range</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<h2>Read before interpreting</h2>
<ul><li>{coverage["history_boundary_limited_orders"]:,} windows extend before supplied history;
{coverage["timestamp_tie_orders"]:,} have tied session timestamps;
{coverage["zero_touch_orders"]:,} have no eligible touch.</li>
<li>Identity uses supplied customer IDs. Missing devices, offline activity and tracking
gaps remain unknown. Equal-time sessions use a lexical tie-break, not inferred chronology.</li>
<li>Position based: 40/20/40 for three or more touches; one touch 100%, two touches 50/50.
Time decay uses elapsed time and normalized half-life weights.</li>
<li>First/last touch use observed session order and include Direct. Repeated channels
receive summed touch credit. Exact paise allocation can affect small totals.</li>
<li>These are attribution results, not causal lift, profit, ROAS or budget
recommendations.</li></ul>
<small>Contract version 1. Source and method fingerprints, per-order allocations and
exact conversion-credit fractions are in the companion JSON report.</small>
</main></html>"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO Attribution Lab: " + WARNING)
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--half-life-days", type=int, default=7)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args(argv)
    try:
        outputs = [p for p in (args.output, args.html) if p is not None]
        if len({p.resolve() for p in outputs}) != len(outputs) or any(p.exists() for p in outputs):
            raise ValueError("output paths must be distinct and must not already exist")
        result = report(
            args.warehouse, lookback_days=args.lookback_days, half_life_days=args.half_life_days
        )
        encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
        else:
            sys.stdout.write(encoded)
        if args.html:
            with args.html.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(render_html(result))
        return 0
    except (ValueError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
