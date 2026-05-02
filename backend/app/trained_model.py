from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from .schemas import RunnerInput


DEFAULT_MODEL_PATH = Path("models/racequant/latest.joblib")


def configured_model_path() -> Path:
    return Path(os.environ.get("RACEQUANT_MODEL_PATH", DEFAULT_MODEL_PATH))


@lru_cache(maxsize=4)
def load_artifact(path_text: str) -> dict[str, Any] | None:
    path = Path(path_text)
    if not path.exists():
        return None
    return joblib.load(path)


def runner_frame(runners: list[RunnerInput]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for runner in runners:
        payload = runner.model_dump()
        rows.append({column: payload.get(column) for column in [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]})
    return pd.DataFrame(rows)


def predict_probabilities(runners: list[RunnerInput]) -> tuple[list[float], list[float]] | None:
    artifact = load_artifact(str(configured_model_path()))
    if artifact is None:
        return None

    models = artifact.get("models", {})
    win_model = models.get("win")
    place_model = models.get("place")
    if win_model is None:
        return None

    frame = runner_frame(runners)
    win_probabilities = win_model.predict_proba(frame)[:, 1].tolist()
    if place_model is None:
        place_probabilities = [min(max(probability * 2.4, 0.08), 0.82) for probability in win_probabilities]
    else:
        place_probabilities = place_model.predict_proba(frame)[:, 1].tolist()

    return win_probabilities, place_probabilities
