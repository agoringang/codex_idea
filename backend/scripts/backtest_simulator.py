from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from app.model import predict_race
from app.schemas import BetRecommendation, BetType, RaceRequest, RunnerInput


OFFICIAL_BET_TYPES: tuple[BetType, ...] = (
    "win",
    "bracket_quinella",
    "quinella",
    "wide",
    "exacta",
    "trio",
    "trifecta",
)

EXOTIC_BET_TYPES: set[BetType] = {
    "bracket_quinella",
    "quinella",
    "wide",
    "exacta",
    "trio",
    "trifecta",
}

PAYOUT_COLUMNS: dict[BetType, str] = {
    "win": "payout_win",
    "place": "payout_place",
    "bracket_quinella": "payout_bracket_quinella",
    "quinella": "payout_quinella",
    "wide": "payout_wide",
    "exacta": "payout_exacta",
    "trio": "payout_trio",
    "trifecta": "payout_trifecta",
}


def value(row: pd.Series, column: str, default: Any = None) -> Any:
    if column not in row or pd.isna(row[column]):
        return default
    return row[column]


def bounded_float(row: pd.Series, column: str, default: float, lower: float, upper: float) -> float:
    return min(max(float(value(row, column, default)), lower), upper)


def bracket_from_runner_number(number: int) -> int:
    return min(max(math.ceil(number / 2), 1), 8)


def decimal_from_payout(value_: Any) -> float | None:
    if value_ is None or pd.isna(value_):
        return None
    payout = float(value_)
    if payout <= 0:
        return None
    # JRA payout columns are commonly yen per 100 yen. Decimal odds are already small.
    return payout / 100 if payout > 20 else payout


def prepare_frame(
    frame: pd.DataFrame,
    place_odds_divisor: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    prepared = frame.copy()
    prepared["race_id"] = prepared["race_id"].astype(str)

    for column in ["number", "gate", "finish_position", "market_odds", "place_odds", "field_size"]:
        if column in prepared:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    # Historical keiba_data conversion currently stores the race number in `number`
    # and the horse number in `gate`. If `number` is unique per runner, keep it.
    if "runner_number" in prepared:
        runner_number = pd.to_numeric(prepared["runner_number"], errors="coerce")
    elif "horse_number" in prepared:
        runner_number = pd.to_numeric(prepared["horse_number"], errors="coerce")
    elif "gate" in prepared and "number" in prepared:
        number_unique = prepared.groupby("race_id")["number"].transform("nunique")
        gate_unique = prepared.groupby("race_id")["gate"].transform("nunique")
        use_gate_as_number = (number_unique <= 2) & (gate_unique > number_unique)
        runner_number = prepared["number"].where(~use_gate_as_number, prepared["gate"])
    else:
        runner_number = prepared["number"]

    prepared["__runner_number"] = pd.to_numeric(runner_number, errors="coerce")
    prepared["__gate"] = prepared["__runner_number"].map(
        lambda number: bracket_from_runner_number(int(number)) if pd.notna(number) else 1
    )

    market_odds = pd.to_numeric(prepared.get("market_odds", 0), errors="coerce")
    raw_place_odds = pd.to_numeric(prepared.get("place_odds", 0), errors="coerce")
    legacy_estimate = (market_odds / place_odds_divisor).clip(lower=1.1)
    legacy_estimate = legacy_estimate.where(legacy_estimate <= market_odds, market_odds)
    conservative_estimate = (1.05 + (market_odds - 1).clip(lower=0) * 0.09).clip(lower=1.1, upper=8.0)
    credible_place = raw_place_odds.where(
        (raw_place_odds > 1)
        & (market_odds > 1)
        & (raw_place_odds <= market_odds)
        & ((raw_place_odds.round(2) - legacy_estimate.round(2)).abs() >= 0.015)
        & ((raw_place_odds.round(2) - conservative_estimate.round(2)).abs() >= 0.015),
        1.1,
    )
    prepared["__place_odds"] = credible_place

    before_rows = len(prepared)
    prepared = prepared[
        (prepared["finish_position"] > 0)
        & (prepared["__runner_number"] > 0)
        & (prepared["market_odds"] > 1)
    ].copy()
    prepared["__runner_number"] = prepared["__runner_number"].astype(int)
    prepared["__gate"] = prepared["__gate"].astype(int)

    prepared = prepared.groupby("race_id", sort=False).filter(lambda group: len(group) >= 2)

    diagnostics = {
        "input_rows": int(before_rows),
        "usable_rows": int(len(prepared)),
        "filtered_rows": int(before_rows - len(prepared)),
        "runner_number_source": (
            "runner_number/horse_number/number"
            if "runner_number" in frame or "horse_number" in frame
            else "number_or_gate"
        ),
        "place_odds_source": "credible_place_odds_only_else_1.1_no_estimated_roi",
    }
    return prepared, diagnostics


def runner_input(row: pd.Series) -> RunnerInput:
    market_odds = max(float(value(row, "market_odds", 10.0)), 1.1)
    place_odds = max(float(value(row, "__place_odds", 2.0)), 1.1)
    runner_number = int(value(row, "__runner_number", value(row, "number", 1)))

    payload: dict[str, Any] = {
        "id": str(
            value(
                row,
                "runner_id",
                value(row, "source_runner_id", f"{row['race_id']}-{runner_number}"),
            )
        ),
        "gate": min(max(int(value(row, "__gate", value(row, "gate", 1))), 1), 8),
        "number": runner_number,
        "name": str(value(row, "horse_name", value(row, "name", runner_number))),
        "market_odds": market_odds,
        "place_odds": place_odds,
        "speed": bounded_float(row, "speed", 72.0, 0, 100),
        "stamina": bounded_float(row, "stamina", 72.0, 0, 100),
        "pace": bounded_float(row, "pace", 72.0, 0, 100),
        "condition": bounded_float(row, "condition", 72.0, 0, 100),
        "base_win": bounded_float(row, "base_win", 0.06, 0.0001, 0.999),
    }

    odds_rank = value(row, "odds_rank")
    if odds_rank is not None and not pd.isna(odds_rank):
        payload["odds_rank"] = max(int(float(odds_rank)), 1)

    for column in NUMERIC_FEATURES:
        if column not in payload and column in row and not pd.isna(row[column]):
            numeric_value = float(row[column])
            rate_columns = {
                "jockey_win_rate",
                "trainer_win_rate",
                "horse_recent_win_rate",
                "horse_recent_place_rate",
                "ticket_pool_share",
            }
            if column in rate_columns:
                payload[column] = min(max(numeric_value, 0.0), 1.0)
            elif column in {"training_score", "bloodline_score"}:
                payload[column] = min(max(numeric_value, 0.0), 100.0)
            elif column in {"distance", "age", "days_since_last_run"}:
                payload[column] = max(int(numeric_value), 0)
            elif column == "odds_rank":
                payload[column] = max(int(numeric_value), 1)
            else:
                payload[column] = numeric_value
    for column in CATEGORICAL_FEATURES:
        if column in row and not pd.isna(row[column]):
            payload[column] = str(row[column])

    return RunnerInput(**payload)


def race_request(
    race_id: str,
    frame: pd.DataFrame,
    bankroll: float,
    risk_level: float,
    enabled_bet_types: list[BetType],
    min_edge: float,
    max_exposure: float,
    min_probability: float,
    max_candidate_odds: float,
    max_edge: float | None,
) -> RaceRequest:
    return RaceRequest(
        race_id=str(race_id),
        model_mode="ensemble",
        risk_level=risk_level,
        bankroll=bankroll,
        min_edge=min_edge,
        max_exposure=max_exposure,
        min_probability=min_probability,
        max_candidate_odds=max_candidate_odds,
        max_edge=max_edge,
        enabled_bet_types=enabled_bet_types,
        runners=[runner_input(row) for _, row in frame.iterrows()],
    )


def pair_key(numbers: list[int]) -> str:
    return "-".join(str(number) for number in numbers)


def unordered_key(numbers: list[int]) -> str:
    return "-".join(str(number) for number in sorted(numbers))


def winning_keys(frame: pd.DataFrame) -> dict[str, str | set[str]]:
    ordered = frame.sort_values("finish_position")
    top = [int(number) for number in ordered["__runner_number"].head(3)]
    gates = [int(gate) for gate in ordered["__gate"].head(2)]
    wide = {
        unordered_key([top[0], top[1]]),
        unordered_key([top[0], top[2]]),
        unordered_key([top[1], top[2]]),
    }

    return {
        "win": str(top[0]),
        "place": {str(number) for number in top},
        "bracket_quinella": unordered_key(gates),
        "quinella": unordered_key(top[:2]),
        "wide": wide,
        "exacta": pair_key(top[:2]),
        "trio": unordered_key(top),
        "trifecta": pair_key(top),
    }


def normalized_selection(selection: str, unordered: bool = False) -> str:
    parts = [match.group(0) for match in re.finditer(r"\d+", str(selection or ""))]
    if not parts:
        return str(selection)
    if unordered:
        return "-".join(sorted(parts, key=int))
    return "-".join(parts)


def winning_selections(recommendation: BetRecommendation, keys: dict[str, str | set[str]]) -> list[str]:
    key = keys[recommendation.bet_type]
    covered = recommendation.covered_selections or [recommendation.selection]

    if recommendation.bet_type == "place":
        return [selection for selection in covered if normalized_selection(selection) in key]
    if recommendation.bet_type in {"bracket_quinella", "quinella", "trio"}:
        return [
            selection
            for selection in covered
            if normalized_selection(selection, unordered=True) == key
        ]
    if recommendation.bet_type == "wide":
        return [
            selection
            for selection in covered
            if normalized_selection(selection, unordered=True) in key
        ]
    if recommendation.bet_type in {"exacta", "trifecta"}:
        return [selection for selection in covered if normalized_selection(selection) == key]
    return [recommendation.selection] if normalized_selection(recommendation.selection) == key else []


def winning_ticket_count(recommendation: BetRecommendation, keys: dict[str, str | set[str]]) -> int:
    return len(winning_selections(recommendation, keys))


def is_hit(recommendation: BetRecommendation, keys: dict[str, str | set[str]]) -> bool:
    return winning_ticket_count(recommendation, keys) > 0


def payout_items_map(race_frame: pd.DataFrame) -> dict[tuple[str, str], float]:
    if "payouts_json" not in race_frame:
        return {}
    raw_values = race_frame["payouts_json"].dropna()
    if raw_values.empty:
        return {}
    try:
        payload = json.loads(str(raw_values.iloc[0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    items: dict[tuple[str, str], float] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        bet_type = str(item.get("bet_type") or item.get("betType") or "")
        payout_yen = item.get("payout_yen") or item.get("payoutYen")
        if not bet_type or payout_yen is None:
            continue
        unordered = bet_type in {"bracket_quinella", "quinella", "wide", "trio"}
        key = normalized_selection(str(item.get("selection") or ""), unordered=unordered)
        decimal = decimal_from_payout(payout_yen)
        if key and decimal is not None:
            items[(bet_type, key)] = decimal
    return items


def official_payout_price(
    recommendation: BetRecommendation,
    race_frame: pd.DataFrame,
    selection: str,
) -> tuple[float, str]:
    unordered = recommendation.bet_type in {"bracket_quinella", "quinella", "wide", "trio"}
    selection_key = normalized_selection(selection, unordered=unordered)
    mapped = payout_items_map(race_frame).get((recommendation.bet_type, selection_key))
    if mapped is not None:
        return mapped, "official"

    payout_column = PAYOUT_COLUMNS.get(recommendation.bet_type)
    if payout_column and payout_column in race_frame:
        if recommendation.bet_type in {"win", "place"}:
            row = selected_runner(race_frame, selection)
            if row is not None:
                odds = decimal_from_payout(row.get(payout_column))
                if odds is not None:
                    return odds, "official"
    return 0.0, "none"


def payout_price(
    recommendation: BetRecommendation,
    race_frame: pd.DataFrame,
    *,
    synthetic_exotics: bool,
    allow_market_fallback: bool,
) -> tuple[float, str]:
    official, source = official_payout_price(recommendation, race_frame, recommendation.selection)
    if official > 0:
        return official, source
    if not allow_market_fallback:
        return 0.0, "none"
    if recommendation.bet_type == "win":
        row = selected_runner(race_frame, recommendation.selection)
        return (float(row["market_odds"]), "market") if row is not None else (0.0, "none")
    if recommendation.bet_type == "place":
        row = selected_runner(race_frame, recommendation.selection)
        return (float(row["__place_odds"]), "market") if row is not None else (0.0, "none")
    if recommendation.bet_type in EXOTIC_BET_TYPES and synthetic_exotics:
        return recommendation.odds, "synthetic"
    return 0.0, "none"


def selected_runner(frame: pd.DataFrame, selection: str) -> pd.Series | None:
    normalized = normalized_selection(selection)
    if not normalized.isdigit():
        return None
    number = int(normalized)
    matched = frame[frame["__runner_number"] == number]
    if matched.empty:
        return None
    return matched.iloc[0]


def payout_odds(
    recommendation: BetRecommendation,
    race_frame: pd.DataFrame,
    *,
    synthetic_exotics: bool,
    allow_market_fallback: bool = False,
) -> float:
    odds, _source = payout_price(
        recommendation,
        race_frame,
        synthetic_exotics=synthetic_exotics,
        allow_market_fallback=allow_market_fallback,
    )
    return odds


def parse_bet_types(text: str | None, synthetic_exotics: bool) -> list[BetType]:
    if not text:
        return list(OFFICIAL_BET_TYPES if synthetic_exotics else ("win",))
    requested = [item.strip() for item in text.split(",") if item.strip()]
    allowed = set(OFFICIAL_BET_TYPES)
    unknown = sorted(set(requested) - allowed)
    if unknown:
        raise ValueError(f"unknown or unsupported bet types: {unknown}")
    return [item for item in requested if item in allowed]  # type: ignore[list-item]


def edge_bucket(edge: float) -> str:
    if edge < 0.05:
        return "00-05"
    if edge < 0.10:
        return "05-10"
    if edge < 0.20:
        return "10-20"
    if edge < 0.40:
        return "20-40"
    if edge < 0.80:
        return "40-80"
    return "80+"


def empty_breakdown() -> dict[str, float | int]:
    return {"stake": 0.0, "payout": 0.0, "bets": 0, "hits": 0}


def add_breakdown(
    breakdown: dict[str, float | int],
    *,
    stake: float,
    payout: float,
) -> None:
    breakdown["stake"] = float(breakdown["stake"]) + stake
    breakdown["payout"] = float(breakdown["payout"]) + payout
    breakdown["bets"] = int(breakdown["bets"]) + 1
    breakdown["hits"] = int(breakdown["hits"]) + int(payout > 0)


def finalize_breakdowns(
    rows: defaultdict[str, dict[str, float | int]],
) -> dict[str, dict[str, float | int]]:
    output: dict[str, dict[str, float | int]] = {}
    for key, values in sorted(rows.items()):
        stake = float(values["stake"])
        bets = int(values["bets"])
        payout = float(values["payout"])
        hits = int(values["hits"])
        output[key] = {
            "bets": bets,
            "hits": hits,
            "total_stake": round(stake, 0),
            "total_payout": round(payout, 0),
            "roi": round(payout / stake, 4) if stake else 0,
            "hit_rate": round(hits / bets, 4) if bets else 0,
        }
    return output


def market_favorite_win_baseline(frame: pd.DataFrame, *, allow_market_fallback: bool) -> dict[str, Any]:
    total_stake = 0.0
    total_payout = 0.0
    hits = 0
    bets = 0
    missing_hit_payouts = 0
    for _, race_frame in frame.groupby("race_id", sort=False):
        favorite = race_frame.sort_values("market_odds").iloc[0]
        stake = 100.0
        payout = 0.0
        if int(favorite["finish_position"]) == 1:
            odds = decimal_from_payout(favorite.get("payout_win"))
            if odds is None and allow_market_fallback:
                odds = float(favorite["market_odds"])
            if odds is None:
                missing_hit_payouts += 1
            else:
                payout = stake * odds
        total_stake += stake
        total_payout += payout
        bets += 1
        hits += int(payout > 0)

    return {
        "bets": bets,
        "total_stake": round(total_stake, 0),
        "total_payout": round(total_payout, 0),
        "roi": round(total_payout / total_stake, 4) if total_stake else 0,
        "hit_rate": round(hits / bets, 4) if bets else 0,
        "missing_hit_payouts": missing_hit_payouts,
        "payout_mode": "official_or_market_fallback" if allow_market_fallback else "official_only",
    }


def simulate(
    frame: pd.DataFrame,
    bankroll: float,
    risk_level: float,
    limit: int,
    enabled_bet_types: list[BetType],
    synthetic_exotics: bool,
    min_edge: float,
    max_exposure: float,
    min_probability: float,
    max_candidate_odds: float,
    max_edge: float | None,
    allow_market_payout_fallback: bool,
) -> dict[str, Any]:
    required = {"race_id", "finish_position"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    if not ({"number", "gate", "runner_number", "horse_number"} & set(frame.columns)):
        raise ValueError(
            "missing runner number column: expected one of number, gate, "
            "runner_number, horse_number"
        )

    total_stake = 0.0
    total_payout = 0.0
    hit_count = 0
    bet_count = 0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    skipped_races = 0
    missing_hit_payouts = 0
    payout_sources: defaultdict[str, int] = defaultdict(int)
    by_bet_type: defaultdict[str, dict[str, float | int]] = defaultdict(empty_breakdown)
    by_edge: defaultdict[str, dict[str, float | int]] = defaultdict(empty_breakdown)

    for race_id, race_frame in frame.groupby("race_id", sort=False):
        prediction = predict_race(
            race_request(
                str(race_id),
                race_frame,
                bankroll,
                risk_level,
                enabled_bet_types,
                min_edge,
                max_exposure,
                min_probability,
                max_candidate_odds,
                max_edge,
            )
        )
        keys = winning_keys(race_frame)
        race_profit = 0.0
        race_bets = 0

        for recommendation in prediction.recommendations[:limit]:
            stake = recommendation.stake
            payout = 0.0
            winning_items = winning_selections(recommendation, keys)
            for selection in winning_items:
                odds, payout_source = official_payout_price(recommendation, race_frame, selection)
                if odds <= 0 and allow_market_payout_fallback:
                    odds, payout_source = payout_price(
                        recommendation,
                        race_frame,
                        synthetic_exotics=synthetic_exotics,
                        allow_market_fallback=True,
                    )
                if odds > 0:
                    payout += recommendation.unit_stake * odds
                else:
                    payout_source = "missing_official"
                    missing_hit_payouts += 1
                payout_sources[payout_source] += 1
            if not winning_items:
                payout_sources["not_hit"] += 1
            hit_count += 1 if payout else 0
            bet_count += 1
            total_stake += stake
            total_payout += payout
            race_profit += payout - stake
            race_bets += 1
            add_breakdown(by_bet_type[recommendation.bet_type], stake=stake, payout=payout)
            add_breakdown(by_edge[edge_bucket(recommendation.edge)], stake=stake, payout=payout)

        skipped_races += int(race_bets == 0)
        equity += race_profit
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    races = int(frame["race_id"].nunique())
    return {
        "races": races,
        "skipped_races": skipped_races,
        "bet_race_rate": round((races - skipped_races) / races, 4) if races else 0,
        "average_bets_per_race": round(bet_count / races, 4) if races else 0,
        "bets": bet_count,
        "total_stake": round(total_stake, 0),
        "total_payout": round(total_payout, 0),
        "roi": round(total_payout / total_stake, 4) if total_stake else 0,
        "hit_rate": round(hit_count / bet_count, 4) if bet_count else 0,
        "max_drawdown": round(max_drawdown, 0),
        "payout_data_complete": missing_hit_payouts == 0,
        "missing_hit_payouts": missing_hit_payouts,
        "payout_sources": dict(sorted(payout_sources.items())),
        "bet_types": enabled_bet_types,
        "filters": {
            "min_edge": min_edge,
            "min_probability": min_probability,
            "max_candidate_odds": max_candidate_odds,
            "max_edge": max_edge,
            "max_exposure": max_exposure,
            "limit": limit,
        },
        "breakdown_by_bet_type": finalize_breakdowns(by_bet_type),
        "breakdown_by_edge": finalize_breakdowns(by_edge),
        "baselines": {
            "market_favorite_win": market_favorite_win_baseline(
                frame,
                allow_market_fallback=allow_market_payout_fallback,
            ),
        },
        "payout_mode": (
            "official_or_market_fallback"
            if allow_market_payout_fallback
            else "official_payouts_only"
        ),
        "note": (
            "公式払戻だけで回収率を計算します。払戻未取得の的中はmissing_hit_payoutsに出し、推定払戻では補完しません。"
            if not allow_market_payout_fallback
            else "検証用に市場オッズ補完を許可しています。本番表示用のROIには使わないでください。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--risk", default=72, type=float)
    parser.add_argument("--bankroll", default=100_000, type=float)
    parser.add_argument("--limit", default=3, type=int)
    parser.add_argument("--min-edge", default=0.12, type=float)
    parser.add_argument("--min-probability", default=0.20, type=float)
    parser.add_argument("--max-odds", default=40.0, type=float)
    parser.add_argument("--max-edge", default=0.8, type=float)
    parser.add_argument("--max-exposure", default=0.04, type=float)
    parser.add_argument(
        "--bet-types",
        default=None,
        help="Comma-separated official bet types. Default excludes place betting.",
    )
    parser.add_argument(
        "--synthetic-exotics",
        action="store_true",
        help="Allow synthetic odds for exotic bets without payout columns",
    )
    parser.add_argument(
        "--allow-market-payout-fallback",
        action="store_true",
        help="Use market odds as payout fallback for debugging only. Do not use for publishable ROI.",
    )
    parser.add_argument("--place-odds-divisor", default=4.0, type=float)
    parser.add_argument(
        "--race-limit",
        default=0,
        type=int,
        help="Use the first N races for a quick smoke test",
    )
    parser.add_argument(
        "--skip-races",
        default=0,
        type=int,
        help="Skip the first N races before applying --race-limit",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        help="Override RACEQUANT_MODEL_PATH for this run",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.model_path:
        os.environ["RACEQUANT_MODEL_PATH"] = str(args.model_path)

    frame = pd.read_csv(args.csv, low_memory=False)
    frame, diagnostics = prepare_frame(frame, args.place_odds_divisor)
    enabled_bet_types = parse_bet_types(args.bet_types, args.synthetic_exotics)
    disabled_bet_types: list[BetType] = []
    if not args.synthetic_exotics:
        filtered_bet_types: list[BetType] = []
        for bet_type in enabled_bet_types:
            payout_column = PAYOUT_COLUMNS.get(bet_type)
            has_payout_json = "payouts_json" in frame.columns and frame["payouts_json"].notna().any()
            if bet_type in EXOTIC_BET_TYPES and payout_column not in frame.columns and not has_payout_json:
                disabled_bet_types.append(bet_type)
                continue
            filtered_bet_types.append(bet_type)
        enabled_bet_types = filtered_bet_types
    if not enabled_bet_types:
        raise ValueError("no bet types are available for this CSV")
    race_ids = frame["race_id"].drop_duplicates()
    if args.skip_races > 0:
        race_ids = race_ids.iloc[args.skip_races :]
        diagnostics["skip_races"] = int(args.skip_races)
    if args.race_limit > 0:
        race_ids = race_ids.head(args.race_limit)
        frame = frame[frame["race_id"].isin(race_ids)].copy()
        diagnostics["race_limit"] = int(args.race_limit)
    elif args.skip_races > 0:
        frame = frame[frame["race_id"].isin(race_ids)].copy()
    summary = simulate(
        frame,
        args.bankroll,
        args.risk,
        args.limit,
        enabled_bet_types,
        args.synthetic_exotics,
        args.min_edge,
        args.max_exposure,
        args.min_probability,
        args.max_odds,
        args.max_edge,
        args.allow_market_payout_fallback,
    )
    if disabled_bet_types:
        summary["disabled_bet_types"] = disabled_bet_types
    summary["diagnostics"] = diagnostics
    body = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
