"""Blind prediction worker. Receives public observations, never evaluator truth."""

import argparse
import importlib.abc
import json
import os
import sys
from pathlib import Path


def install_guard(workspace: Path):
    """Catch accidental private/lab access by trusted Python code; not an OS sandbox."""
    root = workspace.resolve()
    package = Path(__file__).resolve().parent
    allowed = (root, package, Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())

    class BlockLab(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in (
                "nemo.contracts",
                "nemo.simulation",
                "nemo.artifacts",
                "nemo.lab_tracking",
                "nemo.lab_payment",
                "nemo.blind_lab",
            ):
                raise PermissionError("blind worker cannot import lab or evaluator modules")
            return None

    def audit(event, args):
        if event != "open" or not args or isinstance(args[0], int):
            return
        try:
            path = Path(os.fsdecode(args[0])).resolve()
        except (TypeError, ValueError):
            return
        if "private" in (part.lower() for part in path.parts):
            raise PermissionError("blind worker cannot read private truth")
        if not any(path.is_relative_to(parent) for parent in allowed):
            raise PermissionError("blind worker file access outside permitted workspace/runtime")

    sys.meta_path.insert(0, BlockLab())
    sys.addaudithook(audit)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Canonical-only blind prediction worker")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--baseline-start", required=True)
    parser.add_argument("--current-start", required=True)
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    # Keep Python tempfile activity within the copied public workspace.
    os.environ.update(TMP=str(workspace), TEMP=str(workspace), TMPDIR=str(workspace))
    install_guard(workspace)
    from datetime import date

    from nemo.decision_case import build_case
    from nemo.warehouse import build_warehouse

    observations = workspace / "observations"
    database = workspace / "warehouse.duckdb"
    build_warehouse(observations, database)
    case = build_case(
        database,
        observations,
        baseline_start=date.fromisoformat(args.baseline_start),
        current_start=date.fromisoformat(args.current_start),
    )
    with (workspace / "case.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(case, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": "sealed_candidate", "finding": case["finding"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
