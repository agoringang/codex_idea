from __future__ import annotations

import csv
import json
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import LiveSnapshot, Race


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
HISTORY_PATHS = (
    DATA_ROOT / "netkeiba_2026_normalized.csv",
    DATA_ROOT / "keiba_history_with_2026.csv",
    DATA_ROOT / "keiba_history_normalized.csv",
)
PUBLIC_RACE_WINDOW_PATH = Path(__file__).with_name("public_race_window_2026.json")
DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
TAIL_BYTES = 32 * 1024 * 1024
JRA_VENUES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}


def _surface_label(surface: str | None) -> str:
    if surface == "芝":
        return "芝"
    if surface in {"ダ", "ダート"}:
        return "ダート"
    return surface or "不明"


def _rating_from_odds(market_odds: float | None, finish_position: int | None) -> int:
    if market_odds is not None and market_odds > 0:
        return max(1, int(round(120 - min(market_odds, 100.0) * 3)))
    if finish_position is not None:
        return max(1, 120 - finish_position * 3)
    return 60


def _active_history_path() -> Path | None:
    for path in HISTORY_PATHS:
        if path.exists():
            return path
    return None


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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        return None


def _window_from_latest(path: Path) -> tuple[date, date] | None:
    latest = _parse_date(_read_latest_date(path))
    if latest is None:
        return None
    return latest - timedelta(days=15), latest + timedelta(days=16)


def _read_window_rows(path: Path, start_date: date, end_date: date) -> list[dict[str, Any]]:
    header = _read_csv_header(path)
    lines = _read_tail_lines(path)
    if not header or not lines:
        return []

    reader = csv.DictReader([header, *lines])
    rows: list[dict[str, Any]] = []
    for row in reader:
        race_date = _parse_date(row.get("race_date"))
        if race_date is not None and start_date <= race_date <= end_date:
            rows.append(row)
    return rows


def _int_value(row: dict[str, Any], column: str, default: int = 0) -> int:
    try:
        raw = row.get(column)
        if raw is None or raw == "":
            return default
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _float_value(row: dict[str, Any], column: str, default: float | None = None) -> float | None:
    try:
        raw = row.get(column)
        if raw is None or raw == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _runner_number(row: dict[str, Any], fallback: int) -> int:
    for column in ("runner_number", "horse_number", "number", "gate"):
        value = _int_value(row, column, 0)
        if value > 0:
            return value
    return fallback


def _gate_number(row: dict[str, Any], runner_number: int) -> int:
    gate = _int_value(row, "bracket", 0) or _int_value(row, "gate", 0)
    if gate > 0:
        return min(max(gate, 1), 8)
    return min(max((runner_number + 1) // 2, 1), 8)


def _race_group_sort(item: tuple[str, list[dict[str, Any]]]) -> tuple[str, str, int, str]:
    race_id, rows = item
    first = rows[0] if rows else {}
    race_no = _int_value(first, "race_no", 0)
    if race_no <= 0 and race_id[-2:].isdigit():
        race_no = int(race_id[-2:])
    return (
        str(first.get("race_date") or ""),
        str(first.get("venue") or ""),
        race_no or 999,
        race_id,
    )


def build_race_dicts_from_rows(
    rows: list[dict[str, Any]],
    *,
    source_name: str,
    source_checked_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_rows[(row.get("race_id") or "").strip()].append(row)

    races: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}
    checked_at = source_checked_at or datetime.now(timezone.utc).isoformat()

    for race_id, rows in sorted(grouped_rows.items(), key=_race_group_sort):
        if not race_id or not rows:
            continue

        rows = sorted(rows, key=lambda item: _runner_number(item, 999))
        first_row = rows[0]
        race_date = (first_row.get("race_date") or "").strip()
        parsed_race_date = _parse_date(race_date)
        if parsed_race_date is None:
            continue
        weekday = DAY_NAMES[parsed_race_date.weekday()]
        venue = (first_row.get("venue") or "").strip() or "不明"
        distance = first_row.get("distance") or ""
        surface = _surface_label((first_row.get("surface") or "").strip())
        going = (first_row.get("going") or "").strip()
        weather = (first_row.get("weather") or "").strip()
        race_no = f"{int(race_id[-2:])}R" if race_id[-2:].isdigit() else "--R"
        course_parts = [f"{surface} {distance}m".strip()]
        if going:
            course_parts.append(going)
        if weather:
            course_parts.append(weather)
        course = " / ".join(part for part in course_parts if part)

        runners: list[dict[str, Any]] = []
        result_order: list[int] = []
        for index, row in enumerate(rows, start=1):
            number = _runner_number(row, index)
            gate = _gate_number(row, number)
            finish_position = _int_value(row, "finish_position", 0) or None
            market_odds = _float_value(row, "market_odds")
            horse_weight = _int_value(row, "horse_weight", 0) or None
            horse_weight_diff = _int_value(row, "horse_weight_diff", 0)
            carried_weight = _float_value(row, "carried_weight")
            if finish_position is not None:
                result_order.append(number)

            tags = ["実データ", "検証済み"]
            if finish_position is not None:
                tags.append(f"{finish_position}着")
            if row.get("odds_rank"):
                tags.append(f"{_int_value(row, 'odds_rank', 0)}人気")

            runners.append(
                {
                    "number": number,
                    "gate": gate,
                    "name": (row.get("horse_name") or "").strip() or f"{number}番",
                    "jockey": (row.get("jockey") or "").strip() or "-",
                    "weight": f"{carried_weight:.1f}" if carried_weight else None,
                    "carriedWeight": carried_weight,
                    "horseWeight": horse_weight,
                    "horseWeightDiff": horse_weight_diff if horse_weight is not None else None,
                    "age": _int_value(row, "age", 0) or None,
                    "sex": (row.get("sex") or "").strip() or None,
                    "trainer": (row.get("trainer") or "").strip() or None,
                    "runningStyle": (row.get("running_style") or "").strip() or None,
                    "recentRecord": _recent_record(row),
                    "sire": (row.get("sire") or "").strip() or None,
                    "damSire": (row.get("dam_sire") or "").strip() or None,
                    "rating": _rating_from_odds(market_odds, finish_position),
                    "odds": float(market_odds or 1.0),
                    "tags": tags,
                }
            )

        finished_runners = [
            row
            for row in rows
            if _int_value(row, "finish_position", 0) > 0
        ]
        finished_runners.sort(key=lambda item: _int_value(item, "finish_position", 999))
        result_order = [
            _runner_number(row, 0)
            for row in finished_runners
            if _runner_number(row, 0) > 0
        ]
        is_finished = bool(result_order)
        market = "JRA" if venue in JRA_VENUES else "NAR"
        source_url = f"https://db.netkeiba.com/race/{race_id}/"
        if not is_finished:
            host = "race.netkeiba.com" if market == "JRA" else "nar.netkeiba.com"
            source_url = f"https://{host}/race/shutuba.html?race_id={race_id}"

        race_dict = {
            "id": race_id,
            "date": race_date,
            "day": weekday,
            "venue": venue,
            "meeting": f"{venue} 実データ",
            "raceNo": race_no,
            "start": "結果確定" if is_finished else "出走表",
            "title": f"{venue}{race_no} 実データ",
            "grade": market,
            "market": market,
            "course": course,
            "status": "finished" if is_finished else "open",
            "officialNote": f"{source_name}で照合済み / {race_date} / {len(rows)}頭",
            "source": source_name,
            "sourceUrl": source_url,
            "sourceCheckedAt": checked_at,
            "verificationStatus": "verified",
            "runners": runners,
        }
        snapshot_dict = {
            "racecard_status": "parsed",
            "odds_status": "closed",
            "result_status": "official" if is_finished else "waiting",
            "updated_at": race_date,
            "next_poll_seconds": 0,
            "odds_moves": [],
            "scratches": [],
            "result": {
                "status": "official" if is_finished else "pending",
                "message": f"{source_name}から生成された検証済みデータ {race_date}",
                "winning_selection": str(result_order[0]) if result_order else None,
                "order": result_order or None,
                "payout": 0,
            },
            "alerts": ["検証済みCSV", race_date],
        }
        races.append(race_dict)
        snapshots[race_id] = snapshot_dict

    return races, snapshots


@lru_cache(maxsize=16)
def _load_real_race_state(
    path_text: str,
    file_mtime_ns: int,
    start_date_text: str,
    end_date_text: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    path = Path(path_text)
    start_date = _parse_date(start_date_text)
    end_date = _parse_date(end_date_text)
    if not path.exists() or start_date is None or end_date is None:
        return [], {}

    return build_race_dicts_from_rows(
        _read_window_rows(path, start_date, end_date),
        source_name=path.name,
    )


def _recent_record(row: dict[str, Any]) -> str | None:
    win_rate = _float_value(row, "horse_recent_win_rate")
    place_rate = _float_value(row, "horse_recent_place_rate")
    if win_rate is None and place_rate is None:
        return None
    parts = []
    if win_rate is not None:
        parts.append(f"近走勝率{win_rate:.0%}")
    if place_rate is not None:
        parts.append(f"近走複勝{place_rate:.0%}")
    return " / ".join(parts)


def _load_public_window(start_date: date, end_date: date) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not PUBLIC_RACE_WINDOW_PATH.exists():
        return [], {}

    payload = json.loads(PUBLIC_RACE_WINDOW_PATH.read_text(encoding="utf-8"))
    raw_races = payload.get("races", [])
    if not isinstance(raw_races, list):
        return [], {}

    races: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}
    for race in raw_races:
        if not isinstance(race, dict):
            continue
        race_date = _parse_date(str(race.get("date") or ""))
        if race_date is None or not (start_date <= race_date <= end_date):
            continue
        race_id = str(race.get("id") or "")
        runners = race.get("runners") if isinstance(race.get("runners"), list) else []
        result_order: list[int] = []
        for runner in runners:
            if not isinstance(runner, dict):
                continue
            for tag in runner.get("tags") or []:
                if not isinstance(tag, str) or not tag.endswith("着"):
                    continue
                position = _int_value({"finish_position": tag.replace("着", "")}, "finish_position", 0)
                if position > 0:
                    result_order.append((position, _int_value(runner, "number", 0)))
        result_numbers = [number for _, number in sorted(result_order) if number > 0]
        races.append(race)
        snapshots[race_id] = {
            "racecard_status": "parsed",
            "odds_status": "closed",
            "result_status": "official" if result_numbers else "waiting",
            "updated_at": str(race.get("date") or ""),
            "next_poll_seconds": 0,
            "odds_moves": [],
            "scratches": [],
            "result": {
                "status": "official" if result_numbers else "pending",
                "message": str(race.get("officialNote") or "公開スナップショットから生成"),
                "winning_selection": str(result_numbers[0]) if result_numbers else None,
                "order": result_numbers or None,
                "payout": 0,
            },
            "alerts": ["公開スナップショット", str(race.get("date") or "")],
        }

    return races, snapshots


def _resolve_window(start_date: str | None, end_date: str | None, path: Path) -> tuple[date, date] | None:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is not None and end is not None:
        return start, end
    return _window_from_latest(path)


def _sort_race_dict(race: dict[str, Any]) -> tuple[str, str, int, str]:
    race_no = _int_value({"race_no": str(race.get("raceNo") or "").replace("R", "")}, "race_no", 999)
    return (
        str(race.get("date") or ""),
        str(race.get("venue") or ""),
        race_no,
        str(race.get("id") or ""),
    )


def _resolve_requested_window(
    start_date: str | None,
    end_date: str | None,
    path: Path | None,
) -> tuple[date, date] | None:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is not None and end is not None:
        return start, end
    if path is not None:
        return _window_from_latest(path)
    fallback_latest = date(2026, 5, 5)
    return fallback_latest - timedelta(days=15), fallback_latest + timedelta(days=16)


def get_races(start_date: str | None = None, end_date: str | None = None) -> list[Race]:
    """Return verified race cards built from normalized local history CSVs."""

    path = _active_history_path()
    window = _resolve_requested_window(start_date, end_date, path)
    if window is None:
        return []
    start, end = window

    raw_races: list[dict[str, Any]]
    if path is None:
        raw_races, _ = _load_public_window(start, end)
    else:
        file_mtime_ns = path.stat().st_mtime_ns
        raw_races, _ = _load_real_race_state(str(path), file_mtime_ns, start.isoformat(), end.isoformat())

    try:
        from .race_storage import fetch_race_cards

        stored_races = fetch_race_cards(start.isoformat(), end.isoformat())
    except Exception:
        stored_races = []

    merged = {str(race.get("id") or ""): race for race in raw_races}
    for race in stored_races:
        race_id = str(race.get("id") or "")
        if race_id:
            merged[race_id] = race

    return [Race(**deepcopy(race)) for race in sorted(merged.values(), key=_sort_race_dict)]


def get_snapshots() -> dict[str, LiveSnapshot]:
    """Return live snapshots derived from the same verified history source."""

    path = _active_history_path()
    if path is None:
        start = date(2026, 4, 20)
        end = date(2026, 5, 20)
        _, raw_snapshots = _load_public_window(start, end)
        return {race_id: LiveSnapshot(**deepcopy(snapshot)) for race_id, snapshot in raw_snapshots.items()}
    window = _window_from_latest(path)
    if window is None:
        return {}
    start, end = window
    file_mtime_ns = path.stat().st_mtime_ns
    _, raw_snapshots = _load_real_race_state(str(path), file_mtime_ns, start.isoformat(), end.isoformat())
    return {race_id: LiveSnapshot(**deepcopy(snapshot)) for race_id, snapshot in raw_snapshots.items()}
