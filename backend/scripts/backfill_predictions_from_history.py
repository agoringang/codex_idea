from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_sources import get_races
from app.ingestion import _existing_prediction_ids, _record_prediction_for_race


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value.replace("\\n", "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill post-result prediction simulations from history CSVs into prediction_history."
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--market", choices=["JRA", "NAR", "all"], default="JRA")
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--env-file", type=Path, default=Path("../.env.local"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_env(args.env_file)

    existing = set() if args.include_existing else _existing_prediction_ids(args.start_date, args.end_date)
    races = get_races(args.start_date, args.end_date)
    candidates = [
        race.model_dump(mode="json")
        for race in races
        if race.status == "finished"
        and (args.market == "all" or race.market == args.market)
        and (args.include_existing or race.id not in existing)
    ]
    if args.limit > 0:
        candidates = candidates[: args.limit]

    saved = 0
    failed: list[str] = []
    for race in candidates:
        race_id = str(race.get("id") or "")
        if _record_prediction_for_race(race, generated_after_result=True):
            saved += 1
            existing.add(race_id)
        else:
            failed.append(race_id)

    print(
        {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "market": args.market,
            "candidate_races": len(candidates),
            "saved": saved,
            "failed": len(failed),
            "failed_sample": failed[:10],
        }
    )


if __name__ == "__main__":
    main()
