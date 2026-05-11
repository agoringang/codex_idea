from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_SEED_PATH = Path(__file__).with_name("race_schedule_seed.json")
JST = timezone(timedelta(hours=9))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _default_window(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = datetime.now(JST).date()
    start = _parse_date(start_date) or today - timedelta(days=30)
    end = _parse_date(end_date) or today + timedelta(days=45)
    if end < start:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _market(value: Any) -> str | None:
    text = str(value or "").upper()
    if text in {"JRA", "NAR"}:
        return text
    return None


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date_in_window(value: str, start_date: str, end_date: str) -> bool:
    return start_date <= value <= end_date


def _schedule_seed_path() -> Path:
    configured = os.getenv("UMALAB_RACE_SCHEDULE_SEED")
    return Path(configured) if configured else DEFAULT_SEED_PATH


def _load_seed_entries(start_date: str, end_date: str) -> list[dict[str, Any]]:
    path = _schedule_seed_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entry_date = _clean_text(item.get("date") or item.get("race_date"))
        market = _market(item.get("market"))
        venues = item.get("venues")
        if not entry_date or not market or not isinstance(venues, list) or not _date_in_window(entry_date, start_date, end_date):
            continue
        grade_races = item.get("gradeRaces") or item.get("grade_races") or []
        if not isinstance(grade_races, list):
            grade_races = []
        for venue in venues:
            venue_text = _clean_text(venue)
            if not venue_text:
                continue
            entries.append(
                {
                    "date": entry_date,
                    "market": market,
                    "venue": venue_text,
                    "raceCount": 0,
                    "gradeRaces": [_clean_text(value) for value in grade_races if _clean_text(value)],
                    "source": _clean_text(item.get("source")) or "seed",
                    "sourceCheckedAt": item.get("sourceCheckedAt") or item.get("source_checked_at"),
                }
            )
    return entries


def _stored_entries(start_date: str, end_date: str) -> list[dict[str, Any]]:
    try:
        from .race_storage import fetch_race_schedule

        rows = fetch_race_schedule(start_date, end_date)
    except Exception:
        return []

    entries: list[dict[str, Any]] = []
    for row in rows:
        entry_date = _clean_text(row.get("race_date") or row.get("date"))
        market = _market(row.get("market"))
        venue = _clean_text(row.get("venue"))
        if not entry_date or not market or not venue:
            continue
        grade_races = row.get("grade_races") or []
        if not isinstance(grade_races, list):
            grade_races = []
        entries.append(
            {
                "date": entry_date,
                "market": market,
                "venue": venue,
                "raceCount": int(row.get("race_count") or 0),
                "gradeRaces": [_clean_text(value) for value in grade_races if _clean_text(value)],
                "source": _clean_text(row.get("source")) or "supabase",
                "sourceCheckedAt": row.get("source_checked_at"),
            }
        )
    return entries


def schedule_entries_from_race_dicts(races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    grade_titles: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for race in races:
        if not isinstance(race, dict):
            continue
        entry_date = _clean_text(race.get("date"))
        market = _market(race.get("market"))
        venue = _clean_text(race.get("venue"))
        if not entry_date or not market or not venue:
            continue
        key = (entry_date, market, venue)
        current = grouped.setdefault(
            key,
            {
                "date": entry_date,
                "market": market,
                "venue": venue,
                "raceCount": 0,
                "gradeRaces": [],
                "source": "race_cards",
                "sourceCheckedAt": race.get("sourceCheckedAt") or race.get("source_checked_at"),
            },
        )
        current["raceCount"] = int(current.get("raceCount") or 0) + 1
        checked_at = race.get("sourceCheckedAt") or race.get("source_checked_at")
        if checked_at and str(checked_at) > str(current.get("sourceCheckedAt") or ""):
            current["sourceCheckedAt"] = checked_at

        title = _clean_text(race.get("title"))
        grade = _clean_text(race.get("grade"))
        if title and (grade.startswith("G") or "重賞" in title or title.endswith(("S", "C"))):
            grade_titles[key].add(title)

    for key, titles in grade_titles.items():
        grouped[key]["gradeRaces"] = sorted(titles)
    return list(grouped.values())


def _race_card_entries(start_date: str, end_date: str) -> list[dict[str, Any]]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is not None and end is not None and (end - start).days > 3:
        return []
    try:
        from .data_sources import get_races

        races = get_races(start_date=start_date, end_date=end_date)
    except Exception:
        return []
    return schedule_entries_from_race_dicts([race.model_dump(mode="json") for race in races])


def _race_card_metadata_entries(start_date: str, end_date: str) -> list[dict[str, Any]]:
    try:
        from .race_storage import fetch_race_card_schedule_rows

        rows = fetch_race_card_schedule_rows(start_date, end_date)
    except Exception:
        return []

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    race_numbers: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for row in rows:
        entry_date = _clean_text(row.get("race_date") or row.get("date"))
        market = _market(row.get("market"))
        venue = _clean_text(row.get("venue"))
        if not entry_date or not market or not venue:
            continue
        key = (entry_date, market, venue)
        current = grouped.setdefault(
            key,
            {
                "date": entry_date,
                "market": market,
                "venue": venue,
                "raceCount": 0,
                "gradeRaces": [],
                "source": "race_cards",
                "sourceCheckedAt": row.get("source_checked_at"),
            },
        )
        try:
            race_no = int(row.get("race_no") or 0)
        except (TypeError, ValueError):
            race_no = 0
        if race_no > 0:
            race_numbers[key].add(race_no)
        checked_at = row.get("source_checked_at")
        if checked_at and str(checked_at) > str(current.get("sourceCheckedAt") or ""):
            current["sourceCheckedAt"] = checked_at

    for key, numbers in race_numbers.items():
        grouped[key]["raceCount"] = len(numbers)
    return list(grouped.values())


def _merge_entries(*entry_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entries in entry_sets:
        for entry in entries:
            key = (
                _clean_text(entry.get("date")),
                _clean_text(entry.get("market")),
                _clean_text(entry.get("venue")),
            )
            if not all(key):
                continue
            current = merged.get(key)
            if current is None:
                merged[key] = dict(entry)
                continue
            grade_races = []
            for title in [*(current.get("gradeRaces") or []), *(entry.get("gradeRaces") or [])]:
                title_text = _clean_text(title)
                if title_text and title_text not in grade_races:
                    grade_races.append(title_text)
            merged[key] = {
                **current,
                **entry,
                "raceCount": max(int(current.get("raceCount") or 0), int(entry.get("raceCount") or 0)),
                "gradeRaces": grade_races,
            }
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in merged.values():
        key = (_clean_text(entry.get("date")), _clean_text(entry.get("market")))
        current = grouped.setdefault(
            key,
            {
                "date": key[0],
                "market": key[1],
                "venues": [],
                "gradeRaces": [],
                "raceCount": 0,
                "source": entry.get("source") or "",
                "sourceCheckedAt": entry.get("sourceCheckedAt"),
            },
        )
        venue = _clean_text(entry.get("venue"))
        if venue and venue not in current["venues"]:
            current["venues"].append(venue)
        for title in entry.get("gradeRaces") or []:
            title_text = _clean_text(title)
            if title_text and title_text not in current["gradeRaces"]:
                current["gradeRaces"].append(title_text)
        current["raceCount"] = int(current.get("raceCount") or 0) + int(entry.get("raceCount") or 0)
        checked_at = entry.get("sourceCheckedAt")
        if checked_at and str(checked_at) > str(current.get("sourceCheckedAt") or ""):
            current["sourceCheckedAt"] = checked_at
        source = _clean_text(entry.get("source"))
        if source == "race_cards" or not current.get("source"):
            current["source"] = source

    return sorted(
        grouped.values(),
        key=lambda item: (item["date"], 0 if item["market"] == "JRA" else 1, "・".join(item["venues"])),
    )


def get_race_schedule(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    start, end = _default_window(start_date, end_date)
    # Priority: seed fallback < stored schedule < light race-card metadata < full race-card payloads.
    return _merge_entries(
        _load_seed_entries(start, end),
        _stored_entries(start, end),
        _race_card_metadata_entries(start, end),
        _race_card_entries(start, end),
    )


def upsert_schedule_from_race_dicts(races: list[dict[str, Any]]) -> int:
    entries = schedule_entries_from_race_dicts(races)
    try:
        from .race_storage import upsert_race_schedule

        return upsert_race_schedule(entries)
    except Exception:
        return 0
