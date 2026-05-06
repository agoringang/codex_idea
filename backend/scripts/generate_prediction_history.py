from __future__ import annotations

import argparse
import json
import sys
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.model import predict_race
from app.schemas import BetRecommendation, BetType
from backtest_simulator import (
    OFFICIAL_BET_TYPES,
    payout_price,
    prepare_frame,
    race_request,
    winning_keys,
    winning_ticket_count,
)


def row_value(row: pd.Series, column: str, default: Any = None) -> Any:
    if column not in row or pd.isna(row[column]):
        return default
    return row[column]


def race_label(race_id: str, frame: pd.DataFrame) -> dict[str, str]:
    first = frame.iloc[0]
    venue = str(row_value(first, "venue", "不明"))
    race_no = row_value(first, "race_no")
    if race_no is None:
        race_no = f"{int(race_id[-2:])}R" if race_id[-2:].isdigit() else "--R"
    elif str(race_no).isdigit():
        race_no = f"{int(race_no)}R"
    else:
        race_no = str(race_no)

    distance = row_value(first, "distance", "")
    surface = row_value(first, "surface", "")
    course = f"{surface}{int(distance)}m" if distance and str(distance).replace(".", "", 1).isdigit() else str(surface)
    return {
        "venue": venue,
        "race_no": str(race_no),
        "title": f"{venue}{race_no}",
        "course": course,
    }


def result_payload(frame: pd.DataFrame) -> dict[str, Any]:
    ordered = frame.sort_values("finish_position")
    order = [int(number) for number in ordered["__runner_number"].head(3)]
    return {
        "status": "official" if order else "unknown",
        "order": order,
        "winning_selection": str(order[0]) if order else None,
    }


def performance_payload(
    recommendations: list[BetRecommendation],
    frame: pd.DataFrame,
    *,
    synthetic_exotics: bool,
) -> dict[str, Any]:
    keys = winning_keys(frame)
    total_stake = 0.0
    total_payout = 0.0
    hits = 0

    for recommendation in recommendations:
        total_stake += recommendation.stake
        odds, payout_source = payout_price(
            recommendation,
            frame,
            synthetic_exotics=synthetic_exotics,
        )
        winning_tickets = winning_ticket_count(recommendation, keys)
        if odds <= 0 or winning_tickets <= 0:
            continue
        hits += 1
        if payout_source == "synthetic" and recommendation.tickets > 1:
            total_payout += recommendation.stake * odds * winning_tickets
        else:
            total_payout += recommendation.unit_stake * odds * winning_tickets

    return {
        "bets": len(recommendations),
        "hits": hits,
        "total_stake": round(total_stake, 0),
        "total_payout": round(total_payout, 0),
        "roi": round(total_payout / total_stake, 4) if total_stake else 0,
        "hit_rate": round(hits / len(recommendations), 4) if recommendations else 0,
    }


def load_existing(path: Path, replace: bool) -> dict[str, list[dict[str, Any]]]:
    if replace or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except JSONDecodeError:
        backup = path.with_suffix(f"{path.suffix}.invalid")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(
            f"warning: invalid history JSON was moved aside for regeneration: {backup}",
            file=sys.stderr,
        )
        return {}


def upsert_entry(
    history: dict[str, list[dict[str, Any]]],
    date: str,
    entry: dict[str, Any],
) -> None:
    day_entries = [item for item in history.get(date, []) if item.get("race_id") != entry["race_id"]]
    day_entries.append(entry)
    day_entries.sort(key=lambda item: str(item.get("race_id", "")))
    history[date] = day_entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate calendar-ready historical prediction records from normalized race CSV."
    )
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", default=Path("data/predictions_history.json"), type=Path)
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--risk", default=52, type=float)
    parser.add_argument("--bankroll", default=100_000, type=float)
    parser.add_argument("--limit", default=5, type=int)
    parser.add_argument("--min-edge", default=0.12, type=float)
    parser.add_argument("--min-probability", default=0.20, type=float)
    parser.add_argument("--max-odds", default=40.0, type=float)
    parser.add_argument("--max-edge", default=0.8, type=float)
    parser.add_argument("--max-exposure", default=0.04, type=float)
    parser.add_argument("--place-odds-divisor", default=4.0, type=float)
    parser.add_argument("--synthetic-exotics", action="store_true")
    parser.add_argument("--replace", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    raw_frame = pd.read_csv(args.csv, low_memory=False)
    if "race_date" not in raw_frame.columns:
        raise ValueError("missing required column: race_date")

    source_dates = pd.to_datetime(raw_frame["race_date"], errors="coerce")
    source_min = source_dates.min()
    source_max = source_dates.max()

    frame, diagnostics = prepare_frame(raw_frame, args.place_odds_divisor)
    race_dates = pd.to_datetime(frame["race_date"], errors="coerce")
    mask = race_dates >= pd.Timestamp(args.start_date)
    if args.end_date:
        mask &= race_dates <= pd.Timestamp(args.end_date)
    frame = frame[mask].copy()

    history = load_existing(args.output, args.replace)
    enabled_bet_types: list[BetType] = list(OFFICIAL_BET_TYPES)
    processed = 0

    for race_id, race_frame in frame.groupby("race_id", sort=False):
        race_date = str(race_frame["race_date"].iloc[0])
        request = race_request(
            str(race_id),
            race_frame,
            args.bankroll,
            args.risk,
            enabled_bet_types,
            args.min_edge,
            args.max_exposure,
            args.min_probability,
            args.max_odds,
            args.max_edge,
        )
        prediction = predict_race(request)
        recommendations = prediction.recommendations[: args.limit]
        labels = race_label(str(race_id), race_frame)

        entry = {
            "race_id": str(race_id),
            "date": race_date,
            **labels,
            "prediction": {
                "risk_level": args.risk,
                "bankroll": args.bankroll,
                "expected_roi": round(prediction.expected_roi, 4),
                "total_stake": round(prediction.total_stake, 0),
                "recommendations": [item.model_dump(mode="json") for item in recommendations],
                "top_runners": [item.model_dump(mode="json") for item in prediction.runners[:5]],
            },
            "result": result_payload(race_frame),
            "performance": performance_payload(
                recommendations,
                race_frame,
                synthetic_exotics=args.synthetic_exotics,
            ),
        }
        upsert_entry(history, race_date, entry)
        processed += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "source_csv": str(args.csv),
        "source_min_date": source_min.date().isoformat() if pd.notna(source_min) else None,
        "source_max_date": source_max.date().isoformat() if pd.notna(source_max) else None,
        "start_date": args.start_date,
        "end_date": args.end_date or None,
        "processed_races": processed,
        "output": str(args.output),
        "diagnostics": diagnostics,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
