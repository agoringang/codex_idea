from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen


RACE_CARD_TABLE = os.getenv("SUPABASE_RACE_CARD_TABLE", "race_cards")
INGEST_RUN_TABLE = os.getenv("SUPABASE_RACE_INGEST_TABLE", "race_ingest_runs")


def _supabase_config() -> tuple[str, str] | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    return url.rstrip("/"), key


def _supabase_request(
    path: str,
    *,
    method: str = "GET",
    body: Any | None = None,
    prefer: str | None = None,
) -> Any:
    config = _supabase_config()
    if config is None:
        raise RuntimeError("Supabase is not configured")

    base_url, key = config
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(f"{base_url}/rest/v1/{path}", data=data, headers=headers, method=method)
    with urlopen(request, timeout=45) as response:  # noqa: S310 - configured Supabase URL
        payload = response.read().decode("utf-8")
    return json.loads(payload) if payload else None


def race_storage_available() -> bool:
    return _supabase_config() is not None


def fetch_race_cards(start_date: str, end_date: str) -> list[dict[str, Any]]:
    if _supabase_config() is None:
        return []

    # Keep the repeated race_date filter explicit for PostgREST.
    query = (
        "select=payload"
        f"&race_date=gte.{start_date}"
        f"&race_date=lte.{end_date}"
        "&order=race_date.asc,venue.asc,race_no.asc"
    )
    rows = _supabase_request(f"{RACE_CARD_TABLE}?{query}") or []
    races = [row.get("payload") for row in rows if isinstance(row, dict)]
    return [race for race in races if isinstance(race, dict)]


def upsert_race_cards(races: list[dict[str, Any]]) -> int:
    if _supabase_config() is None:
        return 0
    if not races:
        return 0

    rows: list[dict[str, Any]] = []
    for race in races:
        race_id = str(race.get("id") or "").strip()
        race_date = str(race.get("date") or "").strip()
        if not race_id or not race_date:
            continue
        race_no_text = str(race.get("raceNo") or "0").replace("R", "")
        try:
            race_no = int(float(race_no_text))
        except ValueError:
            race_no = 0
        rows.append(
            {
                "race_id": race_id,
                "race_date": race_date,
                "venue": str(race.get("venue") or ""),
                "race_no": race_no,
                "status": str(race.get("status") or ""),
                "market": str(race.get("market") or ""),
                "source_url": race.get("sourceUrl"),
                "source_checked_at": race.get("sourceCheckedAt"),
                "payload": race,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    for index in range(0, len(rows), 100):
        _supabase_request(
            f"{RACE_CARD_TABLE}?on_conflict=race_id",
            method="POST",
            body=rows[index : index + 100],
            prefer="resolution=merge-duplicates,return=minimal",
        )
    return len(rows)


def record_ingest_run(summary: dict[str, Any]) -> None:
    if _supabase_config() is None:
        return
    row = {
        "started_at": summary.get("started_at"),
        "finished_at": summary.get("finished_at") or datetime.now(timezone.utc).isoformat(),
        "source": summary.get("source") or "netkeiba",
        "start_date": summary.get("start_date"),
        "end_date": summary.get("end_date"),
        "races_found": summary.get("races_found") or 0,
        "races_stored": summary.get("races_stored") or 0,
        "rows_found": summary.get("rows_found") or 0,
        "status": summary.get("status") or "unknown",
        "message": summary.get("message"),
        "payload": summary,
    }
    try:
        _supabase_request(INGEST_RUN_TABLE, method="POST", body=row, prefer="return=minimal")
    except Exception:
        return
