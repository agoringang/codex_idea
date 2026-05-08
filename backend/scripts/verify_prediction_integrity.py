from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_sources import get_races
from app.history import get_all_history
from app.ingestion import _race_request_from_dict
from app.model import predict_race
from app.runner_integrity import validate_race_runner_integrity
from app.settlement import settle_history

FIXED_PUBLIC_BET_TYPES = {
    "win",
    "bracket_quinella",
    "quinella",
    "wide",
    "exacta",
    "trio",
    "trifecta",
}


def flatten_history(history: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entries in history.values():
        rows.extend(item for item in entries if isinstance(item, dict))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that public prediction history does not create unsupported bet types or fake payouts."
    )
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=35)).isoformat())
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--market", choices=["", "JRA", "NAR"], default="")
    parser.add_argument("--sample-predictions", type=int, default=24)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    races = get_races(start_date=args.start_date, end_date=args.end_date)
    if args.market:
        races = [race for race in races if race.market == args.market]
    history = get_all_history(args.start_date, args.end_date)
    settled = flatten_history(settle_history(history, races))

    errors: list[str] = []
    payout_sources: Counter[str] = Counter()
    bet_types: Counter[str] = Counter()
    settled_count = 0

    for entry in settled:
        result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
        if not result.get("settled"):
            continue
        settled_count += 1
        recommendation_results = result.get("recommendation_results")
        if not isinstance(recommendation_results, list):
            continue
        stake_sum = sum(float(item.get("stake") or 0) for item in recommendation_results if isinstance(item, dict))
        payout_sum = sum(float(item.get("payout") or 0) for item in recommendation_results if isinstance(item, dict))
        if abs(float(result.get("stake") or 0) - stake_sum) > 1e-6:
            errors.append(f"{entry.get('race_id')}: result stake does not match recommendation stake sum")
        if abs(float(result.get("payout") or 0) - payout_sum) > 1e-6:
            errors.append(f"{entry.get('race_id')}: result payout does not match recommendation payout sum")

        for item in recommendation_results:
            if not isinstance(item, dict):
                continue
            bet_type = str(item.get("bet_type") or "")
            source = str(item.get("payout_source") or "")
            payout_sources[source] += 1
            bet_types[bet_type] += 1
            if bet_type == "support":
                errors.append(f"{entry.get('race_id')}: unsupported support bet leaked into result UI")
            if bet_type == "place":
                errors.append(f"{entry.get('race_id')}: place bet leaked into result UI")
            hit = bool(item.get("hit"))
            payout = float(item.get("payout") or 0)
            official = float(item.get("official_payout_yen") or 0)
            if source == "official" and (not hit or official <= 0 or payout <= 0):
                errors.append(f"{entry.get('race_id')}: official payout source has invalid hit/payout")
            if source != "official" and payout > 0:
                errors.append(f"{entry.get('race_id')}: non-official payout source produced positive payout")
            if not hit and source not in {"not_hit", "missing_official_payout"}:
                errors.append(f"{entry.get('race_id')}: non-hit recommendation has unexpected payout source {source}")
            if not hit and source == "missing_official_payout" and payout > 0:
                errors.append(f"{entry.get('race_id')}: missing official payout was counted as a positive return")

    sampled = 0
    sample_bet_types: Counter[str] = Counter()
    non_triple_predictions = 0
    runner_integrity_errors = 0
    runner_integrity_warnings = 0
    for race in races:
        integrity = validate_race_runner_integrity(race)
        runner_errors = integrity.get("errors") if isinstance(integrity.get("errors"), list) else []
        runner_warnings = integrity.get("warnings") if isinstance(integrity.get("warnings"), list) else []
        runner_integrity_errors += len(runner_errors)
        runner_integrity_warnings += len(runner_warnings)
        for error in runner_errors:
            errors.append(f"{race.id}: runner integrity failed: {error}")

        if sampled >= args.sample_predictions:
            continue
        payload = race.model_dump(mode="json")
        if len(payload.get("runners") or []) < 2:
            continue
        request = _race_request_from_dict(payload)
        request.enabled_bet_types = list(FIXED_PUBLIC_BET_TYPES)
        request.min_edge = 0.0
        request.min_probability = 0.0
        request.max_edge = None
        request.max_candidate_odds = 999
        request.max_exposure = 0.1
        request.recommendation_limit = 7
        prediction = predict_race(request)
        sampled += 1
        generated_types = {item.bet_type for item in prediction.recommendations}
        sample_bet_types.update(generated_types)
        if "support" in generated_types:
            errors.append(f"{race.id}: prediction generated unsupported support bet")
        if "place" in generated_types:
            errors.append(f"{race.id}: prediction generated place bet")
        if generated_types != FIXED_PUBLIC_BET_TYPES:
            non_triple_predictions += 1

    if non_triple_predictions > 0:
        errors.append(f"sample predictions did not contain the fixed seven bet types: {non_triple_predictions}/{sampled}")

    summary = {
        "status": "ok" if not errors else "failed",
        "start_date": args.start_date,
        "end_date": args.end_date,
        "market": args.market or "ALL",
        "races": len(races),
        "settled_history": settled_count,
        "result_bet_types": dict(bet_types),
        "payout_sources": dict(payout_sources),
        "sampled_predictions": sampled,
        "sample_prediction_bet_types": dict(sample_bet_types),
        "runner_integrity_errors": runner_integrity_errors,
        "runner_integrity_warnings": runner_integrity_warnings,
        "errors": errors[:50],
        "error_count": len(errors),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
