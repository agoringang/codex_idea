from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


TARGET_MARKET_MULTIPLIER = {
    "is_win": 1.0,
    "is_top2": 2.0,
    "is_place": 3.0,
}


def market_probability(frame: pd.DataFrame, target: str) -> np.ndarray:
    odds = pd.to_numeric(frame.get("market_odds"), errors="coerce").replace(0, np.nan)
    implied = (1 / odds).replace([np.inf, -np.inf], np.nan)
    race_total = implied.groupby(frame["race_id"]).transform("sum").replace(0, np.nan)
    win_probability = (implied / race_total).fillna(0).to_numpy(dtype=float)
    multiplier = TARGET_MARKET_MULTIPLIER.get(target, 1.0)
    if target == "is_win":
        return np.clip(win_probability, 1e-6, 0.95)
    field_size = pd.to_numeric(frame.get("field_size"), errors="coerce").fillna(
        frame.groupby("race_id")["race_id"].transform("size")
    )
    values = win_probability * np.minimum(field_size.to_numpy(dtype=float), multiplier)
    return np.clip(values, 1e-6, 0.95)


class CalibratedBlendModel:
    def __init__(
        self,
        *,
        base_model: Pipeline,
        calibrator: LogisticRegression | None,
        target: str,
        features: list[str],
        market_weight: float,
        fallback_rate: float,
    ) -> None:
        self.base_model = base_model
        self.calibrator = calibrator
        self.target = target
        self.features = features
        self.market_weight = market_weight
        self.fallback_rate = fallback_rate

    def predict_positive(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.base_model.predict_proba(frame[self.features])[:, 1]
        raw = np.clip(raw.astype(float), 1e-6, 1 - 1e-6)
        if self.calibrator is not None:
            logits = np.log(raw / (1 - raw)).reshape(-1, 1)
            probabilities = self.calibrator.predict_proba(logits)[:, 1]
        else:
            probabilities = raw
        if not np.isfinite(probabilities).all():
            probabilities = np.full(len(frame), self.fallback_rate, dtype=float)
        probabilities = np.clip(probabilities.astype(float), 1e-6, 1 - 1e-6)
        if self.market_weight > 0:
            market = market_probability(frame, self.target)
            probabilities = (1 - self.market_weight) * probabilities + self.market_weight * market
        return np.clip(probabilities.astype(float), 1e-6, 1 - 1e-6)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        positive = self.predict_positive(frame)
        return np.column_stack([1 - positive, positive])

    def __getstate__(self) -> dict[str, Any]:
        return self.__dict__.copy()

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
