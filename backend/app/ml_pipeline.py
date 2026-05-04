from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES


ALL_FEATURES = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]

NUMERIC_COLUMNS = [
    *NUMERIC_FEATURES,
    "finish_position",
    "is_win",
    "is_place",
    "gate",
    "number",
    "age",
    "carried_weight",
    "horse_weight",
    "horse_weight_diff",
    "market_odds",
    "odds_rank",
    "best_time",
    "last600m",
    "distance",
]


def build_pipeline(seed: int, numeric_features: list[str], categorical_features: list[str]) -> Pipeline:
    numeric = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    min_frequency=8,
                    sparse_output=True,
                    dtype=np.float32,
                ),
            ),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric, numeric_features),
            ("categorical", categorical, categorical_features),
        ],
        sparse_threshold=1.0,
    )

    model = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=1e-4,
        max_iter=50,
        tol=1e-3,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=3,
        class_weight="balanced",
        random_state=seed,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def load_training_frame(csv_path: Path) -> pd.DataFrame:
    required_columns = {
        "race_id",
        "race_date",
        "finish_position",
        "is_win",
        "is_place",
        "number",
        *ALL_FEATURES,
    }

    return pd.read_csv(
        csv_path,
        usecols=lambda name: name in required_columns,
        dtype={"race_id": "string", "race_date": "string"},
        low_memory=False,
    )


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "race_id" not in frame:
        raise ValueError("missing required column: race_id")

    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float32")

    if "is_win" not in frame:
        if "finish_position" not in frame:
            raise ValueError("missing required target: is_win or finish_position")
        frame["is_win"] = (frame["finish_position"] == 1).astype("int8")

    if "is_place" not in frame:
        if "finish_position" not in frame:
            raise ValueError("missing required target: is_place or finish_position")
        frame["is_place"] = (frame["finish_position"] <= 3).astype("int8")

    for column in NUMERIC_FEATURES:
        if column not in frame:
            frame[column] = np.nan
        else:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float32")

    for column in CATEGORICAL_FEATURES:
        if column not in frame:
            frame[column] = pd.Series("unknown", index=frame.index, dtype="category")
        else:
            frame[column] = frame[column].replace("", pd.NA).fillna("unknown").astype("category")

    frame["race_id"] = frame["race_id"].astype(str)
    if "race_date" in frame:
        frame["race_date"] = frame["race_date"].fillna("")

    return frame


def race_split_indices(frame: pd.DataFrame) -> tuple[pd.Index, pd.Index, pd.Index]:
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

    train_index = frame.index[frame["race_id"].isin(train_ids)]
    valid_index = frame.index[frame["race_id"].isin(valid_ids)]
    test_index = frame.index[frame["race_id"].isin(test_ids)]
    return train_index, valid_index, test_index


def binary_metrics(
    model: Pipeline,
    frame: pd.DataFrame,
    target: str,
    index: pd.Index,
    features: list[str],
) -> dict[str, Any]:
    subset = frame.loc[index]
    y_true = subset[target].astype(int)
    probabilities = model.predict_proba(subset[features])[:, 1]

    metrics: dict[str, Any] = {
        "rows": int(len(subset)),
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


def train_target(
    frame: pd.DataFrame,
    train_index: pd.Index,
    valid_index: pd.Index,
    test_index: pd.Index,
    features: list[str],
    numeric_features: list[str],
    categorical_features: list[str],
    target: str,
    seed: int,
) -> tuple[Pipeline, dict[str, Any]]:
    train = frame.loc[train_index]
    if train[target].nunique() < 2:
        raise ValueError(f"target {target} has only one class in train split")

    pipeline = build_pipeline(seed, numeric_features, categorical_features)
    pipeline.fit(train[features], train[target].astype(int))

    return pipeline, {
        "train": binary_metrics(pipeline, frame, target, train_index, features),
        "valid": binary_metrics(pipeline, frame, target, valid_index, features),
        "test": binary_metrics(pipeline, frame, target, test_index, features),
    }


def feature_presence(frame: pd.DataFrame) -> dict[str, float]:
    return {column: float(frame[column].notna().mean()) for column in ALL_FEATURES}


def select_training_features(frame: pd.DataFrame, train_index: pd.Index) -> tuple[list[str], list[str], list[str]]:
    train = frame.loc[train_index]
    numeric_features = [column for column in NUMERIC_FEATURES if float(train[column].notna().mean()) > 0.0]
    categorical_features = [
        column
        for column in CATEGORICAL_FEATURES
        if int(train[column].astype(str).nunique(dropna=True)) > 1
    ]
    features = [*numeric_features, *categorical_features]
    if not features:
        raise ValueError("no usable features in train split")
    return features, numeric_features, categorical_features


def train_artifact(csv_path: Path, output_dir: Path, seed: int = 42) -> dict[str, Any]:
    frame = prepare_frame(load_training_frame(csv_path))
    train_index, valid_index, test_index = race_split_indices(frame)
    features, active_numeric_features, active_categorical_features = select_training_features(frame, train_index)

    models: dict[str, Pipeline] = {}
    metrics: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(csv_path),
        "rows": int(len(frame)),
        "races": int(frame["race_id"].nunique()),
        "splits": {
            "train_rows": int(len(train_index)),
            "valid_rows": int(len(valid_index)),
            "test_rows": int(len(test_index)),
            "train_races": int(frame.loc[train_index, "race_id"].nunique()),
            "valid_races": int(frame.loc[valid_index, "race_id"].nunique()),
            "test_races": int(frame.loc[test_index, "race_id"].nunique()),
        },
        "targets": {},
        "feature_presence": feature_presence(frame),
    }

    for target in ["is_win", "is_place"]:
        model, target_metrics = train_target(
            frame,
            train_index,
            valid_index,
            test_index,
            features,
            active_numeric_features,
            active_categorical_features,
            target,
            seed,
        )
        models[target.removeprefix("is_")] = model
        metrics["targets"][target] = target_metrics

    artifact = {
        "models": models,
        "metrics": metrics,
        "numeric_features": active_numeric_features,
        "categorical_features": active_categorical_features,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    latest_path = output_dir / "latest.joblib"
    metrics_path = output_dir / "metrics.json"

    joblib.dump(artifact, model_path)
    shutil.copyfile(model_path, latest_path)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    return metrics


@lru_cache(maxsize=4)
def load_artifact(path_text: str) -> dict[str, Any] | None:
    path = Path(path_text)
    if not path.exists():
        return None
    return joblib.load(path)
