from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES


FEATURES = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]


def build_pipeline(seed: int) -> Pipeline:
    numeric = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=8, sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ]
    )

    model = HistGradientBoostingClassifier(
        learning_rate=0.035,
        max_iter=260,
        max_leaf_nodes=31,
        min_samples_leaf=24,
        l2_regularization=0.10,
        random_state=seed,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def prepare_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "race_id" not in frame:
        raise ValueError("missing required column: race_id")
    if "is_win" not in frame:
        if "finish_position" not in frame:
            raise ValueError("missing required target: is_win or finish_position")
        frame["is_win"] = (frame["finish_position"] == 1).astype(int)
    if "is_place" not in frame:
        if "finish_position" not in frame:
            raise ValueError("missing required target: is_place or finish_position")
        frame["is_place"] = (frame["finish_position"] <= 3).astype(int)

    for column in NUMERIC_FEATURES:
        if column not in frame:
            frame[column] = pd.NA
    for column in CATEGORICAL_FEATURES:
        if column not in frame:
            frame[column] = "unknown"

    if "race_date" in frame:
        frame = frame.sort_values(["race_date", "race_id", "number" if "number" in frame else "is_win"])
    else:
        frame = frame.sort_values(["race_id", "number" if "number" in frame else "is_win"])

    return frame.reset_index(drop=True)


def race_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if "race_date" in frame:
        races = frame[["race_id", "race_date"]].drop_duplicates().sort_values(["race_date", "race_id"])
    else:
        races = frame[["race_id"]].drop_duplicates()

    race_ids = races["race_id"].tolist()
    if len(race_ids) < 10:
        raise ValueError("need at least 10 races for grouped time split")

    train_cut = max(1, int(len(race_ids) * 0.70))
    valid_cut = max(train_cut + 1, int(len(race_ids) * 0.85))
    train_ids = set(race_ids[:train_cut])
    valid_ids = set(race_ids[train_cut:valid_cut])
    test_ids = set(race_ids[valid_cut:])

    return (
        frame[frame["race_id"].isin(train_ids)].copy(),
        frame[frame["race_id"].isin(valid_ids)].copy(),
        frame[frame["race_id"].isin(test_ids)].copy(),
    )


def binary_metrics(model: Pipeline, frame: pd.DataFrame, target: str) -> dict[str, Any]:
    y_true = frame[target].astype(int)
    probabilities = model.predict_proba(frame[FEATURES])[:, 1]
    metrics: dict[str, Any] = {
        "rows": int(len(frame)),
        "positive_rate": float(y_true.mean()),
        "brier": float(brier_score_loss(y_true, probabilities)),
    }
    labels = set(y_true.tolist())
    if len(labels) == 2:
        metrics["auc"] = float(roc_auc_score(y_true, probabilities))
        metrics["log_loss"] = float(log_loss(y_true, probabilities, labels=[0, 1]))
    else:
        metrics["auc"] = None
        metrics["log_loss"] = None
    return metrics


def train_target(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame, target: str, seed: int) -> tuple[Pipeline, dict[str, Any]]:
    if train[target].nunique() < 2:
        raise ValueError(f"target {target} has only one class in train split")

    pipeline = build_pipeline(seed)
    pipeline.fit(train[FEATURES], train[target].astype(int))
    return pipeline, {
        "train": binary_metrics(pipeline, train, target),
        "valid": binary_metrics(pipeline, valid, target),
        "test": binary_metrics(pipeline, test, target),
    }


def feature_presence(frame: pd.DataFrame) -> dict[str, float]:
    return {column: float(frame[column].notna().mean()) for column in FEATURES}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("models/racequant"), type=Path)
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()

    frame = prepare_frame(args.csv)
    train, valid, test = race_split(frame)

    models: dict[str, Pipeline] = {}
    metrics: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(args.csv),
        "rows": int(len(frame)),
        "races": int(frame["race_id"].nunique()),
        "splits": {
            "train_rows": int(len(train)),
            "valid_rows": int(len(valid)),
            "test_rows": int(len(test)),
            "train_races": int(train["race_id"].nunique()),
            "valid_races": int(valid["race_id"].nunique()),
            "test_races": int(test["race_id"].nunique()),
        },
        "targets": {},
        "feature_presence": feature_presence(frame),
    }

    for target in ["is_win", "is_place"]:
        model, target_metrics = train_target(train, valid, test, target, args.seed)
        models[target.removeprefix("is_")] = model
        metrics["targets"][target] = target_metrics

    artifact = {
        "models": models,
        "metrics": metrics,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "model.joblib"
    latest_path = args.output_dir / "latest.joblib"
    metrics_path = args.output_dir / "metrics.json"
    joblib.dump(artifact, model_path)
    shutil.copyfile(model_path, latest_path)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
