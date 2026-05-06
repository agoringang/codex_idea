from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from .ml_pipeline import load_artifact
from .schemas import RunnerInput


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = BACKEND_ROOT / "models/racequant/latest.joblib"
HOLDOUT_MODEL_PATH = BACKEND_ROOT / "models/racequant_holdout_2026/holdout_artifact.joblib"
MODEL_URL_ENV = "RACEQUANT_MODEL_URL"
MODEL_SHA_ENV = "RACEQUANT_MODEL_SHA256"
MODEL_CACHE_DIR_ENV = "RACEQUANT_MODEL_CACHE_DIR"


@dataclass
class RunnerProbabilities:
    win: list[float]
    place: list[float]
    top2: list[float] | None = None
    second: list[float] | None = None
    third: list[float] | None = None
    out: list[float] | None = None
    model_source: str = "none"


def _model_cache_dir() -> Path:
    configured = os.environ.get(MODEL_CACHE_DIR_ENV)
    if configured:
        return Path(configured)
    if os.environ.get("VERCEL"):
        return Path("/tmp/umalab-racequant-models")
    return BACKEND_ROOT / "runtime/models"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path_for_url(url: str) -> Path:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "racequant_model.joblib"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return _model_cache_dir() / f"{digest}-{filename}"


def _verify_model_checksum(path: Path) -> None:
    expected = os.environ.get(MODEL_SHA_ENV)
    if not expected:
        return
    actual = _sha256_file(path)
    if actual.lower() != expected.lower():
        raise ValueError(
            f"{MODEL_SHA_ENV} mismatch for {path}: expected {expected}, got {actual}"
        )


def _download_model(url: str) -> Path:
    cache_path = _cache_path_for_url(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists() and cache_path.stat().st_size > 0:
        _verify_model_checksum(cache_path)
        return cache_path

    tmp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    request = Request(url, headers={"User-Agent": "UmaLab/0.2 model-loader"})
    with urlopen(request, timeout=120) as response, tmp_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)

    _verify_model_checksum(tmp_path)
    tmp_path.replace(cache_path)
    return cache_path


def configured_model_path() -> Path:
    model_url = os.environ.get(MODEL_URL_ENV)
    if model_url:
        return _download_model(model_url)

    configured = os.environ.get("RACEQUANT_MODEL_PATH")
    if configured:
        return Path(configured)
    if HOLDOUT_MODEL_PATH.exists():
        return HOLDOUT_MODEL_PATH
    return DEFAULT_MODEL_PATH


def runner_frame(runners: list[RunnerInput]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for runner in runners:
        payload = runner.model_dump()
        payload["runner_number"] = runner.number
        payload["bracket"] = runner.gate
        payload["field_size"] = len(runners)
        rows.append(
            {column: payload.get(column) for column in [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]}
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["race_id"] = "inference"
    if not frame.empty and "market_odds" in frame:
        odds = pd.to_numeric(frame["market_odds"], errors="coerce").replace(0, np.nan)
        implied = (1 / odds).replace([np.inf, -np.inf], np.nan)
        total = float(implied.sum(skipna=True))
        win_probability = (implied / total).fillna(0) if total else pd.Series(0, index=frame.index)
        frame["market_win_probability"] = win_probability.astype("float32")
        frame["market_place_probability"] = (
            win_probability * min(len(frame), 3)
        ).clip(lower=1e-6, upper=0.95).astype("float32")
    return frame


def _positive_probability(model: Any, frame: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_positive"):
        return model.predict_positive(frame)
    return model.predict_proba(frame)[:, 1]


def _normalized_win(probabilities: np.ndarray) -> list[float]:
    clipped = np.clip(probabilities.astype(float), 1e-6, 1.0)
    total = float(clipped.sum())
    if total <= 0 or not np.isfinite(total):
        return (np.full(len(clipped), 1 / max(len(clipped), 1))).tolist()
    return (clipped / total).tolist()


def display_model_path(model_path: Path) -> str:
    if model_path.is_relative_to(BACKEND_ROOT):
        return str(model_path.relative_to(BACKEND_ROOT))
    return str(model_path)


@lru_cache(maxsize=2)
def _load_configured_artifact(model_path: str) -> dict[str, Any] | None:
    return load_artifact(model_path)


def predict_probabilities(runners: list[RunnerInput]) -> RunnerProbabilities | None:
    model_path = configured_model_path()
    try:
        artifact = _load_configured_artifact(str(model_path))
    except Exception:
        return None
    if artifact is None:
        return None

    models = artifact.get("models", {})
    win_model = models.get("is_win") or models.get("win")
    top2_model = models.get("is_top2")
    place_model = models.get("is_place") or models.get("place")
    if win_model is None:
        return None

    frame = runner_frame(runners)
    win_raw = _positive_probability(win_model, frame)
    win_probabilities = _normalized_win(win_raw)

    top2_probabilities: list[float] | None = None
    second_probabilities: list[float] | None = None
    third_probabilities: list[float] | None = None
    out_probabilities: list[float] | None = None
    if top2_model is not None:
        top2_raw = np.clip(_positive_probability(top2_model, frame), 1e-6, 1 - 1e-6)
        top2_raw = np.maximum(top2_raw, np.asarray(win_probabilities, dtype=float))
        top2_probabilities = np.clip(top2_raw, 1e-6, 1 - 1e-6).tolist()

    if place_model is None:
        place_probabilities = [
            min(max(probability * 2.4, 0.08), 0.82) for probability in win_probabilities
        ]
    else:
        place_raw = np.clip(_positive_probability(place_model, frame), 1e-6, 1 - 1e-6)
        if top2_probabilities is not None:
            place_raw = np.maximum(place_raw, np.asarray(top2_probabilities, dtype=float))
        place_probabilities = np.clip(place_raw, 1e-6, 1 - 1e-6).tolist()

    if top2_probabilities is not None:
        second = np.asarray(top2_probabilities, dtype=float) - np.asarray(
            win_probabilities,
            dtype=float,
        )
        third = np.asarray(place_probabilities, dtype=float) - np.asarray(
            top2_probabilities,
            dtype=float,
        )
        out = 1 - np.asarray(place_probabilities, dtype=float)
        second_probabilities = np.clip(second, 0, 1).tolist()
        third_probabilities = np.clip(third, 0, 1).tolist()
        out_probabilities = np.clip(out, 0, 1).tolist()

    return RunnerProbabilities(
        win=win_probabilities,
        top2=top2_probabilities,
        place=place_probabilities,
        second=second_probabilities,
        third=third_probabilities,
        out=out_probabilities,
        model_source=display_model_path(model_path),
    )
