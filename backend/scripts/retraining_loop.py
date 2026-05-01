from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def write_heartbeat(path: Path, interval_seconds: int, provider: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "status": "waiting_for_real_sync_implementation",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "loop_interval_seconds": interval_seconds,
        "next_jobs": [
            "sync race cards and odds snapshots",
            "refresh predictions",
            "ingest official results",
            "queue retraining when labels arrive",
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="jravan", choices=["jravan", "csv"])
    parser.add_argument("--interval-seconds", default=300, type=int)
    parser.add_argument("--heartbeat", default=Path("runtime/retraining-heartbeat.json"), type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        write_heartbeat(args.heartbeat, args.interval_seconds, args.provider)
        if args.once:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
