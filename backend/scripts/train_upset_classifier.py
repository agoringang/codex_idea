from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


JRA_VENUES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}


def inferred_market(frame: pd.DataFrame) -> pd.Series:
    if "market" in frame:
        market = frame["market"].astype(str).str.upper()
        return market.where(market.isin(["JRA", "NAR"]), "NAR")
    venue = frame.get("venue", pd.Series("", index=frame.index)).astype(str)
    return pd.Series(np.where(venue.isin(JRA_VENUES), "JRA", "NAR"), index=frame.index)


def normalize_runner_number(frame: pd.DataFrame) -> pd.Series:
    if "runner_number" in frame:
        return pd.to_numeric(frame["runner_number"], errors="coerce")
    if "horse_number" in frame:
        return pd.to_numeric(frame["horse_number"], errors="coerce")
    if "number" in frame:
        return pd.to_numeric(frame["number"], errors="coerce")
    return pd.Series(np.nan, index=frame.index)


def scalar_float(value: Any, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return default if pd.isna(number) else float(number)


UPSET_USECOLS = {
    "race_id",
    "race_date",
    "venue",
    "distance",
    "going",
    "surface",
    "weather",
    "finish_position",
    "market_odds",
    "runner_number",
    "horse_number",
    "number",
    "market",
}


def load_source_csv(path: Path) -> pd.DataFrame:
    columns = pd.read_csv(path, nrows=0).columns.tolist()
    usecols = [column for column in columns if column in UPSET_USECOLS]
    return pd.read_csv(path, usecols=usecols, low_memory=False)


def race_level_frame(source: pd.DataFrame) -> pd.DataFrame:
    frame = source.copy()
    frame["race_date"] = pd.to_datetime(frame["race_date"], errors="coerce")
    frame["finish_position"] = pd.to_numeric(frame["finish_position"], errors="coerce")
    frame["market_odds"] = pd.to_numeric(frame.get("market_odds"), errors="coerce")
    frame["runner_number"] = normalize_runner_number(frame)
    frame["market"] = inferred_market(frame)
    frame = frame.dropna(subset=["race_id", "race_date", "finish_position", "market_odds"]).copy()
    frame = frame[frame["market_odds"] > 1.0].copy()
    frame["odds_rank"] = frame.groupby("race_id")["market_odds"].rank(method="first", ascending=True)
    inv_odds = 1 / frame["market_odds"].clip(lower=1.01)
    prob_sum = inv_odds.groupby(frame["race_id"]).transform("sum").replace(0, np.nan)
    normalized_probs = (inv_odds / prob_sum).clip(lower=1e-9)
    frame["entropy_part"] = -(normalized_probs * np.log(normalized_probs))

    base_columns = ["race_date", "market", "venue", "surface", "going", "weather", "distance"]
    for column in base_columns:
        if column not in frame:
            frame[column] = ""
    base = frame.groupby("race_id", sort=False).agg(
        race_date=("race_date", "first"),
        market=("market", "first"),
        venue=("venue", "first"),
        surface=("surface", "first"),
        going=("going", "first"),
        weather=("weather", "first"),
        distance=("distance", "first"),
        field_size=("runner_number", "count"),
        favorite_odds=("market_odds", "min"),
        odds_entropy=("entropy_part", "sum"),
        odds_std=("market_odds", "std"),
        longshot_count=("market_odds", lambda values: int((values >= 20).sum())),
        mid_odds_count=("market_odds", lambda values: int(((values >= 8) & (values < 20)).sum())),
    )
    sorted_odds = frame.sort_values(["race_id", "market_odds"]).groupby("race_id")["market_odds"]
    second = sorted_odds.nth(1).rename("second_favorite_odds")
    base = base.join(second)
    base["second_favorite_odds"] = base["second_favorite_odds"].fillna(base["favorite_odds"])
    base["favorite_gap"] = base["second_favorite_odds"] - base["favorite_odds"]
    base["odds_std"] = base["odds_std"].fillna(0)
    base["distance"] = pd.to_numeric(base["distance"], errors="coerce").fillna(0)

    winner = frame[frame["finish_position"] == 1].groupby("race_id", sort=False).agg(
        winner_odds_rank=("odds_rank", "first"),
        winner_odds=("market_odds", "first"),
    )
    top3 = frame[frame["finish_position"] <= 3].groupby("race_id", sort=False).agg(
        top3_max_odds_rank=("odds_rank", "max"),
        top3_avg_odds=("market_odds", "mean"),
    )
    races = base.join(winner).join(top3).dropna(subset=["winner_odds_rank", "top3_max_odds_rank"])
    races["upset"] = (
        (races["winner_odds_rank"] >= 4)
        | (races["top3_max_odds_rank"] >= 7)
        | (races["winner_odds"] >= 10)
        | (races["top3_avg_odds"] >= 12)
    ).astype("int8")
    return races.reset_index()


def build_hgb(numeric: list[str]) -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.06,
                    max_iter=120,
                    max_leaf_nodes=31,
                    l2_regularization=0.02,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


def score(y_true: pd.Series, probability: np.ndarray) -> dict[str, Any]:
    probability = np.clip(probability.astype(float), 1e-6, 1 - 1e-6)
    return {
        "rows": int(len(y_true)),
        "positive_rate": float(y_true.mean()),
        "brier": float(brier_score_loss(y_true, probability)),
        "auc": float(roc_auc_score(y_true, probability)) if y_true.nunique() > 1 else None,
        "log_loss": float(log_loss(y_true, probability, labels=[0, 1])),
        "alert_rate_at_0_60": float((probability >= 0.60).mean()),
        "actual_rate_at_0_60": float(y_true[probability >= 0.60].mean()) if (probability >= 0.60).any() else None,
    }


def train_segment(frame: pd.DataFrame, market: str, train_end_date: str, holdout_start_date: str) -> dict[str, Any]:
    segment = frame if market == "ALL" else frame[frame["market"] == market]
    train = segment[segment["race_date"] <= pd.Timestamp(train_end_date)]
    holdout = segment[segment["race_date"] >= pd.Timestamp(holdout_start_date)]
    if train.empty or holdout.empty or train["upset"].nunique() < 2:
        return {"market": market, "status": "skipped", "train_races": int(len(train)), "holdout_races": int(len(holdout))}

    numeric = [
        "distance",
        "field_size",
        "favorite_odds",
        "second_favorite_odds",
        "favorite_gap",
        "odds_entropy",
        "odds_std",
        "longshot_count",
        "mid_odds_count",
    ]
    y_train = train["upset"].astype(int)
    y_holdout = holdout["upset"].astype(int)
    constant = np.full(len(holdout), float(y_train.mean()))
    heuristic = np.clip(
        0.22
        + holdout["odds_entropy"].rank(pct=True).to_numpy() * 0.35
        + holdout["favorite_odds"].rank(pct=True).to_numpy() * 0.25
        + holdout["field_size"].rank(pct=True).to_numpy() * 0.18,
        0.01,
        0.99,
    )
    candidates = {
        "hgb_numeric_race_features": (build_hgb(numeric), numeric),
    }
    metrics: dict[str, Any] = {
        "constant_train_rate": score(y_holdout, constant),
        "market_shape_heuristic": score(y_holdout, heuristic),
    }
    models: dict[str, Pipeline] = {}
    for name, (model, features) in candidates.items():
        model.fit(train[features], y_train)
        probability = model.predict_proba(holdout[features])[:, 1]
        metrics[name] = score(y_holdout, probability)
        models[name] = model
    best_name = min(
        candidates,
        key=lambda name: (
            metrics[name]["brier"],
            -(metrics[name]["auc"] or 0),
        ),
    )
    return {
        "market": market,
        "status": "ok",
        "train_races": int(len(train)),
        "holdout_races": int(len(holdout)),
        "features": {"numeric": numeric, "categorical": []},
        "metrics": metrics,
        "best_model": best_name,
        "model": models[best_name],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a separate race-level upset classifier.")
    parser.add_argument("--train-csv", type=Path, default=Path("data/keiba_history_normalized.csv"))
    parser.add_argument("--holdout-csv", type=Path, default=Path("data/netkeiba_2026_enriched.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("models/upset_classifier"))
    parser.add_argument("--train-end-date", default="2025-12-31")
    parser.add_argument("--holdout-start-date", default="2026-01-01")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = pd.concat([load_source_csv(args.train_csv), load_source_csv(args.holdout_csv)], ignore_index=True, sort=False)
    races = race_level_frame(source)
    payload: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_csv": str(args.train_csv),
        "holdout_csv": str(args.holdout_csv),
        "definition": "upset=winner odds rank >=4, top3 contains rank >=7, winner odds >=10, or top3 average odds >=12",
        "segments": {},
    }
    artifact: dict[str, Any] = {"segments": {}, "metrics": payload}
    for market in ("ALL", "JRA", "NAR"):
        result = train_segment(races, market, args.train_end_date, args.holdout_start_date)
        model = result.pop("model", None)
        payload["segments"][market] = result
        if model is not None:
            artifact["segments"][market] = {"model": model, "metrics": result}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output_dir / "upset_classifier_metrics.json"
    artifact_path = args.output_dir / "upset_classifier.joblib"
    payload["metrics_path"] = str(metrics_path)
    payload["artifact_path"] = str(artifact_path)
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    joblib.dump(artifact, artifact_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
