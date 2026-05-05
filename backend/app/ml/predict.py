from __future__ import annotations

import joblib
import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.schemas import RacePrediction, RaceRequest, RunnerPrediction


def _heuristic_score(row: dict) -> float:
    speed = float(row.get("speed") or 50)
    stamina = float(row.get("stamina") or 50)
    pace = float(row.get("pace") or 50)
    odds = row.get("market_odds")
    odds_signal = 50
    if odds:
        odds_signal = max(1, min(80, 100 / float(odds)))
    return 0.35 * speed + 0.25 * stamina + 0.15 * pace + 0.25 * odds_signal


def _probabilities_from_scores(scores: np.ndarray) -> np.ndarray:
    scores = scores.astype(float)
    scores = scores - scores.max()
    exp = np.exp(scores / 12.0)
    return exp / exp.sum()


def predict_race(request: RaceRequest) -> RacePrediction:
    settings = get_settings()
    df = pd.DataFrame([r.model_dump() for r in request.runners])
    model_path = settings.model_dir / "win_model" / "latest.joblib"

    model_version = "heuristic"
    if model_path.exists():
        try:
            artifact = joblib.load(model_path)
            pipeline = artifact["pipeline"]
            features = artifact["features"]
            for col in features:
                if col not in df.columns:
                    df[col] = np.nan
            raw = pipeline.predict_proba(df[features])[:, 1]
            probs = raw / raw.sum() if raw.sum() > 0 else _probabilities_from_scores(raw)
            model_version = str(model_path)
        except Exception:
            scores = np.array([_heuristic_score(row) for row in df.to_dict(orient="records")])
            probs = _probabilities_from_scores(scores)
            model_version = "heuristic_fallback"
    else:
        scores = np.array([_heuristic_score(row) for row in df.to_dict(orient="records")])
        probs = _probabilities_from_scores(scores)

    runners: list[RunnerPrediction] = []
    for row, p in zip(df.to_dict(orient="records"), probs):
        market_odds = row.get("market_odds")
        fair_odds = 1.0 / max(float(p), 1e-6)
        expected_value = None
        action = "watch"
        reason = "市場オッズがないため、勝率だけを確認する候補です。"
        if market_odds:
            expected_value = float(p) * float(market_odds) - 1.0
            if expected_value >= 0.10 and float(p) >= 0.06:
                action = "buy"
                reason = "推定勝率に対して市場オッズが高く、期待値がプラスです。"
            elif expected_value >= -0.05:
                action = "watch"
                reason = "期待値は境界付近です。直前オッズや馬体重更新待ちです。"
            else:
                action = "avoid"
                reason = "推定勝率に対して市場オッズが低く、見送り寄りです。"

        runners.append(
            RunnerPrediction(
                horse_name=str(row.get("horse_name")),
                number=None if pd.isna(row.get("number")) else int(row.get("number")),
                win_probability=round(float(p), 4),
                fair_odds=round(fair_odds, 2),
                market_odds=None if not market_odds else float(market_odds),
                expected_value=None if expected_value is None else round(expected_value, 4),
                action=action,
                reason=reason,
            )
        )

    runners.sort(key=lambda x: x.expected_value if x.expected_value is not None else x.win_probability, reverse=True)
    return RacePrediction(race_id=request.race_id, model_version=model_version, runners=runners)
