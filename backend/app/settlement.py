from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .schemas import Race


NUMBER_PATTERN = re.compile(r"\d+")
SUPPORTED_BET_TYPES = {"win", "place", "quinella", "wide", "exacta", "trio", "trifecta"}


def _numbers(value: Any) -> list[int]:
    if isinstance(value, list):
        parsed: list[int] = []
        for item in value:
            try:
                parsed.append(int(item))
            except (TypeError, ValueError):
                continue
        return parsed
    return [int(match.group(0)) for match in NUMBER_PATTERN.finditer(str(value or ""))]


def _result_order(race: Race) -> list[int]:
    order: list[tuple[int, int]] = []
    for runner in race.runners:
        for tag in runner.tags:
            if not tag.endswith("着"):
                continue
            try:
                position = int(tag.replace("着", ""))
            except ValueError:
                continue
            order.append((position, runner.number))
    return [number for _, number in sorted(order)]


def _recommendation_entries(recommendation: dict[str, Any]) -> list[list[int]]:
    covered = recommendation.get("covered_selections")
    if isinstance(covered, list) and covered:
        entries = [_numbers(selection) for selection in covered]
    else:
        entries = [_numbers(recommendation.get("selection"))]
    return [entry for entry in entries if entry]


def _entry_key(numbers: list[int], *, ordered: bool) -> str:
    values = numbers if ordered else sorted(numbers)
    return "-".join(str(number) for number in values)


def _payout_key(selection: Any, *, ordered: bool) -> str:
    return _entry_key(_numbers(selection), ordered=ordered)


def _runner_by_number(race: Race) -> dict[int, Any]:
    return {runner.number: runner for runner in race.runners}


def _official_payout_yen(recommendation: dict[str, Any], race: Race, order: list[int]) -> float | None:
    entries = _recommendation_entries(recommendation)
    return _official_payout_for_entries(recommendation, race, order, entries)


def _official_payout_for_entries(
    recommendation: dict[str, Any],
    race: Race,
    order: list[int],
    entries: list[list[int]],
) -> float | None:
    bet_type = str(recommendation.get("bet_type") or "")
    runners = _runner_by_number(race)

    if bet_type == "win":
        runner = runners.get(entries[0][0]) if entries else None
        return float(runner.payoutWin) if runner and runner.payoutWin else None
    if bet_type == "place":
        runner = runners.get(entries[0][0]) if entries else None
        return float(runner.payoutPlace) if runner and runner.payoutPlace else None

    ordered = bet_type in {"exacta", "trifecta"}
    entry_keys = {_entry_key(entry, ordered=ordered) for entry in entries}
    for payout in getattr(race, "payouts", []) or []:
        payout_type = getattr(payout, "betType", "")
        if payout_type != bet_type:
            continue
        if _payout_key(getattr(payout, "selection", ""), ordered=ordered) in entry_keys:
            return float(getattr(payout, "payoutYen", 0) or 0) or None

    return None


def _entry_is_hit(bet_type: str, entry: list[int], order: list[int]) -> bool:
    if not order:
        return False
    first = order[0]
    top2 = order[:2]
    top3 = order[:3]

    if bet_type == "win" and entry[0] == first:
        return True
    if bet_type == "place" and entry[0] in top3:
        return True
    if bet_type in {"quinella", "bracket_quinella"} and len(entry) >= 2 and set(entry[:2]) == set(top2):
        return True
    if bet_type == "wide" and len(entry) >= 2 and len(set(entry[:2]) & set(top3)) >= 2:
        return True
    if bet_type == "exacta" and len(entry) >= 2 and entry[:2] == top2:
        return True
    if bet_type == "trio" and len(entry) >= 3 and set(entry[:3]) == set(top3):
        return True
    if bet_type == "trifecta" and len(entry) >= 3 and entry[:3] == top3:
        return True
    return False


def _winning_entries(recommendation: dict[str, Any], order: list[int]) -> list[list[int]]:
    bet_type = str(recommendation.get("bet_type") or "")
    return [
        entry
        for entry in _recommendation_entries(recommendation)
        if _entry_is_hit(bet_type, entry, order)
    ]


def settle_prediction_entry(entry: dict[str, Any], race: Race | None) -> dict[str, Any]:
    enriched = deepcopy(entry)
    if race is None:
        enriched["result"] = {
            **(enriched.get("result") if isinstance(enriched.get("result"), dict) else {}),
            "settled": False,
            "message": "対応するレース結果がまだ保存されていません",
        }
        return enriched

    order = _result_order(race)
    if len(order) < 3:
        enriched["result"] = {
            **(enriched.get("result") if isinstance(enriched.get("result"), dict) else {}),
            "settled": False,
            "message": "結果待ち",
            "order": order or None,
        }
        return enriched

    prediction = enriched.get("prediction") if isinstance(enriched.get("prediction"), dict) else {}
    recommendations = prediction.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    recommendations = [
        item
        for item in recommendations
        if isinstance(item, dict) and str(item.get("bet_type") or "") in SUPPORTED_BET_TYPES
    ]

    total_stake = sum(float(item.get("stake") or 0) for item in recommendations)

    hit_recommendations: list[dict[str, Any]] = []
    recommendation_results: list[dict[str, Any]] = []
    total_payout = 0.0
    payout_data_complete = True
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        stake = float(recommendation.get("stake") or 0)
        odds = float(recommendation.get("odds") or 0)
        tickets = max(int(float(recommendation.get("tickets") or 1)), 1)
        unit_stake = float(recommendation.get("unit_stake") or (stake / tickets if tickets else stake))
        winning_entries = _winning_entries(recommendation, order)
        recommendation_hit = bool(winning_entries)
        official_payouts = [
            _official_payout_for_entries(recommendation, race, order, [entry])
            for entry in winning_entries
        ]
        missing_official_payout = recommendation_hit and any(
            payout is None or payout <= 0 for payout in official_payouts
        )
        if missing_official_payout:
            payout_data_complete = False
        payout = sum(
            unit_stake * float(official_payout) / 100
            for official_payout in official_payouts
            if official_payout is not None and official_payout > 0
        )
        official_payout = next(
            (float(value) for value in official_payouts if value is not None and value > 0),
            None,
        )
        payable_hit = recommendation_hit and not missing_official_payout
        if payable_hit:
            hit_recommendations.append(recommendation)
            total_payout += payout
        recommendation_results.append(
            {
                "bet_type": recommendation.get("bet_type"),
                "strategy": recommendation.get("strategy") or recommendation.get("note"),
                "selection": recommendation.get("selection"),
                "hit": payable_hit,
                "selection_matched": recommendation_hit,
                "stake": stake,
                "odds": odds,
                "payout": payout,
                "official_payout_yen": official_payout,
                "winning_tickets": len(winning_entries),
                "payout_source": (
                    "official"
                    if recommendation_hit and not missing_official_payout
                    else "missing_official_payout"
                    if recommendation_hit
                    else "not_hit"
                ),
            }
        )

    roi = total_payout / total_stake if total_stake > 0 else 0.0
    hit = bool(hit_recommendations)
    enriched["result"] = {
        "settled": True,
        "hit": hit,
        "emoji": "🎯" if hit else "",
        "hit_count": len(hit_recommendations),
        "bet_count": len(recommendations),
        "stake": total_stake,
        "payout": total_payout,
        "roi": roi,
        "order": order,
        "recommendation_results": recommendation_results,
        "payout_data_complete": payout_data_complete,
        "excluded_from_roi": bool(enriched.get("generated_after_result") or enriched.get("official_prediction") is False),
        "message": (
            "🎯 的中"
            if hit and payout_data_complete
            else "的中判定あり / 払戻未取得"
            if not payout_data_complete
            else "不的中"
        ),
    }
    return enriched


def settle_history(
    history: dict[str, list[dict[str, Any]]],
    races: list[Race],
) -> dict[str, list[dict[str, Any]]]:
    races_by_id = {race.id: race for race in races}
    settled: dict[str, list[dict[str, Any]]] = {}
    for day, entries in history.items():
        settled[day] = [
            settle_prediction_entry(entry, races_by_id.get(str(entry.get("race_id") or "")))
            for entry in entries
            if isinstance(entry, dict)
        ]
    return settled
