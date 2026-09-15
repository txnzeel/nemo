"""Descriptive buyer cohorts, retention and scoped contribution from canonical inputs."""

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.economics_inputs import COST_COMPONENTS, load_inputs
from nemo.warehouse import open_warehouse, project_hash

METRICS = [
    {
        "name": "first_observed_buyers",
        "formula": "count of customers with purchase_rank = 1",
        "unit": "buyers",
        "grain": "supplied history and first-purchase dimensions",
        "requires": ["orders", "sessions"],
        "limitation": "Not first-ever or causal acquisition.",
    },
    {
        "name": "monthly_purchase_retention",
        "formula": "active cohort buyers / original cohort buyers",
        "unit": "fraction",
        "grain": "cohort month x calendar age month",
        "requires": ["orders"],
        "limitation": "Only completed months; not continuous or rolling retention.",
    },
    {
        "name": "observed_repeat_buyer_rate",
        "formula": "buyers with >= 2 orders / all buyers",
        "unit": "fraction",
        "grain": "supplied history",
        "requires": ["orders"],
        "limitation": "Follow-up differs across cohorts.",
    },
    {
        "name": "historical_net_value",
        "formula": "net merchandise receipts / all cohort buyers",
        "unit": "paise_per_buyer",
        "grain": "cohort through observation cutoff",
        "requires": ["orders", "order_items", "refunds", "refund_coverage_contract"],
        "limitation": "Not predicted lifetime value, profit or incremental impact.",
    },
    {
        "name": "contribution_paise",
        "formula": "gross merchandise - merchandise refunds - declared order-variable costs",
        "unit": "paise",
        "grain": "customer or cohort through cutoff",
        "requires": ["orders", "refund_coverage_contract", "order_variable_costs"],
        "limitation": "Before acquisition costs and fixed overhead; not company profit.",
    },
]


def ratio(numerator, denominator):
    if numerator is None or denominator == 0:
        return {"numerator": numerator, "denominator": denominator, "value": None}
    with localcontext() as context:
        context.prec = 50
        value = (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    return {"numerator": numerator, "denominator": denominator, "value": format(value, "f")}


def rows(cursor):
    columns = [item[0] for item in cursor.description]
    return [
        {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in zip(columns, row, strict=True)
        }
        for row in cursor.fetchall()
    ]


def report(warehouse: Path, observations: Path, *, max_age: int = 12):
    if type(max_age) is not int or not 0 <= max_age <= 120:
        raise ValueError("max_age must be an integer from 0 through 120")
    with (
        open_warehouse(warehouse) as snapshot,
        tempfile.TemporaryDirectory(prefix="nemo-economics-") as temporary,
    ):
        inputs = load_inputs(snapshot, observations)
        parameters = {
            "refunds_complete": inputs["refunds_complete"],
        }
        for table in ("refunds", "costs"):
            path = Path(temporary) / f"{table}.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in inputs[table]), encoding="utf-8"
            )
            parameters[table] = str(path)
        sql = files("nemo").joinpath("economics.sql").read_text(encoding="utf-8")
        customers = rows(snapshot.connection.execute(sql + " ORDER BY customer_id", parameters))

        def aggregate(dimensions):
            columns = ", ".join(dimensions)
            prefix = columns + ", " if dimensions else ""
            suffix = f" GROUP BY {columns} ORDER BY {columns}" if dimensions else ""
            query = f"""
                SELECT {prefix}count(*) AS buyers,
                       count(*) FILTER (WHERE paid_orders >= 2) AS repeat_buyers,
                       coalesce(sum(paid_orders), 0) AS paid_orders,
                       coalesce(sum(gross_merchandise_paise), 0) AS gross_merchandise_paise,
                       coalesce(sum(cost_covered_orders), 0) AS cost_covered_orders,
                       CASE WHEN $refunds_complete THEN coalesce(sum(refunds_paise), 0)
                            END AS refunds_paise,
                       CASE WHEN $refunds_complete THEN coalesce(sum(net_merchandise_paise), 0)
                            END AS net_merchandise_paise,
                       CASE WHEN $costs_declared AND count(variable_cost_paise) = count(*)
                            THEN coalesce(sum(variable_cost_paise), 0) END AS variable_cost_paise,
                       CASE WHEN $refunds_complete AND $costs_declared
                                 AND count(contribution_paise) = count(*)
                            THEN coalesce(sum(contribution_paise), 0) END AS contribution_paise
                FROM ({sql}) customer_values{suffix}
            """
            results = rows(
                snapshot.connection.execute(
                    query, {**parameters, "costs_declared": inputs["costs_declared"]}
                )
            )
            for row in results:
                row["repeat_buyer_rate"] = ratio(row["repeat_buyers"], row["buyers"])
                row["historical_net_value_paise_per_buyer"] = ratio(
                    row["net_merchandise_paise"], row["buyers"]
                )
                row["contribution_paise_per_buyer"] = ratio(
                    row["contribution_paise"], row["buyers"]
                )
            return results

        retention_sql = files("nemo").joinpath("retention.sql").read_text(encoding="utf-8")
        retention = rows(
            snapshot.connection.execute(retention_sql, {"cutoff": snapshot.end, "max_age": max_age})
        )
        for row in retention:
            if row["observation_status"] == "not_yet_observed":
                row["observed_active_buyers"] = None
            numerator = (
                row["observed_active_buyers"] if row["observation_status"] == "complete" else None
            )
            row["retention"] = ratio(numerator, row["buyers"])
        result = {
            "report_version": "1",
            "claim_type": "descriptive_metric",
            "mode": snapshot.contract.mode,
            "dataset_id": snapshot.contract.dataset_id,
            "history_start": snapshot.start.isoformat(),
            "cutoff_exclusive": snapshot.end.isoformat(),
            "business_timezone": "Asia/Kolkata",
            "currency": "INR",
            "money_unit": "paise",
            "cost_scope": "Order contribution before acquisition costs and fixed overhead",
            "cost_components": list(COST_COMPONENTS),
            "coverage": {
                "refunds_complete": inputs["refunds_complete"],
                "costs_declared": inputs["costs_declared"],
                "cost_provenance": inputs["cost_provenance"],
                "contract": inputs["contract"],
            },
            "metric_contracts": [
                {**m, "version": "1", "claim_type": "descriptive_metric"} for m in METRICS
            ],
            "total": aggregate(())[0],
            "acquisition": aggregate(("acquisition_channel", "acquisition_campaign_id")),
            "cohorts": aggregate(("cohort_month",)),
            "customers": customers,
            "retention": retention,
            "max_age_months": max_age,
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "tables": snapshot.table_hashes | inputs["source_hashes"],
                "dbt_project_sha256": project_hash(),
                "code_sha256": {
                    name: hashlib.sha256(files("nemo").joinpath(name).read_bytes()).hexdigest()
                    for name in (
                        "economics.py",
                        "economics_inputs.py",
                        "economics.sql",
                        "retention.sql",
                    )
                },
            },
            "limitations": [
                "First observed acquisition is left-censored and not causal attribution.",
                "Historical values have unequal follow-up and are not lifetime forecasts.",
                "Incomplete retention months are unknown; completed inactive months are zero.",
                "Missing refund or cost coverage propagates unknown rather than assumed zero.",
                "Cost provenance is asserted; synthetic assumptions are not company evidence.",
                "Contribution excludes acquisition costs and fixed overhead and is not profit.",
                "Full CAC and incremental economics remain unassessed.",
                "Refunds/corrections can restate values; no arrival-as-of history.",
            ],
        }
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO historical customer economics")
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--max-age", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = report(args.warehouse, args.observations, max_age=args.max_age)
        encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
        else:
            sys.stdout.write(encoded)
        return 0
    except (ValueError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
