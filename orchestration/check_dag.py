"""Run in the isolated Airflow environment; no scheduler or company credentials needed."""

import os
import runpy
import signal
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch


def main():
    module = runpy.run_path(str(Path(__file__).with_name("nemo_pipeline.py")))
    dag = module["dag"]
    assert set(dag.task_ids) == {"publish", "verify_publication"}
    assert dag.max_active_runs == 1 and not dag.catchup
    assert dag.schedule is None
    publish = dag.get_task("publish")
    assert publish.downstream_task_ids == {"verify_publication"}
    assert publish.retries == 2 and publish.retry_exponential_backoff
    assert publish.execution_timeout == timedelta(minutes=30)
    process = Mock()
    process.communicate.return_value = ('{"status":"published","run_id":"test"}', "")
    process.returncode = 0
    process.poll.return_value = 0
    with (
        patch.dict(
            os.environ,
            {
                "NEMO_CORE_PYTHON": "/test/python",
                "NEMO_PIPELINE_CONFIG": "/test/config.json",
                "SECRET_SENTINEL": "must-not-enter-child",
            },
        ),
        patch("subprocess.Popen", return_value=process) as popen,
    ):
        assert module["execute_pipeline"]()["status"] == "published"
        assert "SECRET_SENTINEL" not in popen.call_args.kwargs["env"]
        assert popen.call_args.kwargs["start_new_session"] is True
        process.returncode = 1
        try:
            module["execute_pipeline"]()
            raise AssertionError("failed child accepted")
        except RuntimeError:
            pass
        process.communicate.side_effect = subprocess.TimeoutExpired("test", 1500)
        process.poll.return_value = None
        with patch("os.killpg") as kill:
            try:
                module["execute_pipeline"]()
                raise AssertionError("timeout accepted")
            except subprocess.TimeoutExpired:
                pass
            kill.assert_called_once_with(process.pid, signal.SIGTERM)
    print("Real Airflow DAG structure, limits, secret isolation, failure and timeout checks pass.")


if __name__ == "__main__":
    main()
