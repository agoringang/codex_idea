from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


POPULARITY_PATTERN = re.compile(r"(\d+)人気")


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _number(value: Any, default: int = 0) -> int:
    try:
        parsed = int(float(str(value)))
    except (TypeError, ValueError):
        return default
    return parsed


def _float(value: Any) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _tags(runner: Any) -> list[str]:
    value = _value(runner, "tags", [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _popularity_tag(runner: Any) -> int | None:
    for tag in _tags(runner):
        match = POPULARITY_PATTERN.search(tag)
        if match:
            return _number(match.group(1))
    return None


def validate_race_runner_integrity(race: Any) -> dict[str, Any]:
    """Validate race-card identity fields before predictions/results are trusted.

    The checks intentionally focus on information that must never drift between
    scraping, odds overlay, prediction, and settlement: horse number, horse name,
    gate, and odds identity.
    """

    race_id = str(_value(race, "id", ""))
    runners = _value(race, "runners", [])
    if not isinstance(runners, list):
        runners = []

    errors: list[str] = []
    warnings: list[str] = []
    numbers = [_number(_value(runner, "number")) for runner in runners]
    names = [_text(_value(runner, "name")) for runner in runners]
    gates = [_number(_value(runner, "gate")) for runner in runners]
    odds = [_float(_value(runner, "odds")) for runner in runners]
    place_odds = [_float(_value(runner, "placeOdds")) for runner in runners]
    status = str(_value(race, "status", ""))
    finish_positions = [
        _number(tag.replace("着", ""))
        for runner in runners
        for tag in _tags(runner)
        if tag.endswith("着")
    ]

    if len(runners) < 2:
        errors.append("出走馬が2頭未満です")
    if len(runners) > 18:
        errors.append(f"出走馬数が18頭を超えています: {len(runners)}頭")
    if status == "finished" and len(runners) <= 3 and sorted(position for position in finish_positions if position > 0) == [1, 2, 3]:
        errors.append("出走馬表ではなく結果上位3頭のみ取得されています")

    invalid_numbers = [number for number in numbers if number <= 0 or number > 18]
    if invalid_numbers:
        errors.append(f"馬番が範囲外です: {invalid_numbers[:6]}")

    duplicated_numbers = sorted(number for number, count in Counter(numbers).items() if number > 0 and count > 1)
    if duplicated_numbers:
        errors.append(f"馬番が重複しています: {duplicated_numbers[:6]}")

    bad_names = [
        f"{number}:{name or '空欄'}"
        for number, name in zip(numbers, names, strict=False)
        if not name or re.fullmatch(r"[\d.\-倍人気]+", name)
    ]
    if bad_names:
        errors.append(f"馬名が不正です: {bad_names[:6]}")

    duplicated_names = sorted(name for name, count in Counter(names).items() if name and count > 1)
    if duplicated_names:
        errors.append(f"馬名が重複しています: {duplicated_names[:6]}")

    invalid_gates = [f"{number}:{gate}" for number, gate in zip(numbers, gates, strict=False) if gate <= 0 or gate > 8]
    if invalid_gates:
        errors.append(f"枠番が範囲外です: {invalid_gates[:6]}")

    odds_count = sum(1 for value in odds if value > 1.01)
    if 0 < odds_count < max(2, int(len(runners) * 0.7)):
        warnings.append(f"単勝オッズが一部のみ取得されています: {odds_count}/{len(runners)}頭")

    bad_place_odds = [
        f"{number}:複勝{place:.1f}>単勝{win:.1f}"
        for number, win, place in zip(numbers, odds, place_odds, strict=False)
        if place > 1.01 and win > 1.01 and place > win
    ]
    if bad_place_odds:
        errors.append(f"複勝オッズが単勝オッズを超えています: {bad_place_odds[:6]}")

    if odds_count >= max(2, int(len(runners) * 0.7)):
        odds_rank = {
            number: index + 1
            for index, (number, _odds) in enumerate(
                sorted(
                    ((number, odd) for number, odd in zip(numbers, odds, strict=False) if number > 0 and odd > 1.01),
                    key=lambda item: (item[1], item[0]),
                )
            )
        }
        rank_gaps: list[str] = []
        for runner, number in zip(runners, numbers, strict=False):
            tagged_rank = _popularity_tag(runner)
            computed_rank = odds_rank.get(number)
            if tagged_rank and computed_rank and abs(tagged_rank - computed_rank) >= 4:
                rank_gaps.append(f"{number}:タグ{tagged_rank}人気/単勝順位{computed_rank}")
        if rank_gaps:
            warnings.append(f"人気タグと単勝順位が大きくずれています: {rank_gaps[:6]}")

    return {
        "race_id": race_id,
        "errors": errors,
        "warnings": warnings,
        "runner_count": len(runners),
        "odds_count": odds_count,
        "checked": [
            "runner_number_unique",
            "horse_name_valid",
            "gate_range",
            "win_place_odds_consistency",
            "popularity_vs_odds_rank",
        ],
    }
