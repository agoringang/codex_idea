from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from app.model import predict_race
from app.schemas import BetRecommendation, RaceRequest, RunnerInput


def value(row: pd.Series, column: str, default: Any = None) -> Any:
    if column not in row or pd.isna(row[column]):
        return default
    return row[column]


def bounded_float(row: pd.Series, column: str, default: float, lower: float, upper: float) -> float:
    return min(max(float(value(row, column, default)), lower), upper)


def runner_input(row: pd.Series) -> RunnerInput:
    payload: dict[str, Any] = {
        "id": str(value(row, "runner_id", f"{row['race_id']}-{row['number']}")),
        "gate": int(value(row, "gate", 1)),
        "number": int(row["number"]),
        "name": str(value(row, "name", row["number"])),
        "market_odds": float(value(row, "market_odds", 10.0)),
        "place_odds": float(value(row, "place_odds", 2.0)),
        "speed": bounded_float(row, "speed", 72.0, 0, 100),
        "stamina": bounded_float(row, "stamina", 72.0, 0, 100),
        "pace": bounded_float(row, "pace", 72.0, 0, 100),
        "condition": bounded_float(row, "condition", 72.0, 0, 100),
        "base_win": bounded_float(row, "base_win", 0.06, 0.0001, 0.999),
    }

    for column in NUMERIC_FEATURES:
        if column not in payload and column in row and not pd.isna(row[column]):
            payload[column] = float(row[column])
    for column in CATEGORICAL_FEATURES:
        if column in row and not pd.isna(row[column]):
            payload[column] = str(row[column])

    return RunnerInput(**payload)


def race_request(race_id: str, frame: pd.DataFrame, bankroll: float, risk_level: float) -> RaceRequest:
    return RaceRequest(
        race_id=str(race_id),
        model_mode="ensemble",
        risk_level=risk_level,
        bankroll=bankroll,
        min_edge=0.0,
        max_exposure=0.04,
        runners=[runner_input(row) for _, row in frame.iterrows()],
    )


def pair_key(numbers: list[int]) -> str:
    return "-".join(str(number) for number in numbers)


def unordered_key(numbers: list[int]) -> str:
    return "-".join(str(number) for number in sorted(numbers))


def winning_keys(frame: pd.DataFrame) -> dict[str, str | set[str]]:
    ordered = frame.sort_values("finish_position")
    top = [int(number) for number in ordered["number"].head(3)]
    gates = [int(gate) for gate in ordered["gate"].head(2)]
    wide = {unordered_key([top[0], top[1]]), unordered_key([top[0], top[2]]), unordered_key([top[1], top[2]])}

    return {
        "win": str(top[0]),
        "place": {str(number) for number in top},
        "support": {str(number) for number in top},
        "bracket_quinella": unordered_key(gates),
        "quinella": unordered_key(top[:2]),
        "wide": wide,
        "exacta": pair_key(top[:2]),
        "trio": unordered_key(top),
        "trifecta": pair_key(top),
    }


def normalized_selection(selection: str, unordered: bool = False) -> str:
    parts = [part.strip() for part in selection.split("-") if part.strip().isdigit()]
    if not parts:
        return selection
    if unordered:
        return "-".join(sorted(parts, key=int))
    return "-".join(parts)


def is_hit(recommendation: BetRecommendation, keys: dict[str, str | set[str]]) -> bool:
    key = keys[recommendation.bet_type]
    covered = recommendation.covered_selections or [recommendation.selection]

    if recommendation.bet_type in {"place", "support"}:
        return normalized_selection(recommendation.selection) in key
    if recommendation.bet_type in {"bracket_quinella", "quinella", "trio"}:
        return normalized_selection(recommendation.selection, unordered=True) == key
    if recommendation.bet_type == "wide":
        return any(normalized_selection(selection, unordered=True) in key for selection in covered)
    if recommendation.bet_type == "trifecta":
        return key in {normalized_selection(selection) for selection in covered}
    return normalized_selection(recommendation.selection) == key


def simulate(frame: pd.DataFrame, bankroll: float, risk_level: float, limit: int) -> dict[str, Any]:
    required = {"race_id", "number", "finish_position"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    total_stake = 0.0
    total_payout = 0.0
    hit_count = 0
    bet_count = 0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for race_id, race_frame in frame.groupby("race_id", sort=False):
        prediction = predict_race(race_request(str(race_id), race_frame, bankroll, risk_level))
        keys = winning_keys(race_frame)
        race_profit = 0.0

        for recommendation in prediction.recommendations[:limit]:
            stake = recommendation.stake
            payout = stake * recommendation.odds if is_hit(recommendation, keys) else 0.0
            hit_count += 1 if payout else 0
            bet_count += 1
            total_stake += stake
            total_payout += payout
            race_profit += payout - stake

        equity += race_profit
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    return {
        "races": int(frame["race_id"].nunique()),
        "bets": bet_count,
        "total_stake": round(total_stake, 0),
        "total_payout": round(total_payout, 0),
        "roi": round(total_payout / total_stake, 4) if total_stake else 0,
        "hit_rate": round(hit_count / bet_count, 4) if bet_count else 0,
        "max_drawdown": round(max_drawdown, 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--risk", default=72, type=float)
    parser.add_argument("--bankroll", default=100_000, type=float)
    parser.add_argument("--limit", default=12, type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    frame = pd.read_csv(args.csv)
    summary = simulate(frame, args.bankroll, args.risk, args.limit)
    body = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
