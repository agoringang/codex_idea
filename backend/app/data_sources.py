from __future__ import annotations

import csv
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import LiveSnapshot, Race


HISTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "keiba_history_normalized.csv"
DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
TAIL_BYTES = 4 * 1024 * 1024


def _surface_label(surface: str | None) -> str:
    if surface == "芝":
        return "芝"
    if surface == "ダ":
        return "ダート"
    return surface or "不明"


def _rating_from_odds(market_odds: float | None, finish_position: int | None) -> int:
    if market_odds is not None and market_odds > 0:
        return max(1, int(round(120 - min(market_odds, 100.0) * 3)))
    if finish_position is not None:
        return max(1, 120 - finish_position * 3)
    return 60


def _read_csv_header(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.readline().strip()


def _read_tail_lines(path: Path) -> list[str]:
    size = path.stat().st_size
    start = max(0, size - TAIL_BYTES)
    with path.open("rb") as handle:
        handle.seek(start)
        text = handle.read().decode("utf-8", errors="ignore")

    lines = [line for line in text.splitlines() if line.strip()]
    if start > 0 and lines:
        lines = lines[1:]
    return lines


def _read_latest_date(path: Path) -> str:
    if not path.exists():
        return ""

    header = next(csv.reader([_read_csv_header(path)]), [])
    if "race_date" not in header:
        return ""
    race_date_index = header.index("race_date")

    for line in reversed(_read_tail_lines(path)):
        row = next(csv.reader([line]), [])
        if len(row) > race_date_index and row[race_date_index].strip():
            return row[race_date_index].strip()
    return ""


def _read_latest_rows(path: Path, latest_date: str) -> list[dict[str, Any]]:
    header = _read_csv_header(path)
    lines = _read_tail_lines(path)
    if not header or not lines:
        return []

    reader = csv.DictReader([header, *lines])
    return [row for row in reader if (row.get("race_date") or "").strip() == latest_date]


@lru_cache(maxsize=1)
def _load_real_race_state(file_mtime_ns: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not HISTORY_PATH.exists():
        return [], {}

    latest_date = _read_latest_date(HISTORY_PATH)
    if not latest_date:
        return [], {}

    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_latest_rows(HISTORY_PATH, latest_date):
        grouped_rows[(row.get("race_id") or "").strip()].append(row)

    races: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}
    weekday = DAY_NAMES[datetime.fromisoformat(latest_date).weekday()]

    for race_id, rows in sorted(grouped_rows.items()):
        if not race_id or not rows:
            continue

        rows = sorted(rows, key=lambda item: int(item.get("number") or 0))
        first_row = rows[0]
        venue = (first_row.get("venue") or "").strip() or "不明"
        distance = first_row.get("distance") or ""
        surface = _surface_label((first_row.get("surface") or "").strip())
        race_no = f"{int(race_id[-2:])}R" if race_id[-2:].isdigit() else "--R"
        course = f"{surface} {distance}m".strip()

        runners: list[dict[str, Any]] = []
        result_order: list[int] = []
        for index, row in enumerate(rows, start=1):
            gate = int(row.get("gate") or index or 1)
            number = gate if gate > 0 else index
            finish_position = int(row.get("finish_position") or 0) or None
            market_odds = float(row.get("market_odds") or 0) if row.get("market_odds") else None
            place_odds = float(row.get("place_odds") or 0) if row.get("place_odds") else None
            if finish_position is not None:
                result_order.append(number)

            runners.append(
                {
                    "number": number,
                    "gate": gate,
                    "name": (row.get("horse_name") or "").strip() or f"{number}番",
                    "jockey": (row.get("jockey") or "").strip() or "-",
                    "weight": f"{float(row.get('carried_weight') or 0):.1f}" if row.get("carried_weight") else None,
                    "rating": _rating_from_odds(market_odds, finish_position),
                    "odds": float(row.get("market_odds") or 1.0),
                    "tags": ["実データ", f"{finish_position}着"] if finish_position is not None else ["実データ"],
                }
            )

        finished_runners = [row for row in rows if row.get("finish_position")]
        finished_runners.sort(key=lambda item: int(item.get("finish_position") or 999))
        result_order = [
            int(row.get("gate") or 0)
            for row in finished_runners
            if int(row.get("gate") or 0) > 0
        ]

        race_dict = {
            "id": race_id,
            "date": latest_date,
            "day": weekday,
            "venue": venue,
            "meeting": f"{venue} 実データ",
            "raceNo": race_no,
            "start": "未取得",
            "title": f"{venue}{race_no} 実データ",
            "grade": None,
            "course": course,
            "status": "finished",
            "officialNote": f"実データ履歴 {latest_date} / {len(rows)}頭",
            "source": HISTORY_PATH.name,
            "runners": runners,
        }
        snapshot_dict = {
            "racecard_status": "parsed",
            "odds_status": "closed",
            "result_status": "official",
            "updated_at": latest_date,
            "next_poll_seconds": 0,
            "odds_moves": [],
            "scratches": [],
            "result": {
                "status": "official",
                "message": f"履歴CSVから生成された実データ {latest_date}",
                "winning_selection": str(result_order[0]) if result_order else None,
                "order": result_order or None,
                "payout": 0,
            },
            "alerts": ["実データ履歴", latest_date],
        }
        races.append(race_dict)
        snapshots[race_id] = snapshot_dict

    return races, snapshots


def get_races() -> list[Race]:
    """Return race cards built from the real normalized history CSV."""

    file_mtime_ns = HISTORY_PATH.stat().st_mtime_ns if HISTORY_PATH.exists() else 0
    raw_races, _ = _load_real_race_state(file_mtime_ns)
    return [Race(**deepcopy(race)) for race in raw_races]


def get_snapshots() -> dict[str, LiveSnapshot]:
    """Return live snapshots derived from the same real history source."""

    file_mtime_ns = HISTORY_PATH.stat().st_mtime_ns if HISTORY_PATH.exists() else 0
    _, raw_snapshots = _load_real_race_state(file_mtime_ns)
    return {race_id: LiveSnapshot(**deepcopy(snapshot)) for race_id, snapshot in raw_snapshots.items()}
