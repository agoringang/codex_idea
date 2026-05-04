from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

STORAGE = Path(__file__).resolve().parents[1] / "data" / "predictions_history.json"


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
    _ensure_storage()
    data = json.loads(STORAGE.read_text(encoding="utf-8") or "{}")
    return data.get(date, [])


def get_all_history() -> Dict[str, List[Dict[str, Any]]]:
    _ensure_storage()
    return json.loads(STORAGE.read_text(encoding="utf-8") or "{}")
