"""Export ONLY explicitly public lab reports for the credential-free UI preview."""

import json
from datetime import date
from pathlib import Path

from nemo.decision_case import build_case
from nemo.integrity import assess
from nemo.opportunities import report

d = Path("web/demo")
d.mkdir(exist_ok=True)
datasets = []
for kind, label in [
    ("business", "Payment-stage review"),
    ("healthy", "Healthy baseline"),
    ("failure", "Measurement issue"),
]:
    source = Path(f"artifacts/milestone-5/{kind}")
    case = build_case(
        source / "nemo.duckdb",
        source / "observations",
        baseline_start=date(2026, 6, 3),
        current_start=date(2026, 6, 17),
    )
    assert case["scope"]["mode"] == "synthetic", "Only lab evidence may be exported"
    values = {
        "decision-case": case,
        "measurement-health": assess(source / "observations"),
        "opportunities": report(
            source / "nemo.duckdb",
            source / "observations",
            baseline_start=date(2026, 6, 3),
            current_start=date(2026, 6, 17),
        ),
        "decisions": {"schema_version": "1", "decisions": [], "events": []},
    }
    datasets.append(
        {
            "id": kind,
            "label": label,
            "origin": "synthetic_lab",
            "capabilities": {"decision_case": True, "ledger": True},
            "delivery": "public_lab_export",
        }
    )
    for name, value in values.items():
        (d / f"{kind}-{name}.json").write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
(d / "datasets.json").write_text(json.dumps({"datasets": datasets}, indent=2) + "\n")
print("Exported three public lab report sets; no source rows or private truth copied.")
