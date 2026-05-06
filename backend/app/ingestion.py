from __future__ import annotations

import argparse
import csv
import importlib.util
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .data_sources import build_race_dicts_from_rows
from .race_storage import race_storage_available, record_ingest_run, upsert_race_cards


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_PATH = BACKEND_ROOT / "scripts" / "scrape_netkeiba_2026.py"


def _load_scraper_module() -> Any:
    spec = importlib.util.spec_from_file_location("umalab_netkeiba_scraper", SCRAPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scraper module: {SCRAPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _date_range_for_days(days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=max(days - 1, 0))
    return start.isoformat(), end.isoformat()


def ingest_netkeiba_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 2,
    max_requests: int | None = None,
    delay: float | None = None,
    refresh: bool = False,
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
        "raw_dir": str(raw_dir),
        "output": str(output),
        "message": stop_reason or f"{len(race_dicts)} races imported",
    }
    record_ingest_run(summary)
    return summary


def parse_date_window(start_date: str | None, end_date: str | None, days: int) -> tuple[str, str]:
    if start_date and end_date:
        return start_date, end_date
    return _date_range_for_days(days)
