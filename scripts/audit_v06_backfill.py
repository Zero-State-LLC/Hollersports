#!/usr/bin/env python3
"""Read-only HollerSports V0.6 historical backfill readiness audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "hollersports"))

from hollersports.backfill import audit_backfill_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--fixtures-root", type=Path, default=REPO_ROOT / "fixtures")
    parser.add_argument("--assert-v06-ready", action="store_true")
    args = parser.parse_args()
    report = audit_backfill_readiness(args.data_root, args.fixtures_root)
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    if args.assert_v06_ready and not report.v06_temporal_backfill_possible:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
