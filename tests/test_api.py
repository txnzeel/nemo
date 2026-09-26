"""Local API contract, authorization and canonical service parity."""

import copy

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_budget_studio import specification
from test_experiments import make_manual
from test_forecasting import baseline as scenario_baseline

from nemo.api import create_app
from nemo.decision_case import build_case
from nemo.experiment_design import encode
from nemo.warehouse import build_warehouse

READ = "test-reader-" + "r" * 32
WRITE = "test-writer-" + "w" * 32
RH = {"Authorization": "Bearer " + READ}
WH = {"Authorization": "Bearer " + WRITE}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    make_manual(root)
    db = root / "verified.duckdb"
    build_warehouse(root / "observations", db)
    config = [
        {
            "id": "manual",
            "label": "Canonical example",
            "observations": "observations",
            "warehouse": "verified.duckdb",
            "ledger": "decisions.sqlite",
            "experiment_plan": "plan.json",
            "baseline_start": "2025-01-01",
            "current_start": "2025-01-05",
        }
    ]
    return root, config


@pytest.fixture
def client(data):
    root, config = data
    with TestClient(create_app(root, config, read_token=READ, write_token=WRITE)) as client:
        yield client


def test_authentication_and_safe_catalog(client, data):
    assert client.get("/health").status_code == 200
    assert client.get("/datasets").status_code == 401
    assert client.get("/datasets", headers={"Authorization": "Bearer wrong"}).status_code == 401
    response = client.get("/datasets", headers=RH)
    assert response.status_code == 200
    assert response.json()["datasets"][0]["id"] == "manual"
    assert str(data[0]) not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers["x-request-id"]) == 32
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/openapi.json", headers=RH).status_code == 200
    assert client.get("/sql", headers=WH).status_code == 404


def test_case_and_canonical_metric_parity(client, data):
    root, config = data
    from datetime import date

    expected = build_case(
        root / "verified.duckdb",
        root / "observations",
        baseline_start=date(2025, 1, 1),
        current_start=date(2025, 1, 5),
    )
    case = client.get("/datasets/manual/decision-case", headers=RH)
    assert case.status_code == 200
    import json

    assert case.json() == json.loads(encode(expected))
    metrics = client.get("/datasets/manual/acquisition", headers=RH)
    assert metrics.status_code == 200
    assert str(root) not in metrics.text
    assert client.get("/datasets/manual/measurement-health", headers=RH).status_code == 200


@pytest.mark.parametrize(
    "route",
    [
        "opportunities",
        "experiments",
        "customers",
        "journeys",
        "attribution",
        "search",
        "forecast",
        "response-curves",
        "retention?baseline=2025-01-01&as_of=2025-01-09",
    ],
)
def test_supported_read_services(client, route):
    response = client.get("/datasets/manual/" + route, headers=RH)
    assert response.status_code == 200, response.text


def test_invalid_requests_do_not_echo_data(client):
    response = client.post("/scenarios", headers=RH, json={"baseline": "private-secret-content"})
    assert response.status_code == 422
    assert "private-secret-content" not in response.text
    assert client.get("/datasets/manual/forecast?horizon=100", headers=RH).status_code == 422
    assert client.get("/datasets/unknown/acquisition", headers=RH).status_code == 404
    value = client.post(
        "/scenarios", headers=RH, json={"baseline": scenario_baseline(), "changes": {}}
    )
    assert value.status_code == 200
    assert value.json()["claim_type"] == "conditional_scenario"
    failed = client.post("/datasets/manual/optimization", headers=RH, json=specification())
    assert failed.status_code == 422


def test_ledger_roles_retries_and_stale_versions(client):
    assert client.get("/datasets/manual/decisions", headers=RH).status_code == 200
    board = client.get("/datasets/manual/opportunities", headers=RH).json()
    opportunity = board["opportunities"][0]["opportunity_id"]
    body = {
        "opportunity_id": opportunity,
        "request_id": "api-import",
        "rationale": "Review observed evidence",
    }
    assert client.post("/datasets/manual/decisions", headers=RH, json=body).status_code == 403
    first = client.post("/datasets/manual/decisions", headers=WH, json=body)
    assert first.status_code == 200, first.text
    assert client.post("/datasets/manual/decisions", headers=WH, json=body).json() == first.json()
    decision = first.json()["decision"]
    url = "/datasets/manual/decisions/" + decision["decision_id"]
    patch = {
        "expected_version": 1,
        "request_id": "api-reject",
        "rationale": "No action selected",
        "changes": {"status": "rejected"},
    }
    updated = client.patch(url, headers=WH, json=patch)
    assert updated.status_code == 200, updated.text
    assert client.patch(url, headers=WH, json=patch).json() == updated.json()
    patch["request_id"] = "api-stale"
    assert client.patch(url, headers=WH, json=patch).status_code == 409
    events = client.get("/datasets/manual/decisions", headers=RH).json()["events"]
    assert all(e["command"]["actor"] == "local-api-operator" for e in events)


@pytest.mark.parametrize("path", ["../outside", "/etc", "private/run.json", ".tools/secret"])
def test_catalog_rejects_nonpublic_paths(data, path):
    root, config = data
    bad = copy.deepcopy(config)
    bad[0]["observations"] = path
    with pytest.raises(ValueError):
        create_app(root, bad, read_token=READ)


def test_duplicate_catalog_and_bad_tokens(data):
    root, config = data
    with pytest.raises(ValueError, match="unique"):
        create_app(root, config * 2, read_token=READ)
    with pytest.raises(ValueError, match="tokens"):
        create_app(root, config, read_token=READ, write_token=READ)


def test_oversized_body_rejected(client):
    response = client.post("/scenarios", headers=RH, content=b" " * 270000)
    assert response.status_code == 413


def test_streamed_body_limit(client):
    response = client.post("/scenarios", headers=RH, content=(b"x" * 90000 for _ in range(4)))
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


def test_symlink_cannot_expose_private_or_external_paths(tmp_path):
    from nemo.api import contained

    (tmp_path / "private").mkdir()
    link = tmp_path / "public"
    try:
        link.symlink_to(tmp_path / "private", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(ValueError, match="nonpublic"):
        contained(tmp_path, "public")
    link.unlink()
    link.symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        contained(tmp_path, "public")


def test_source_failure_is_sanitized(data):
    root, config = data
    bad = copy.deepcopy(config)
    bad[0]["warehouse"] = "missing-sensitive-name.duckdb"
    with TestClient(create_app(root, bad, read_token=READ)) as client:
        response = client.get("/datasets/manual/acquisition", headers=RH)
    assert response.status_code == 503
    assert "missing-sensitive-name" not in response.text
    assert str(root) not in response.text


def test_reader_only_configuration_cannot_write(data):
    root, config = data
    with TestClient(create_app(root, config, read_token=READ)) as client:
        response = client.post(
            "/datasets/manual/decisions",
            headers=RH,
            json={"opportunity_id": "unknown", "request_id": "reader-only", "rationale": "Review"},
        )
    assert response.status_code == 403


def test_exact_money_survives_http_json(client):
    baseline = scenario_baseline()
    baseline["merchandise_receipts_paise"] = 9007199254740993
    response = client.post("/scenarios", headers=RH, json={"baseline": baseline, "changes": {}})
    assert response.status_code == 200
    result = response.json()
    assert result["estimates"]["merchandise_receipts_paise"] == {
        "numerator": 9007199254740993,
        "denominator": 1,
    }
    assert result["incremental_profit_paise"] is None
