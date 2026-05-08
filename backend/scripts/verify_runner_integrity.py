from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_sources import get_races
from app.runner_integrity import validate_race_runner_integrity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify race-card runner identity, horse names, gates, and odds consistency."
    )
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=7)).isoformat())
    parser.add_argument("--end-date", default=(date.today() + timedelta(days=7)).isoformat())
    parser.add_argument("--market", choices=["", "JRA", "NAR"], default="")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    races = get_races(start_date=args.start_date, end_date=args.end_date)
    if args.market:
        races = [race for race in races if race.market == args.market]

    reports: list[dict[str, Any]] = []
    error_count = 0
    warning_count = 0
    for race in races:
        report = validate_race_runner_integrity(race)
        errors = report.get("errors") if isinstance(report.get("errors"), list) else []
        warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
        error_count += len(errors)
        warning_count += len(warnings)
        if errors or warnings:
            reports.append(
                {
                    "race_id": race.id,
                    "date": race.date,
                    "venue": race.venue,
                    "race_no": race.raceNo,
                    "market": race.market,
                    "errors": errors,
                    "warnings": warnings,
                    "runner_count": report.get("runner_count"),
                    "odds_count": report.get("odds_count"),
                }
            )

    failed = error_count > 0 or (args.strict and warning_count > 0)
    summary = {
        "status": "failed" if failed else "ok",
        "start_date": args.start_date,
        "end_date": args.end_date,
        "market": args.market or "ALL",
        "races": len(races),
        "error_count": error_count,
        "warning_count": warning_count,
        "reports": reports[:80],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
