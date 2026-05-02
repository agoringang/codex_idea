from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Start netkeiba collection in a detached background process.")
    parser.add_argument("--start-year", default=2006, type=int)
    parser.add_argument("--end-year", default=2026, type=int)
    parser.add_argument("--end-date", default="2026-05-02")
    parser.add_argument("--delay-seconds", default=10.0, type=float)
    parser.add_argument("--jitter-seconds", default=3.0, type=float)
    parser.add_argument("--train-after", action="store_true")
    parser.add_argument("--log", default=Path("runtime/netkeiba_collect.log"), type=Path)
    parser.add_argument("--pid-file", default=Path("runtime/netkeiba_collect.pid"), type=Path)
    args = parser.parse_args()

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.pid_file.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "scripts/netkeiba_collect.py",
        "--start-year",
        str(args.start_year),
        "--end-year",
        str(args.end_year),
        "--end-date",
        args.end_date,
        "--delay-seconds",
        str(args.delay_seconds),
        "--jitter-seconds",
        str(args.jitter_seconds),
    ]
    if args.train_after:
        command.append("--train-after")

    log_handle = args.log.open("a", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    args.pid_file.write_text(str(process.pid), encoding="utf-8")
    print(
        json.dumps(
            {
                "started": True,
                "pid": process.pid,
                "log": str(args.log),
                "pid_file": str(args.pid_file),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "command": command,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
