from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def write_live_snapshot(path: Path, race_ids: list[str], provider: str, interval_seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "interval_seconds": interval_seconds,
        "race_ids": race_ids,
        "pipeline": [
            "racecard: detect finalized entries",
            "odds: store snapshots and compute deltas",
            "scratches: remove scratched runners and recompute tickets",
            "results: settle tickets and highlight hit/refund/miss",
        ],
        "status": "adapter_ready",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="simulation", choices=["simulation", "jravan", "accessd"])
    parser.add_argument("--race-id", action="append", default=[])
    parser.add_argument("--interval-seconds", default=60, type=int)
    parser.add_argument("--out", default=Path("runtime/live-snapshot.json"), type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        write_live_snapshot(args.out, args.race_id, args.provider, args.interval_seconds)
        if args.once:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
