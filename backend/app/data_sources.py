from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import re
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .runner_integrity import validate_race_runner_integrity
from .runner_state import canonical_runner_status, runner_is_inactive_dict
from .schemas import LiveSnapshot, Race


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
HISTORY_PATHS = (
    DATA_ROOT / "netkeiba_2026_enriched.csv",
    DATA_ROOT / "keiba_history_with_2026_enriched.csv",
    DATA_ROOT / "netkeiba_2026_normalized.csv",
    DATA_ROOT / "keiba_history_with_2026.csv",
    DATA_ROOT / "keiba_history_normalized.csv",
)
HISTORY_READ_ORDER = tuple(reversed(HISTORY_PATHS))
REMOTE_HISTORY_URLS_ENV = "UMALAB_HISTORY_CSV_URLS"
REMOTE_HISTORY_SHA_ENV = "UMALAB_HISTORY_CSV_SHA256S"
REMOTE_HISTORY_CACHE_DIR_ENV = "UMALAB_HISTORY_CACHE_DIR"
PUBLIC_RACE_WINDOW_PATH = Path(__file__).with_name("public_race_window_2026.json")
DAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
TAIL_BYTES = 32 * 1024 * 1024
FULL_READ_MAX_BYTES = 160 * 1024 * 1024
JRA_VENUES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
JRA_COURSE_CODE_VENUES = {
    "01": "札幌",
    "02": "函館",
    "03": "福島",
    "04": "新潟",
    "05": "東京",
    "06": "中山",
    "07": "中京",
    "08": "京都",
    "09": "阪神",
    "10": "小倉",
}


def _runner_status_from_row(row: dict[str, Any]) -> str | None:
    for column in (
        "runner_status",
        "runnerStatus",
        "status",
        "result_status",
        "remarks",
        "note",
        "備考",
        "状態",
        "finish_position",
        "着順",
    ):
        status = canonical_runner_status(row.get(column))
        if status:
            return status
    for column in ("market_odds", "place_odds", "odds_rank"):
        status = canonical_runner_status(row.get(column))
        if status:
            return status
    return None


def _surface_label(surface: str | None) -> str:
    if surface == "芝":
        return "芝"
    if surface in {"ダ", "ダート"}:
        return "ダート"
    return surface or "不明"


def _clean_text(value: str | None) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _estimated_start_time(race_no: int, market: str) -> str | None:
    if race_no <= 0:
        return None
    jra_times = {
        1: "09:50",
        2: "10:20",
        3: "10:50",
        4: "11:20",
        5: "12:10",
        6: "12:40",
        7: "13:10",
        8: "13:40",
        9: "14:15",
        10: "14:50",
        11: "15:30",
        12: "16:10",
    }
    nar_times = {
        1: "10:30",
        2: "11:00",
        3: "11:30",
        4: "12:05",
        5: "12:40",
        6: "13:15",
        7: "13:50",
        8: "14:25",
        9: "15:05",
        10: "15:45",
        11: "16:25",
        12: "17:05",
    }
    return (jra_times if market == "JRA" else nar_times).get(race_no)


def _start_label(row: dict[str, Any], is_finished: bool, race_no: int, market: str) -> str:
    for column in ("start_time", "post_time", "race_time", "発走時刻"):
        value = _clean_text(row.get(column))
        if value:
            match = re.search(r"\d{1,2}:\d{2}", value)
            return match.group(0) if match else value
    estimated = _estimated_start_time(race_no, market)
    if estimated:
        return f"推定 {estimated}"
    return "結果確定" if is_finished else "時刻確認中"


def _trusted_place_odds(row: dict[str, Any], win_odds: float | None) -> float | None:
    place_odds = _float_value(row, "place_odds")
    if place_odds is None or place_odds <= 1 or win_odds is None or win_odds <= 1:
        return None
    if place_odds > win_odds:
        return None

    legacy_estimate = round(max(1.1, min(win_odds, win_odds / 4.0)), 2)
    conservative_estimate = round(max(1.1, min(8.0, 1.05 + max(win_odds - 1.0, 0.0) * 0.09)), 2)
    rounded = round(place_odds, 2)
    if abs(rounded - legacy_estimate) < 0.015:
        return None
    if abs(rounded - conservative_estimate) < 0.015:
        return None
    return place_odds


def _row_float(row: dict[str, Any], column: str) -> float | None:
    try:
        value = float(str(row.get(column, "")).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _rating_from_runner_features(row: dict[str, Any]) -> int:
    scores: list[float] = []
    for column in (
        "speed",
        "condition",
        "pace",
        "stamina",
        "avg_last3_speed",
        "training_score",
        "bloodline_score",
        "paddock_score",
    ):
        value = _row_float(row, column)
        if value is not None and value > 0:
            scores.append(max(1.0, min(100.0, value)))

    for column in (
        "jockey_win_rate",
        "trainer_win_rate",
        "horse_recent_win_rate",
        "horse_recent_place_rate",
        "horse_distance_place_rate",
        "horse_surface_place_rate",
    ):
        value = _row_float(row, column)
        if value is not None:
            scores.append(max(35.0, min(92.0, 48.0 + value * 58.0)))

    draw_bias = _row_float(row, "draw_bias")
    if draw_bias is not None:
        scores.append(max(42.0, min(78.0, 58.0 + draw_bias * 9.0)))

    weight_diff = _row_float(row, "horse_weight_diff")
    if weight_diff is not None:
        if abs(weight_diff) <= 4:
            scores.append(66.0)
        elif abs(weight_diff) >= 18:
            scores.append(46.0)

    if not scores:
        return 60
    return max(1, min(100, int(round(sum(scores) / len(scores)))))


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]


def _history_cache_dir() -> Path:
    configured = os.getenv(REMOTE_HISTORY_CACHE_DIR_ENV)
    if configured:
        return Path(configured)
    if os.getenv("VERCEL"):
        return Path("/tmp/umalab-history-csv")
    return DATA_ROOT / ".remote"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path_for_history_url(url: str) -> Path:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "umalab_history.csv"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return _history_cache_dir() / f"{digest}-{filename}"


def _download_history_csv(url: str, expected_sha256: str | None = None) -> Path:
    cache_path = _cache_path_for_history_url(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists() and cache_path.stat().st_size > 0:
        if expected_sha256 and _sha256_file(cache_path).lower() != expected_sha256.lower():
            cache_path.unlink(missing_ok=True)
        else:
            return cache_path

    tmp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    request = Request(url, headers={"User-Agent": "UmaLab/0.2 history-loader"})
    with urlopen(request, timeout=180) as response, tmp_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)

    if expected_sha256:
        actual = _sha256_file(tmp_path)
        if actual.lower() != expected_sha256.lower():
            tmp_path.unlink(missing_ok=True)
            raise ValueError(f"{REMOTE_HISTORY_SHA_ENV} mismatch for {url}: expected {expected_sha256}, got {actual}")

    tmp_path.replace(cache_path)
    return cache_path


@lru_cache(maxsize=4)
def _remote_history_paths_from_env(urls_text: str, shas_text: str) -> tuple[Path, ...]:
    urls = _split_env_list(urls_text)
    shas = _split_env_list(shas_text)
    paths: list[Path] = []
    for index, url in enumerate(urls):
        expected_sha = shas[index] if index < len(shas) else None
        paths.append(_download_history_csv(url, expected_sha))
    return tuple(paths)


def _remote_history_paths() -> list[Path]:
    urls_text = os.getenv(REMOTE_HISTORY_URLS_ENV, "")
    if not urls_text.strip():
        return []
    return list(_remote_history_paths_from_env(urls_text, os.getenv(REMOTE_HISTORY_SHA_ENV, "")))


def _existing_history_paths() -> list[Path]:
    local_paths = [path for path in HISTORY_READ_ORDER if path.exists()]
    remote_paths = _remote_history_paths()
    return [*local_paths, *remote_paths]


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


def _read_data_lines(path: Path) -> list[str]:
    if path.stat().st_size <= FULL_READ_MAX_BYTES:
        with path.open("r", encoding="utf-8", newline="") as handle:
            lines = handle.read().splitlines()
        return [line for line in lines[1:] if line.strip()]
    return _read_tail_lines(path)


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


def _window_from_latest(paths: list[Path]) -> tuple[date, date] | None:
    latest_dates = [
        parsed
        for parsed in (_parse_date(_read_latest_date(path)) for path in paths)
        if parsed is not None
    ]
    if not latest_dates:
        return None
    latest = max(latest_dates)
    return latest - timedelta(days=15), latest + timedelta(days=16)


def _read_window_rows(path: Path, start_date: date, end_date: date) -> list[dict[str, Any]]:
    header = _read_csv_header(path)
    lines = _read_data_lines(path)
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


def _horse_weight_value(row: dict[str, Any]) -> int | None:
    value = _int_value(row, "horse_weight", 0)
    if not 250 <= value <= 700:
        return None
    return value


def _horse_weight_diff_value(row: dict[str, Any], horse_weight: int | None) -> int | None:
    if horse_weight is None:
        return None
    value = _int_value(row, "horse_weight_diff", 0)
    if value == 0:
        return 0
    if abs(value) > 80:
        return None
    return value


def _race_payout_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("payouts_json")
    if not raw:
        return []
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        bet_type = str(item.get("bet_type") or item.get("betType") or "").strip()
        selection = _clean_text(item.get("selection"))
        payout = _float_value(
            {"payout": item.get("payout_yen") or item.get("payoutYen")},
            "payout",
        )
        if not bet_type or not selection or not payout:
            continue
        key = (bet_type, selection, float(payout))
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "betType": bet_type,
                "selection": selection,
                "payoutYen": float(payout),
                "popularity": _int_value({"popularity": item.get("popularity")}, "popularity", 0) or None,
            }
        )
    return items


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


def _venue_from_race_id(race_id: str, fallback: str) -> str:
    if len(race_id) >= 6 and race_id[:4].isdigit():
        venue = JRA_COURSE_CODE_VENUES.get(race_id[4:6])
        if venue:
            return venue
    return fallback


def build_race_dicts_from_rows(
    rows: list[dict[str, Any]],
    *,
    source_name: str,
    source_checked_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_rows[str(row.get("race_id") or "").strip()].append(row)

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
        venue = _venue_from_race_id(race_id, (first_row.get("venue") or "").strip() or "不明")
        distance = first_row.get("distance") or ""
        surface = _surface_label((first_row.get("surface") or "").strip())
        going = _clean_text(first_row.get("going"))
        weather = _clean_text(first_row.get("weather"))
        race_no = f"{int(race_id[-2:])}R" if race_id[-2:].isdigit() else "--R"
        race_no_value = _int_value(first_row, "race_no", 0)
        if race_no_value <= 0 and race_id[-2:].isdigit():
            race_no_value = int(race_id[-2:])
        course_parts = [f"{surface} {distance}m".strip()]
        if going:
            course_parts.append(going)
        if weather:
            course_parts.append(weather)
        course = " / ".join(part for part in course_parts if part)
        market = "JRA" if venue in JRA_VENUES else "NAR"

        runners: list[dict[str, Any]] = []
        result_order: list[int] = []
        for index, row in enumerate(rows, start=1):
            number = _runner_number(row, index)
            gate = _gate_number(row, number)
            finish_position = _int_value(row, "finish_position", 0) or None
            runner_status = _runner_status_from_row(row)
            scratched = runner_status is not None
            market_odds = _float_value(row, "market_odds")
            place_odds = _trusted_place_odds(row, market_odds)
            horse_weight = _horse_weight_value(row)
            horse_weight_diff = _horse_weight_diff_value(row, horse_weight)
            carried_weight = _float_value(row, "carried_weight")
            if finish_position is not None:
                result_order.append(number)

            tags = ["実データ", "検証済み"]
            if runner_status:
                tags.append(runner_status)
            if finish_position is not None:
                tags.append(f"{finish_position}着")
            if row.get("odds_rank"):
                tags.append(f"{_int_value(row, 'odds_rank', 0)}人気")

            runners.append(
                {
                    "number": number,
                    "gate": gate,
                    "name": _clean_text(row.get("horse_name")) or f"{number}番",
                    "jockey": _clean_text(row.get("jockey")) or "-",
                    "weight": f"{carried_weight:.1f}" if carried_weight else None,
                    "carriedWeight": carried_weight,
                    "horseWeight": horse_weight,
                    "horseWeightDiff": horse_weight_diff if horse_weight is not None else None,
                    "age": _int_value(row, "age", 0) or None,
                    "sex": _clean_text(row.get("sex")) or None,
                    "trainer": _clean_text(row.get("trainer")) or None,
                    "runningStyle": _clean_text(row.get("running_style")) or None,
                    "recentRecord": _recent_record(row),
                    "daysSinceLastRun": _int_value(row, "days_since_last_run", 0) or None,
                    "avgLast3Speed": _float_value(row, "avg_last3_speed"),
                    "bestTime": _float_value(row, "best_time"),
                    "last600m": _float_value(row, "last600m"),
                    "jockeyWinRate": _float_value(row, "jockey_win_rate"),
                    "trainerWinRate": _float_value(row, "trainer_win_rate"),
                    "horseRecentWinRate": _float_value(row, "horse_recent_win_rate"),
                    "horseRecentPlaceRate": _float_value(row, "horse_recent_place_rate"),
                    "horseDistancePlaceRate": _float_value(row, "horse_distance_place_rate"),
                    "horseSurfacePlaceRate": _float_value(row, "horse_surface_place_rate"),
                    "trainingScore": _float_value(row, "training_score"),
                    "bloodlineScore": _float_value(row, "bloodline_score"),
                    "paddockScore": _float_value(row, "paddock_score"),
                    "oddsDelta": _float_value(row, "odds_delta"),
                    "oddsDelta5m": _float_value(row, "odds_delta_5m"),
                    "oddsDelta15m": _float_value(row, "odds_delta_15m"),
                    "oddsVolatility": _float_value(row, "odds_volatility"),
                    "ticketPoolShare": _float_value(row, "ticket_pool_share"),
                    "lap3f": _float_value(row, "lap_3f"),
                    "lap4f": _float_value(row, "lap_4f"),
                    "bodyWeightAnnouncedAt": _clean_text(row.get("body_weight_announced_at")) or None,
                    "payoutWin": _float_value(row, "payout_win"),
                    "payoutPlace": _float_value(row, "payout_place"),
                    "payoutQuinella": _float_value(row, "payout_quinella"),
                    "payoutWide": _float_value(row, "payout_wide"),
                    "payoutExacta": _float_value(row, "payout_exacta"),
                    "payoutTrio": _float_value(row, "payout_trio"),
                    "payoutTrifecta": _float_value(row, "payout_trifecta"),
                    "drawBias": _float_value(row, "draw_bias"),
                    "sireId": _clean_text(row.get("sire_id")) or None,
                    "sire": _clean_text(row.get("sire")) or None,
                    "damSireId": _clean_text(row.get("dam_sire_id")) or None,
                    "damSire": _clean_text(row.get("dam_sire")) or None,
                    "rating": _rating_from_runner_features(row),
                    "odds": 0.0 if scratched else float(market_odds) if market_odds and market_odds > 1 else 0.0,
                    "placeOdds": None if scratched else place_odds,
                    "scratched": scratched,
                    "runnerStatus": runner_status,
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
            "start": _start_label(first_row, is_finished, race_no_value, market),
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
            "payouts": _race_payout_items(first_row),
            "runners": runners,
        }
        snapshot_dict = {
            "racecard_status": "parsed",
            "odds_status": "closed",
            "result_status": "official" if is_finished else "waiting",
            "updated_at": race_date,
            "next_poll_seconds": 0,
            "odds_moves": [],
            "scratches": [
                {
                    "number": runner["number"],
                    "name": runner["name"],
                    "reason": runner.get("runnerStatus") or "取消",
                }
                for runner in runners
                if runner_is_inactive_dict(runner)
            ],
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


def _merge_race_states(
    states: list[tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    merged_races: dict[str, dict[str, Any]] = {}
    merged_snapshots: dict[str, dict[str, Any]] = {}
    for races, snapshots in states:
        for race in races:
            race_id = str(race.get("id") or "")
            if race_id:
                merged_races[race_id] = race
        merged_snapshots.update(snapshots)
    return _collapse_duplicate_races(list(merged_races.values())), merged_snapshots


def _load_history_sources(
    paths: list[Path],
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    states: list[tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]] = []
    for path in paths:
        file_mtime_ns = path.stat().st_mtime_ns
        states.append(
            _load_real_race_state(
                str(path),
                file_mtime_ns,
                start.isoformat(),
                end.isoformat(),
            )
        )
    return _merge_race_states(states)


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
    return _window_from_latest([path])


def _sort_race_dict(race: dict[str, Any]) -> tuple[str, str, int, str]:
    race_no = _int_value({"race_no": str(race.get("raceNo") or "").replace("R", "")}, "race_no", 999)
    return (
        str(race.get("date") or ""),
        str(race.get("venue") or ""),
        race_no,
        str(race.get("id") or ""),
    )


def _race_display_key(race: dict[str, Any]) -> tuple[str, str, int]:
    date_text = str(race.get("date") or "")
    venue = str(race.get("venue") or "")
    race_no = _int_value({"race_no": str(race.get("raceNo") or "").replace("R", "")}, "race_no", 999)
    return date_text, venue, race_no


def _race_feature_count(race: dict[str, Any]) -> int:
    feature_keys = {
        "horseWeight",
        "horseWeightDiff",
        "daysSinceLastRun",
        "avgLast3Speed",
        "last600m",
        "jockeyWinRate",
        "trainerWinRate",
        "horseRecentWinRate",
        "horseRecentPlaceRate",
        "horseDistancePlaceRate",
        "horseSurfacePlaceRate",
        "trainingScore",
        "bloodlineScore",
        "paddockScore",
        "oddsDelta",
        "ticketPoolShare",
        "drawBias",
        "sire",
        "damSire",
    }
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    count = 0
    for runner in runners:
        if not isinstance(runner, dict):
            continue
        count += sum(1 for key in feature_keys if runner.get(key) not in (None, "", []))
    return count


def _race_quality_score(race: dict[str, Any]) -> tuple[int, int, int, int, str]:
    source = str(race.get("source") or "")
    source_score = 0
    if "live scrape" in source:
        source_score = 4
    elif "netkeiba_2026" in source:
        source_score = 3
    elif "with_2026" in source:
        source_score = 2
    elif "normalized" in source:
        source_score = 1
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    result_score = 1 if str(race.get("status") or "") == "finished" else 0
    start = str(race.get("start") or "")
    start_score = 1 if re.search(r"\d{1,2}:\d{2}", start) and not start.startswith("推定") else 0
    return (
        source_score,
        result_score,
        start_score,
        len(runners) + _race_feature_count(race),
        str(race.get("sourceCheckedAt") or ""),
    )


def _sanitize_race_payload(race: dict[str, Any]) -> dict[str, Any]:
    race = deepcopy(race)
    course = race.get("course")
    if isinstance(course, str):
        race["course"] = _clean_text(course)

    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    raw_numbers: list[int] = []
    for runner in runners:
        if not isinstance(runner, dict):
            continue
        try:
            raw_numbers.append(int(float(str(runner.get("number")))))
        except (TypeError, ValueError):
            raw_numbers.append(0)
    valid_raw_numbers = [number for number in raw_numbers if number > 0]
    force_sequential_numbers = (
        any(number > 18 for number in valid_raw_numbers)
        or len(set(valid_raw_numbers)) != len(valid_raw_numbers)
    )
    seen_numbers: set[int] = set()
    for index, runner in enumerate(runners, start=1):
        if not isinstance(runner, dict):
            continue

        try:
            number = int(float(str(runner.get("number"))))
        except (TypeError, ValueError):
            number = index
        if force_sequential_numbers:
            number = index
        if number <= 0 or number > 18 or number in seen_numbers:
            number = next(
                (candidate for candidate in range(1, max(19, len(runners) + 1)) if candidate not in seen_numbers),
                index,
            )
        runner["number"] = number
        if force_sequential_numbers or not runner.get("gate"):
            runner["gate"] = min(max((number + 1) // 2, 1), 8)
        seen_numbers.add(number)

        name = _clean_text(runner.get("name"))
        if not name or re.fullmatch(r"[\d.\-倍人気]+", name):
            runner["name"] = f"{number}番"
        else:
            runner["name"] = name

        try:
            horse_weight = int(float(str(runner.get("horseWeight"))))
        except (TypeError, ValueError):
            horse_weight = 0
        if not 250 <= horse_weight <= 700:
            runner["horseWeight"] = None
            runner["horseWeightDiff"] = None
        else:
            runner["horseWeight"] = horse_weight
            try:
                horse_weight_diff = int(float(str(runner.get("horseWeightDiff"))))
            except (TypeError, ValueError):
                horse_weight_diff = 0
            runner["horseWeightDiff"] = horse_weight_diff if abs(horse_weight_diff) <= 80 else None

        status = canonical_runner_status(runner.get("runnerStatus")) or canonical_runner_status(runner.get("runner_status"))
        if status:
            runner["runnerStatus"] = status
            runner["scratched"] = True
        if runner_is_inactive_dict(runner):
            runner["scratched"] = True
            runner["runnerStatus"] = status or canonical_runner_status(runner.get("status")) or "取消"
            tags = runner.get("tags") if isinstance(runner.get("tags"), list) else []
            if runner["runnerStatus"] not in tags:
                tags.append(runner["runnerStatus"])
            runner["tags"] = [
                tag
                for tag in tags
                if not (isinstance(tag, str) and tag.endswith("人気"))
            ]
            runner["odds"] = 0.0
            runner["placeOdds"] = None
            runner["payoutWin"] = None
            runner["payoutPlace"] = None
            continue

        try:
            win_odds = float(str(runner.get("odds")))
        except (TypeError, ValueError):
            win_odds = 0.0
        if not math.isfinite(win_odds) or win_odds <= 1:
            runner["odds"] = 0.0
            runner["placeOdds"] = None
            if isinstance(runner.get("tags"), list):
                runner["tags"] = [
                    tag
                    for tag in runner["tags"]
                    if not (isinstance(tag, str) and tag.endswith("人気"))
                ]
            continue
        runner["odds"] = win_odds

        try:
            place_odds = float(str(runner.get("placeOdds")))
        except (TypeError, ValueError):
            place_odds = 0.0
        if not math.isfinite(place_odds) or place_odds <= 1 or place_odds > win_odds:
            runner["placeOdds"] = None
        else:
            runner["placeOdds"] = place_odds

    return race


def _apply_runner_integrity_status(race: dict[str, Any]) -> dict[str, Any]:
    report = validate_race_runner_integrity(race)
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if not errors:
        return race

    race = deepcopy(race)
    race["verificationStatus"] = "unverified"
    current_note = _clean_text(race.get("officialNote"))
    issue_text = " / ".join(str(error) for error in errors[:3])
    integrity_note = f"出走馬整合性要確認: {issue_text}"
    race["officialNote"] = f"{current_note} / {integrity_note}" if current_note else integrity_note
    return race


def _runner_finish_tags(race: dict[str, Any]) -> dict[int, list[str]]:
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    finish_tags: dict[int, list[str]] = {}
    for runner in runners:
        if not isinstance(runner, dict):
            continue
        number = _int_value(runner, "number", 0)
        tags = runner.get("tags") if isinstance(runner.get("tags"), list) else []
        values = [str(tag) for tag in tags if isinstance(tag, str) and tag.endswith("着")]
        if number > 0 and values:
            finish_tags[number] = values
    return finish_tags


def _is_top3_only_result(race: dict[str, Any]) -> bool:
    if str(race.get("status") or "") != "finished":
        return False
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    if len(runners) > 3:
        return False
    finish_positions: list[int] = []
    for runner in runners:
        if not isinstance(runner, dict):
            continue
        tags = runner.get("tags") if isinstance(runner.get("tags"), list) else []
        for tag in tags:
            if not isinstance(tag, str) or not tag.endswith("着"):
                continue
            value = _int_value({"finish_position": tag.replace("着", "")}, "finish_position", 0)
            if value > 0:
                finish_positions.append(value)
    return sorted(finish_positions) == [1, 2, 3]


def _merge_duplicate_race_payloads(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_runners = first.get("runners") if isinstance(first.get("runners"), list) else []
    second_runners = second.get("runners") if isinstance(second.get("runners"), list) else []
    first_finished = str(first.get("status") or "") == "finished"
    second_finished = str(second.get("status") or "") == "finished"
    card = second if len(second_runners) > len(first_runners) else first
    result = second if second_finished else first if first_finished else None

    if result is None or card is result:
        if _is_top3_only_result(second) and len(first_runners) > len(second_runners):
            result = second
            card = first
        elif _is_top3_only_result(first) and len(second_runners) > len(first_runners):
            result = first
            card = second
        else:
            return second if _race_quality_score(second) >= _race_quality_score(first) else first

    merged = deepcopy(card)
    merged["status"] = "finished"
    merged["start"] = result.get("start") or merged.get("start")
    merged["title"] = result.get("title") or merged.get("title")
    merged["officialNote"] = f"{_clean_text(merged.get('officialNote'))} / 結果は{_clean_text(result.get('source')) or '別ソース'}で照合済み".strip(" /")
    merged["source"] = " + ".join(
        dict.fromkeys(
            source
            for source in [str(merged.get("source") or ""), str(result.get("source") or "")]
            if source
        )
    ) or merged.get("source")
    merged["sourceUrl"] = result.get("sourceUrl") or merged.get("sourceUrl")
    merged["sourceCheckedAt"] = max(str(merged.get("sourceCheckedAt") or ""), str(result.get("sourceCheckedAt") or ""))
    result_payouts = result.get("payouts") if isinstance(result.get("payouts"), list) else []
    if result_payouts:
        merged["payouts"] = result_payouts

    finish_tags = _runner_finish_tags(result)
    payout_by_number = {
        _int_value(runner, "number", 0): runner
        for runner in (result.get("runners") if isinstance(result.get("runners"), list) else [])
        if isinstance(runner, dict)
    }
    for runner in merged.get("runners", []):
        if not isinstance(runner, dict):
            continue
        number = _int_value(runner, "number", 0)
        tags = [tag for tag in (runner.get("tags") if isinstance(runner.get("tags"), list) else []) if not (isinstance(tag, str) and tag.endswith("着"))]
        tags.extend(finish_tags.get(number, []))
        runner["tags"] = tags
        result_runner = payout_by_number.get(number)
        if result_runner:
            for key in [
                "payoutWin",
                "payoutPlace",
                "payoutQuinella",
                "payoutWide",
                "payoutExacta",
                "payoutTrio",
                "payoutTrifecta",
            ]:
                if result_runner.get(key):
                    runner[key] = result_runner[key]
    return merged


def _repair_race_start_time(race: dict[str, Any]) -> dict[str, Any]:
    start = str(race.get("start") or "")
    if re.search(r"\d{1,2}:\d{2}", start):
        return race

    race_no = _int_value({"race_no": str(race.get("raceNo") or "").replace("R", "")}, "race_no", 0)
    market = str(race.get("market") or "")
    if market not in {"JRA", "NAR"}:
        market = "JRA" if str(race.get("venue") or "") in JRA_VENUES else "NAR"
    estimated = _estimated_start_time(race_no, market)
    if estimated:
        race = deepcopy(race)
        race["start"] = f"推定 {estimated}"
    return race


def _collapse_duplicate_races(races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: dict[tuple[str, str, int], dict[str, Any]] = {}
    for race in races:
        race = _sanitize_race_payload(_repair_race_start_time(race))
        key = _race_display_key(race)
        if key[2] == 999:
            key = (key[0], key[1], hash(str(race.get("id") or "")))
        current = collapsed.get(key)
        if current is None:
            collapsed[key] = race
        else:
            collapsed[key] = _merge_duplicate_race_payloads(current, race)
    return sorted((_apply_runner_integrity_status(race) for race in collapsed.values()), key=_sort_race_dict)


def _resolve_requested_window(
    start_date: str | None,
    end_date: str | None,
    paths: list[Path],
) -> tuple[date, date] | None:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is not None and end is not None:
        return start, end
    if paths:
        return _window_from_latest(paths)
    fallback_latest = date(2026, 5, 5)
    return fallback_latest - timedelta(days=15), fallback_latest + timedelta(days=16)


def get_races(start_date: str | None = None, end_date: str | None = None) -> list[Race]:
    """Return verified race cards built from normalized local history CSVs."""

    paths = _existing_history_paths()
    window = _resolve_requested_window(start_date, end_date, paths)
    if window is None:
        return []
    start, end = window

    raw_races: list[dict[str, Any]]
    if not paths:
        raw_races, _ = _load_public_window(start, end)
    else:
        raw_races, _ = _load_history_sources(paths, start, end)

    try:
        from .race_storage import fetch_race_cards

        stored_races = fetch_race_cards(start.isoformat(), end.isoformat())
    except Exception:
        stored_races = []

    normalized_races: list[Race] = []
    for race in _collapse_duplicate_races([*raw_races, *stored_races]):
        payload = deepcopy(race)
        if payload.get("verificationStatus") not in {"verified", "stale", "unverified"}:
            payload["verificationStatus"] = "verified"
        normalized_races.append(Race(**payload))
    return normalized_races


def get_snapshots() -> dict[str, LiveSnapshot]:
    """Return live snapshots derived from the same verified history source."""

    paths = _existing_history_paths()
    if not paths:
        start = date(2026, 4, 20)
        end = date(2026, 5, 20)
        _, raw_snapshots = _load_public_window(start, end)
        return {race_id: LiveSnapshot(**deepcopy(snapshot)) for race_id, snapshot in raw_snapshots.items()}
    window = _window_from_latest(paths)
    if window is None:
        return {}
    start, end = window
    _, raw_snapshots = _load_history_sources(paths, start, end)
    return {race_id: LiveSnapshot(**deepcopy(snapshot)) for race_id, snapshot in raw_snapshots.items()}
