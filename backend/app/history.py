from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


if os.getenv("UMALAB_HISTORY_PATH"):
    STORAGE = Path(os.environ["UMALAB_HISTORY_PATH"])
elif os.getenv("VERCEL"):
    STORAGE = Path("/tmp/umalab_predictions_history.json")
else:
    STORAGE = Path(__file__).resolve().parents[1] / "data" / "predictions_history.json"

SUPABASE_TABLE = "prediction_history"


def _supabase_config() -> tuple[str, str] | None:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    return url, key


def _supabase_request(
    query: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    prefer: str | None = None,
) -> Any:
    config = _supabase_config()
    if config is None:
        raise RuntimeError("Supabase is not configured")

    url, key = config
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    request = Request(
        f"{url}/rest/v1/{query}",
        data=data,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=8) as response:
        text = response.read().decode("utf-8")
    return json.loads(text) if text else None


def _history_entry(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    entry: dict[str, Any] = {
        "race_id": row.get("race_id"),
        "prediction": row.get("prediction") or {},
        "result": row.get("result") or {},
    }
    entry.update(metadata)
    return entry


def _supabase_record_prediction(
    race_id: str,
    date: str,
    prediction: Dict[str, Any] | None,
    result: Dict[str, Any] | None,
) -> bool:
    if _supabase_config() is None:
        return False
    body = {
        "race_id": race_id,
        "race_date": date,
        "prediction": prediction or {},
        "result": result or {},
    }
    try:
        _supabase_request(
            f"{SUPABASE_TABLE}?on_conflict=race_id,race_date",
            method="POST",
            body=body,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return True
    except (RuntimeError, TimeoutError, URLError, OSError, ValueError):
        return False


def _supabase_history_for_date(date: str) -> List[Dict[str, Any]] | None:
    if _supabase_config() is None:
        return None
    query = urlencode(
        {
            "race_date": f"eq.{date}",
            "select": "race_id,race_date,prediction,result,metadata,created_at",
            "order": "created_at.desc",
        },
        safe=".,",
    )
    try:
        rows = _supabase_request(f"{SUPABASE_TABLE}?{query}")
    except (RuntimeError, TimeoutError, URLError, OSError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    return [_history_entry(row) for row in rows if isinstance(row, dict)]


def _supabase_all_history() -> Dict[str, List[Dict[str, Any]]] | None:
    if _supabase_config() is None:
        return None
    query = urlencode(
        {
            "select": "race_id,race_date,prediction,result,metadata,created_at",
            "order": "race_date.desc",
            "limit": "500",
        },
        safe=".,",
    )
    try:
        rows = _supabase_request(f"{SUPABASE_TABLE}?{query}")
    except (RuntimeError, TimeoutError, URLError, OSError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    history: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        race_date = str(row.get("race_date") or "")
        if not race_date:
            continue
        history.setdefault(race_date, []).append(_history_entry(row))
    return history


def _ensure_storage():
    STORAGE.parent.mkdir(parents=True, exist_ok=True)
    if not STORAGE.exists():
        STORAGE.write_text("{}", encoding="utf-8")


def record_prediction(
    race_id: str,
    date: str,
    prediction: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
) -> None:
    """Append or update a prediction record for a race.

    prediction/result are arbitrary dicts (will be stored as-is).
    """
    if _supabase_record_prediction(race_id, date, prediction, result):
        return

    _ensure_storage()
    data = json.loads(STORAGE.read_text(encoding="utf-8") or "{}")
    day = date
    day_entries: List[Dict[str, Any]] = data.get(day, [])
    # update existing entry if present
    for entry in day_entries:
        if entry.get("race_id") == race_id:
            if prediction is not None:
                entry["prediction"] = prediction
            if result is not None:
                entry["result"] = result
            STORAGE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return
    # otherwise append
    entry: Dict[str, Any] = {"race_id": race_id}
    if prediction is not None:
        entry["prediction"] = prediction
    if result is not None:
        entry["result"] = result
    day_entries.append(entry)
    data[day] = day_entries
    STORAGE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_history_for_date(date: str) -> List[Dict[str, Any]]:
    supabase_history = _supabase_history_for_date(date)
    if supabase_history is not None:
        return supabase_history

    _ensure_storage()
    data = json.loads(STORAGE.read_text(encoding="utf-8") or "{}")
    return data.get(date, [])


def get_all_history() -> Dict[str, List[Dict[str, Any]]]:
    supabase_history = _supabase_all_history()
    if supabase_history is not None:
        return supabase_history

    _ensure_storage()
    return json.loads(STORAGE.read_text(encoding="utf-8") or "{}")
