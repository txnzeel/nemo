"""Authoritative acquisition metric registry; ratios reference summed SQL facts."""

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

DIMENSIONS = ("business_date", "channel", "campaign_id", "device")
FACTS = (
    "impressions",
    "clicks",
    "spend_paise",
    "ad_rows",
    "sessions",
    "purchasing_sessions",
    "orders",
    "revenue_paise",
    "new_customers",
    "paid_orders",
    "paid_new_customers",
    "paid_revenue_paise",
)


@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    numerator: str
    denominator: str | None
    unit: str
    sources: tuple[str, ...]
    limitations: str
    paid_only: bool = False
    version: str = "1"
    claim_type: str = "descriptive_metric"
    grain: str = "Selected reporting interval and dimension combination"
    dimensions: tuple[str, ...] = DIMENSIONS
    freshness_requirement: str = (
        "Snapshot must cover the report window; ingestion freshness is not assessed in M2."
    )

    def definition(self) -> dict:
        result = asdict(self)
        result["formula"] = (
            f"{self.numerator} / {self.denominator}" if self.denominator else self.numerator
        )
        return result

    def evaluate(self, facts: dict[str, int]) -> dict:
        reason = None
        numerator = facts.get(self.numerator)
        denominator = facts.get(self.denominator) if self.denominator else None
        if self.name == "cac":
            reason = "missing_full_acquisition_costs"
        elif self.paid_only and facts["ad_rows"] == 0:
            reason = "no_paid_ad_observations_in_scope"
        elif self.denominator and denominator == 0:
            reason = "zero_denominator"
        if reason:
            value = None
        elif self.denominator:
            with localcontext() as context:
                context.prec = 50
                value = format(
                    (Decimal(numerator) / Decimal(denominator)).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    ),
                    "f",
                )
        else:
            value = numerator
        return {
            "value": value,
            "unit": self.unit,
            "reason": reason,
            "numerator": numerator,
            "denominator": denominator,
            "definition_version": self.version,
        }


ADS = ("ad_performance",)
SESSIONS = ("sessions",)
ORDERS = ("sessions", "orders")
CREDIT = "Purchase-session credit is descriptive, not causal or platform attribution."
REGISTRY = (
    Metric(
        "impressions",
        "Recorded paid ad displays",
        "impressions",
        None,
        "count",
        ADS,
        "Coverage is limited to supplied paid-media observations.",
        paid_only=True,
    ),
    Metric(
        "clicks",
        "Recorded paid ad clicks",
        "clicks",
        None,
        "count",
        ADS,
        "A click need not create a session.",
        paid_only=True,
    ),
    Metric(
        "spend",
        "Paid media spend",
        "spend_paise",
        None,
        "paise",
        ADS,
        "Excludes non-media acquisition costs.",
        paid_only=True,
    ),
    Metric(
        "sessions",
        "Sessions started in the window",
        "sessions",
        None,
        "count",
        SESSIONS,
        "Session-start cohort, not ad clicks.",
    ),
    Metric(
        "purchasing_sessions",
        "In-window sessions with a paid order before report end",
        "purchasing_sessions",
        None,
        "count",
        ORDERS,
        "Distinct sessions; recent sessions have less follow-up.",
    ),
    Metric(
        "orders",
        "Paid orders with payment in the window",
        "orders",
        None,
        "count",
        ORDERS,
        "Repeat purchases count; failed payments do not.",
    ),
    Metric(
        "conversions",
        "Purchase conversions (alias of paid order count)",
        "orders",
        None,
        "count",
        ORDERS,
        "This conversion definition is a paid purchase, not a visitor or lead.",
    ),
    Metric(
        "revenue",
        "Paid merchandise sales before refunds",
        "revenue_paise",
        None,
        "paise",
        ORDERS,
        "Tax-exclusive; ignores refunds, fees and costs; not profit.",
    ),
    Metric(
        "new_customers",
        "First-observed paying customers",
        "new_customers",
        None,
        "count",
        ORDERS,
        "Earlier history may be missing; not necessarily lifetime first purchase.",
    ),
    Metric(
        "ctr",
        "Paid click-through rate",
        "clicks",
        "impressions",
        "fraction",
        ADS,
        "A ratio of sums, not the mean campaign CTR.",
        paid_only=True,
    ),
    Metric(
        "cpc",
        "Average paid click cost",
        "spend_paise",
        "clicks",
        "paise_per_click",
        ADS,
        "Cheap clicks need not produce valuable purchases.",
        paid_only=True,
    ),
    Metric(
        "cvr",
        "Session purchase conversion rate",
        "purchasing_sessions",
        "sessions",
        "fraction",
        ORDERS,
        "Session-start cohort observed by report end; not click-based CVR.",
    ),
    Metric(
        "cpa",
        "Media cost per paid-session purchase",
        "spend_paise",
        "paid_orders",
        "paise_per_purchase",
        ADS + ORDERS,
        CREDIT,
        paid_only=True,
    ),
    Metric(
        "media_cac",
        "Media cost per first-observed paid-session buyer",
        "spend_paise",
        "paid_new_customers",
        "paise_per_customer",
        ADS + ORDERS,
        "Excludes sales/marketing overhead; first observed is not first-ever. " + CREDIT,
        paid_only=True,
    ),
    Metric(
        "cac",
        "Full customer acquisition cost",
        "full_acquisition_cost_paise",
        "new_customers",
        "paise_per_customer",
        ("sales_marketing_costs",) + ORDERS,
        "Unavailable: full sales and marketing costs are not supplied.",
    ),
    Metric(
        "roas",
        "Reported paid-session revenue / paid media spend",
        "paid_revenue_paise",
        "spend_paise",
        "multiple",
        ADS + ORDERS,
        "Before refunds, not profit, not incremental return. " + CREDIT,
        paid_only=True,
    ),
)
