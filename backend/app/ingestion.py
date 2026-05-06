from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .data_sources import build_race_dicts_from_rows
from .history import get_all_history, record_prediction
from .model import predict_race
from .race_storage import race_storage_available, record_ingest_run, upsert_race_cards
from .schemas import RaceRequest, RunnerInput


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_PATH = BACKEND_ROOT / "scripts" / "scrape_netkeiba_2026.py"
JST = timezone(timedelta(hours=9))


def _load_scraper_module() -> Any:
    module_name = "umalab_netkeiba_scraper"
    spec = importlib.util.spec_from_file_location(module_name, SCRAPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scraper module: {SCRAPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _date_range_for_days(days: int) -> tuple[str, str]:
    end = datetime.now(JST).date()
    start = end - timedelta(days=max(days - 1, 0))
    return start.isoformat(), end.isoformat()


def _safe_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _race_request_from_dict(race: dict[str, Any]) -> RaceRequest:
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    odds_rank = {
        id(item): index + 1
        for index, item in enumerate(
            sorted(runners, key=lambda item: _safe_float(item.get("odds") if isinstance(item, dict) else None, 999.0))
        )
        if isinstance(item, dict)
    }
    course = str(race.get("course") or "")
    distance_match = re.search(r"(\d+(?:\.\d+)?)m", course)
    distance = int(float(distance_match.group(1))) if distance_match else None
    surface = "ダ" if "ダ" in course else "芝" if "芝" in course else None
    going = next((label for label in ("不良", "稍重", "重", "良") if label in course), None)

    runner_inputs: list[RunnerInput] = []
    for index, runner in enumerate(runners, start=1):
        if not isinstance(runner, dict):
            continue
        number = _safe_int(runner.get("number"), index)
        odds = max(_safe_float(runner.get("odds"), 1.1), 1.1)
        rating = max(1.0, min(100.0, _safe_float(runner.get("rating"), 60.0)))
        runner_inputs.append(
            RunnerInput(
                id=f"{race.get('id')}-{number}",
                gate=max(1, min(8, _safe_int(runner.get("gate"), (number + 1) // 2))),
                number=number,
                name=str(runner.get("name") or f"{number}番"),
                market_odds=odds,
                place_odds=max(1.1, odds * 0.32),
                speed=rating,
                stamina=rating,
                pace=rating,
                condition=rating,
                base_win=max(0.001, min(0.8, 1 / odds)),
                carried_weight=runner.get("carriedWeight"),
                horse_weight=runner.get("horseWeight"),
                horse_weight_diff=runner.get("horseWeightDiff"),
                age=runner.get("age"),
                sex=runner.get("sex"),
                venue=race.get("venue"),
                surface=surface,
                going=going,
                jockey=runner.get("jockey"),
                trainer=runner.get("trainer"),
                running_style=runner.get("runningStyle"),
                sire=runner.get("sire"),
                dam_sire=runner.get("damSire"),
                odds_rank=odds_rank.get(id(runner)),
            )
        )

    return RaceRequest(
        race_id=str(race.get("id") or ""),
        race_date=str(race.get("date") or date.today().isoformat()),
        venue=race.get("venue"),
        title=race.get("title"),
        race_no=race.get("raceNo"),
        course=race.get("course"),
        market=race.get("market") if race.get("market") in {"JRA", "NAR"} else None,
        model_version="racequant-active",
        model_mode="ensemble",
        risk_level=52,
        bankroll=100_000,
        min_edge=0.06,
        min_probability=0.05,
        max_candidate_odds=45,
        max_edge=1.1,
        max_exposure=0.022,
        runners=runner_inputs,
    )


def _record_prediction_for_race(race: dict[str, Any], *, generated_after_result: bool = False) -> bool:
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    if len(runners) < 2:
        return False
    try:
        request = _race_request_from_dict(race)
        prediction = predict_race(request)
        record_prediction(
            request.race_id,
            request.race_date or date.today().isoformat(),
            prediction=prediction.model_dump(mode="json"),
            metadata={
                "race_date": request.race_date,
                "venue": request.venue,
                "title": request.title,
                "race_no": request.race_no,
                "course": request.course,
                "market": request.market,
                "risk_level": request.risk_level,
                "bankroll": request.bankroll,
                "model_mode": request.model_mode,
                "model_version": request.model_version,
                "auto_generated": True,
                "official_prediction": not generated_after_result,
                "generated_after_result": generated_after_result,
                "prediction_kind": "post_result_simulation" if generated_after_result else "pre_race_auto",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        return False
    return True


def _auto_predict_open_races(races: list[dict[str, Any]]) -> int:
    count = 0
    for race in races:
        if str(race.get("status") or "") == "finished":
            continue
        if _record_prediction_for_race(race):
            count += 1
    return count


def _existing_prediction_ids(start_date: str, end_date: str) -> set[str]:
    existing: set[str] = set()
    try:
        history = get_all_history(start_date, end_date)
    except Exception:
        return existing
    for entries in history.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            prediction = entry.get("prediction")
            race_id = str(entry.get("race_id") or "")
            if race_id and isinstance(prediction, dict) and prediction:
                existing.add(race_id)
    return existing


def _auto_predict_missing_finished_races(races: list[dict[str, Any]], start_date: str, end_date: str) -> int:
    existing = _existing_prediction_ids(start_date, end_date)
    count = 0
    for race in races:
        race_id = str(race.get("id") or "")
        if not race_id or race_id in existing:
            continue
        if str(race.get("status") or "") != "finished":
            continue
        if _record_prediction_for_race(race, generated_after_result=True):
            existing.add(race_id)
            count += 1
    return count


def ingest_netkeiba_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 2,
    max_requests: int | None = None,
    delay: float | None = None,
    refresh: bool = False,
    prefer_results: bool = False,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    if not start_date or not end_date:
        start_date, end_date = _date_range_for_days(days)

    raw_dir = Path(os.getenv("NETKEIBA_RAW_DIR", "/tmp/umalab_netkeiba_raw")) / f"{start_date}_{end_date}"
    output = Path(os.getenv("NETKEIBA_INGEST_OUTPUT", "/tmp/umalab_netkeiba_normalized.csv"))
    raw_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    scraper = _load_scraper_module()
    args = argparse.Namespace(
        start_date=start_date,
        end_date=end_date,
        race_id=[],
        race_ids_file=None,
        raw_dir=raw_dir,
        output=output,
        base_csv=None,
        combined_output=None,
        encoding="utf-8-sig",
        delay=delay if delay is not None else float(os.getenv("NETKEIBA_INGEST_DELAY", "1.5")),
        timeout=float(os.getenv("NETKEIBA_INGEST_TIMEOUT", "20")),
        retries=int(os.getenv("NETKEIBA_INGEST_RETRIES", "1")),
        max_requests=max_requests if max_requests is not None else int(os.getenv("NETKEIBA_INGEST_MAX_REQUESTS", "120")),
        refresh=refresh,
        prefer_results=prefer_results,
        no_calendar=False,
        list_only=False,
        skip_import=False,
        user_agent=os.getenv(
            "NETKEIBA_USER_AGENT",
            "UmaLabResearch/0.2 (public pages only; rate-limited; contact: local-user)",
        ),
    )

    fetcher = scraper.RateLimitedFetcher(
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        max_requests=args.max_requests,
        refresh=args.refresh,
        user_agent=args.user_agent,
    )

    calendar_ids: list[str] = []
    race_results: list[dict[str, Any]] = []
    stop_reason = ""
    try:
        calendar_ids, _calendar_results = scraper.scrape_calendar_pages(args, fetcher)
        race_ids = sorted(set(calendar_ids))
        race_results = scraper.scrape_race_pages(race_ids, args, fetcher)
    except scraper.MaxRequestsReached as exc:
        race_ids = sorted(set(calendar_ids))
        stop_reason = str(exc)
    except SystemExit as exc:
        race_ids = sorted(set(calendar_ids))
        stop_reason = str(exc)

    import_summary = scraper.import_downloaded_html(args)
    rows = _read_rows(output)
    rows = [
        row
        for row in rows
        if start_date <= str(row.get("race_date") or "") <= end_date
    ]
    race_dicts, _snapshots = build_race_dicts_from_rows(
        rows,
        source_name="netkeiba live scrape",
        source_checked_at=datetime.now(timezone.utc).isoformat(),
    )
    races_stored = upsert_race_cards(race_dicts)
    open_predictions = _auto_predict_open_races(race_dicts) if races_stored > 0 else 0
    backfilled_predictions = (
        _auto_predict_missing_finished_races(race_dicts, start_date, end_date)
        if prefer_results and races_stored > 0
        else 0
    )
    auto_predictions = open_predictions + backfilled_predictions

    status = "ok"
    if stop_reason:
        status = "partial"
    if not race_dicts:
        status = "skipped"
    if race_dicts and races_stored == 0 and not race_storage_available():
        status = "error"
        stop_reason = "Supabase is not configured, so scraped races were not persisted"

    summary = {
        "status": status,
        "source": "netkeiba",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "request_count": fetcher.request_count,
        "race_ids": len(race_ids),
        "race_pages": len(race_results),
        "rows_found": int(import_summary.get("rows") or len(rows)),
        "races_found": len(race_dicts),
        "races_stored": races_stored,
        "auto_predictions": auto_predictions,
        "backfilled_predictions": backfilled_predictions,
        "raw_dir": str(raw_dir),
        "output": str(output),
        "message": stop_reason
        or (
            f"{len(race_dicts)} races imported, "
            f"{open_predictions} open-race predictions saved, "
            f"{backfilled_predictions} finished-race simulations backfilled"
        ),
    }
    record_ingest_run(summary)
    return summary


def import_netkeiba_race_cards(
    race_cards: list[dict[str, Any]],
    *,
    source: str = "netkeiba_local_import",
    auto_predict: bool = True,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    races = [race for race in race_cards if isinstance(race, dict)]
    dates = sorted({str(race.get("date") or "") for race in races if race.get("date")})
    start_date = dates[0] if dates else ""
    end_date = dates[-1] if dates else ""

    races_stored = upsert_race_cards(races)
    auto_predictions = _auto_predict_open_races(races) if auto_predict and races_stored > 0 else 0

    status = "ok"
    message = f"{len(races)} races imported, {auto_predictions} open-race predictions saved"
    if not races:
        status = "skipped"
        message = "no race cards supplied"
    if races and races_stored == 0 and not race_storage_available():
        status = "error"
        message = "Supabase is not configured, so supplied races were not persisted"

    summary = {
        "status": status,
        "source": source,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "request_count": 0,
        "race_ids": len(races),
        "race_pages": len(races),
        "rows_found": sum(len(race.get("runners") or []) for race in races),
        "races_found": len(races),
        "races_stored": races_stored,
        "auto_predictions": auto_predictions,
        "backfilled_predictions": 0,
        "raw_dir": "",
        "output": "",
        "message": message,
    }
    record_ingest_run(summary)
    return summary


def parse_date_window(start_date: str | None, end_date: str | None, days: int) -> tuple[str, str]:
    if start_date and end_date:
        return start_date, end_date
    return _date_range_for_days(days)
