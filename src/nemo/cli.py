"""Offline CLI for generating immutable synthetic observation snapshots."""

import argparse
import sys
from datetime import date
from pathlib import Path

from nemo.artifacts import canonical_json, write_world
from nemo.contracts import SimulationConfig
from nemo.simulation import generate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEMO synthetic business core (no real data)")
    parser.add_argument("--output", type=Path, required=True, help="New snapshot directory")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=date(2026, 7, 1),
        help="Exclusive end date (YYYY-MM-DD)",
    )
    parser.add_argument("--lockfile", type=Path, help="Dependency lockfile to fingerprint")
    args = parser.parse_args(argv)
    try:
        config = SimulationConfig(seed=args.seed, start_date=args.start, end_date=args.end)
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError(f"Output already exists: {args.output}")
        if args.lockfile is not None and not args.lockfile.is_file():
            raise ValueError("--lockfile must name an existing file")
        manifest = write_world(generate(config), args.output, lockfile=args.lockfile)
    except (ValueError, OSError) as error:
        sys.stderr.write(canonical_json({"status": "error", "message": str(error)}).decode())
        return 1
    print(
        canonical_json(
            {
                "status": "complete",
                "mode": "synthetic",
                "output": str(args.output.absolute()),
                "rows": {name: details["rows"] for name, details in manifest["tables"].items()},
            }
        ).decode(),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
