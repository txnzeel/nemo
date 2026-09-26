"""Authenticated local HTTP transport over existing canonical NEMO services."""

import argparse
import hmac
import json
import os
import sqlite3
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from nemo import (
    attribution,
    budget_studio,
    economics,
    experiments,
    forecasting,
    integrity,
    journeys,
    ledger,
    measurement,
    opportunities,
    response_curves,
    retention,
    search_intelligence,
)
from nemo.canonical import source_contract
from nemo.decision_case import build_case


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dataset(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=100)
    observations: str
    origin: Literal[
        "unverified_source", "manual_fixture", "synthetic_lab", "company_data_unverified"
    ] = "unverified_source"
    warehouse: str | None = None
    ledger: str | None = None
    experiment_plan: str | None = None
    baseline_start: date | None = None
    current_start: date | None = None


class Scenario(Model):
    baseline: dict[str, Any]
    changes: dict[str, Any]


class Budget(Model):
    period_days: StrictInt
    total_budget_paise: StrictInt
    step_paise: StrictInt
    experiment_reserve_paise: StrictInt
    channels: list[dict[str, Any]] = Field(min_length=1, max_length=12)


class ImportDecision(Model):
    opportunity_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=4000)


class UpdateDecision(Model):
    expected_version: StrictInt = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=4000)
    changes: dict[str, Any]


def contained(root, relative):
    path = Path(relative)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(
            part.casefold().startswith("private") or part in (".git", ".tools")
            for part in path.parts
        )
    ):
        raise ValueError("resource must be a public relative path")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("resource escapes configured root")
    if any(
        part.casefold().startswith("private") or part in (".git", ".tools")
        for part in resolved.relative_to(root).parts
    ):
        raise ValueError("resource resolves to a nonpublic path")
    return resolved


class BodyLimit:
    def __init__(self, app, limit=262144):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Enforce the actual streamed size before framework JSON parsing.
        # Retain at most limit bytes; Content-Length is not trusted.
        body = bytearray()
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await JSONResponse({"error": "request_too_large"}, status_code=413)(
                    scope, receive, send
                )
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        body = bytes(body)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(root, datasets, *, read_token, write_token=None):
    root = Path(root).resolve()
    if (
        not isinstance(read_token, str)
        or len(read_token) < 32
        or (
            write_token is not None
            and (
                not isinstance(write_token, str)
                or len(write_token) < 32
                or write_token == read_token
            )
        )
    ):
        raise ValueError("distinct service tokens must contain at least 32 characters")
    parsed = [Dataset.model_validate(row) for row in datasets]
    catalog = {row.id: row for row in parsed}
    if len(catalog) != len(parsed) or not catalog:
        raise ValueError("dataset IDs must be unique and nonempty")
    ledgers = set()
    for row in parsed:
        for name in ("observations", "warehouse", "ledger", "experiment_plan"):
            value = getattr(row, name)
            if value is not None:
                resolved = contained(root, value)
                if name == "ledger":
                    if resolved in ledgers:
                        raise ValueError("datasets must not share a ledger")
                    ledgers.add(resolved)
        if (row.baseline_start is None) != (row.current_start is None):
            raise ValueError("case dates must be configured together")
    app = FastAPI(
        title="NEMO Evidence API", version="1", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(BodyLimit)
    bearer = HTTPBearer(auto_error=False)

    def role(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        value = credentials.credentials.encode() if credentials else b""
        if write_token and hmac.compare_digest(value, write_token.encode()):
            return "writer"
        if hmac.compare_digest(value, read_token.encode()):
            return "reader"
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})

    def writer(access: Annotated[str, Depends(role)]):
        if access != "writer":
            raise HTTPException(403, "Write role required")
        return "local-api-operator"

    def dataset(dataset_id):
        if dataset_id not in catalog:
            raise HTTPException(404, "Dataset not found")
        return catalog[dataset_id]

    def resource(row, name):
        value = getattr(row, name)
        if value is None:
            raise HTTPException(409, f"{name} is not configured for this dataset")
        path = contained(root, value)
        if name == "observations":
            # Nested public files must not redirect outside the configured source.
            manifest = contained(root, str((path / "manifest.json").relative_to(root)))
            if not manifest.is_relative_to(path):
                raise ValueError("manifest escapes observations")
            for child in path.glob("*.jsonl"):
                if not child.resolve().is_relative_to(path):
                    raise ValueError("observation table escapes source")
        return path

    def dates(row):
        if row.baseline_start is None:
            raise HTTPException(409, "Comparison dates are not configured")
        return {"baseline_start": row.baseline_start, "current_start": row.current_start}

    def board(row):
        return opportunities.report(
            resource(row, "warehouse"),
            resource(row, "observations"),
            **(dates(row) if row.baseline_start else {}),
            experiment_plan=resource(row, "experiment_plan") if row.experiment_plan else None,
        )

    def history(row):
        path = resource(row, "ledger")
        result = (
            ledger.read(path)
            if path.exists()
            else {"schema_version": "1", "decisions": [], "events": []}
        )
        contract = source_contract(
            json.loads((resource(row, "observations") / "manifest.json").read_bytes())
        )
        for state in result["decisions"]:
            scope = state["evidence_available"]["scope"]
            if scope["dataset_id"] != contract.dataset_id or scope["source_mode"] != contract.mode:
                raise ValueError("ledger source does not match configured dataset")
        return result

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Do not echo submitted bodies, tokens, customer data or raw paths.
        return JSONResponse(
            {"error": "invalid_request", "request_id": request.state.request_id}, status_code=422
        )

    async def service_error(request, error):
        conflict = isinstance(error, ValueError) and (
            str(error).startswith("stale or invalid expected version")
            or str(error).startswith("request ID reused")
        )
        status = (
            409
            if conflict
            else 422
            if isinstance(error, (ValueError, TypeError, KeyError))
            else 503
        )
        return JSONResponse(
            {
                "error": "conflict" if conflict else "service_input_or_source_unavailable",
                "request_id": request.state.request_id,
            },
            status_code=status,
        )

    for kind in (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        duckdb.Error,
    ):
        app.add_exception_handler(kind, service_error)

    @app.get("/health")
    def health():
        return {"status": "ok", "api_version": "1", "deployment": "local_service"}

    @app.get("/openapi.json", dependencies=[Depends(role)])
    def openapi():
        return app.openapi()

    @app.get("/datasets", dependencies=[Depends(role)])
    def datasets_index():
        return {
            "datasets": [
                {
                    "id": row.id,
                    "label": row.label,
                    "origin": row.origin,
                    "capabilities": {
                        "warehouse": row.warehouse is not None,
                        "decision_case": row.baseline_start is not None
                        and row.warehouse is not None,
                        "ledger": row.ledger is not None,
                        "experiment": row.experiment_plan is not None,
                    },
                }
                for row in parsed
            ]
        }

    @app.get("/metrics", dependencies=[Depends(role)])
    def metrics():
        return {"registry": measurement.registry()}

    @app.get("/datasets/{dataset_id}/measurement-health", dependencies=[Depends(role)])
    def measurement_health(dataset_id: str):
        return integrity.assess(resource(dataset(dataset_id), "observations"))

    @app.get("/datasets/{dataset_id}/acquisition", dependencies=[Depends(role)])
    def acquisition(
        dataset_id: str,
        start: date | None = None,
        end: date | None = None,
        group_by: Literal["channel", "device", "campaign_id", "business_date"] = "channel",
    ):
        row = dataset(dataset_id)
        return measurement.measure(
            warehouse=resource(row, "warehouse"),
            integrity_observations=resource(row, "observations"),
            start=start,
            end=end,
            group_by=(group_by,),
        )

    @app.get("/datasets/{dataset_id}/decision-case", dependencies=[Depends(role)])
    def decision_case(dataset_id: str):
        row = dataset(dataset_id)
        return build_case(resource(row, "warehouse"), resource(row, "observations"), **dates(row))

    @app.get("/datasets/{dataset_id}/opportunities", dependencies=[Depends(role)])
    def opportunity_board(dataset_id: str):
        return board(dataset(dataset_id))

    @app.get("/datasets/{dataset_id}/experiments", dependencies=[Depends(role)])
    def experiment_report(dataset_id: str):
        row = dataset(dataset_id)
        return experiments.report(
            resource(row, "warehouse"),
            resource(row, "observations"),
            resource(row, "experiment_plan"),
        )

    @app.get("/datasets/{dataset_id}/customers", dependencies=[Depends(role)])
    def customers(dataset_id: str, max_age: Annotated[int, Query(ge=0, le=36)] = 12):
        row = dataset(dataset_id)
        return economics.report(
            resource(row, "warehouse"), resource(row, "observations"), max_age=max_age
        )

    @app.get("/datasets/{dataset_id}/journeys", dependencies=[Depends(role)])
    def journey_report(dataset_id: str, lookback_days: Annotated[int, Query(ge=1, le=90)] = 30):
        return journeys.report(
            resource(dataset(dataset_id), "warehouse"), lookback_days=lookback_days
        )

    @app.get("/datasets/{dataset_id}/attribution", dependencies=[Depends(role)])
    def attribution_report(dataset_id: str, lookback_days: Annotated[int, Query(ge=1, le=90)] = 30):
        return attribution.report(
            resource(dataset(dataset_id), "warehouse"), lookback_days=lookback_days
        )

    @app.get("/datasets/{dataset_id}/search", dependencies=[Depends(role)])
    def search_report(dataset_id: str):
        return search_intelligence.report(resource(dataset(dataset_id), "observations"))

    @app.get("/datasets/{dataset_id}/retention", dependencies=[Depends(role)])
    def retention_report(dataset_id: str, baseline: date, as_of: date):
        row = dataset(dataset_id)
        return retention.report(
            resource(row, "warehouse"),
            resource(row, "observations"),
            baseline=baseline,
            as_of=as_of,
        )

    @app.get("/datasets/{dataset_id}/forecast", dependencies=[Depends(role)])
    def forecast_report(
        dataset_id: str,
        metric: Literal["orders", "sessions", "revenue"] = "orders",
        horizon: Annotated[int, Query(ge=1, le=14)] = 7,
        cutoff: date | None = None,
    ):
        row = dataset(dataset_id)
        return forecasting.report(
            resource(row, "warehouse"),
            resource(row, "observations"),
            metric=metric,
            horizon=horizon,
            cutoff=cutoff,
        )

    @app.get("/datasets/{dataset_id}/response-curves", dependencies=[Depends(role)])
    def response_report(dataset_id: str):
        return response_curves.report(resource(dataset(dataset_id), "observations"))

    @app.post("/scenarios", dependencies=[Depends(role)])
    def scenario(body: Scenario):
        return forecasting.scenario(body.baseline, body.changes)

    @app.post("/datasets/{dataset_id}/optimization", dependencies=[Depends(role)])
    def optimize(dataset_id: str, body: Budget):
        evidence = response_curves.report(resource(dataset(dataset_id), "observations"))
        return budget_studio.allocate(evidence, body.model_dump())

    @app.get("/datasets/{dataset_id}/decisions", dependencies=[Depends(role)])
    def decisions(dataset_id: str):
        return history(dataset(dataset_id))

    @app.post("/datasets/{dataset_id}/decisions")
    def import_decision(
        dataset_id: str, body: ImportDecision, actor: Annotated[str, Depends(writer)]
    ):
        row = dataset(dataset_id)
        history(row)
        return ledger.submit(
            resource(row, "ledger"),
            {
                "operation": "import",
                "request_id": body.request_id,
                "actor": actor,
                "rationale": body.rationale,
                "report": board(row),
                "opportunity_id": body.opportunity_id,
            },
        )

    @app.patch("/datasets/{dataset_id}/decisions/{decision_id}")
    def update_decision(
        dataset_id: str,
        decision_id: str,
        body: UpdateDecision,
        actor: Annotated[str, Depends(writer)],
    ):
        row = dataset(dataset_id)
        if decision_id not in {s["decision_id"] for s in history(row)["decisions"]}:
            raise HTTPException(404, "Decision not found")
        return ledger.submit(
            resource(row, "ledger"),
            {
                "operation": "update",
                "decision_id": decision_id,
                "actor": actor,
                **body.model_dump(),
            },
        )

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        import uvicorn

        app = create_app(
            args.root,
            json.loads(args.catalog.read_bytes()),
            read_token=os.environ.get("NEMO_READ_TOKEN"),
            write_token=os.environ.get("NEMO_WRITE_TOKEN"),
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
        return 0
    except (ValueError, TypeError, OSError):
        print(
            "NEMO API configuration is invalid; check catalog, root and service tokens.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
