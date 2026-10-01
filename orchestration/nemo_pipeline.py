"""Manual canonical pipeline DAG; no extraction or company data at parse time."""

import json
import os
import signal
import subprocess
from datetime import timedelta
from pathlib import Path

from airflow.sdk import DAG, task


def execute_pipeline(*arguments):
    python = Path(os.environ["NEMO_CORE_PYTHON"])
    config = Path(os.environ["NEMO_PIPELINE_CONFIG"])
    if not python.is_absolute() or not config.is_absolute():
        raise ValueError("absolute operator-managed runtime and config required")
    process = subprocess.Popen(
        [str(python), "-m", "nemo.pipeline", "--config", str(config), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env={k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ")},
    )
    try:
        stdout, _ = process.communicate(timeout=1500)
        if process.returncode != 0:
            raise RuntimeError("NEMO pipeline failed; inspect canonical input and output lock")
        return json.loads(stdout)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


with DAG(
    dag_id="nemo_canonical_pipeline",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=10),
    },
    tags=["nemo", "canonical", "read-only-decisions"],
) as dag:

    @task(execution_timeout=timedelta(minutes=30))
    def publish():
        return execute_pipeline()

    @task(execution_timeout=timedelta(minutes=5))
    def verify_publication(result):
        verified = execute_pipeline("--verify", result["run_id"])
        if verified["status"] != "verified":
            raise RuntimeError("publication verification failed")

    verify_publication(publish())
