from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .schemas import Race


NUMBER_PATTERN = re.compile(r"\d+")


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


def _is_hit(recommendation: dict[str, Any], order: list[int]) -> bool:
    if not order:
        return False
    bet_type = recommendation.get("bet_type")
    entries = _recommendation_entries(recommendation)
    first = order[0]
    top2 = order[:2]
    top3 = order[:3]

    for entry in entries:
        if bet_type == "win" and entry[0] == first:
            return True
        if bet_type in {"place", "support"} and entry[0] in top3:
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

    total_stake = float(prediction.get("total_stake") or 0)
    if total_stake <= 0:
        total_stake = sum(float(item.get("stake") or 0) for item in recommendations if isinstance(item, dict))

    hit_recommendations: list[dict[str, Any]] = []
    recommendation_results: list[dict[str, Any]] = []
    total_payout = 0.0
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        stake = float(recommendation.get("stake") or 0)
        odds = float(recommendation.get("odds") or 0)
        recommendation_hit = _is_hit(recommendation, order)
        payout = stake * odds if recommendation_hit else 0.0
        if recommendation_hit:
            hit_recommendations.append(recommendation)
            total_payout += payout
        recommendation_results.append(
            {
                "bet_type": recommendation.get("bet_type"),
                "strategy": recommendation.get("strategy") or recommendation.get("note"),
                "selection": recommendation.get("selection"),
                "hit": recommendation_hit,
                "stake": stake,
                "odds": odds,
                "payout": payout,
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
        "message": "🎯 的中" if hit else "不的中",
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
