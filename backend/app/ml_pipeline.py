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
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TRAINING_NUMERIC_FEATURES


ALL_FEATURES = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]
TRAINING_FEATURE_CANDIDATES = [*TRAINING_NUMERIC_FEATURES, *CATEGORICAL_FEATURES]

NUMERIC_COLUMNS = [
    *NUMERIC_FEATURES,
    "finish_position",
    "is_win",
    "is_place",
    "gate",
    "bracket",
    "number",
    "race_no",
    "horse_number",
    "runner_number",
    "field_size",
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


def build_pipeline(
    seed: int,
    numeric_features: list[str],
    categorical_features: list[str],
    positive_weight: float,
) -> Pipeline:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
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

    class_weight = {0: 1.0, 1: positive_weight} if positive_weight > 1.0 else None
    model = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=1e-4,
        max_iter=50,
        tol=1e-3,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=3,
        class_weight=class_weight,
        random_state=seed,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


class ProbabilityCalibratedPipeline:
    def __init__(
        self,
        base_model: Pipeline,
        calibrator: LogisticRegression | None,
        fallback_positive_rate: float,
        target: str,
        market_weight: float = 0.0,
    ) -> None:
        self.base_model = base_model
        self.calibrator = calibrator
        self.fallback_positive_rate = fallback_positive_rate
        self.target = target
        self.market_weight = market_weight

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.base_model.predict_proba(frame)[:, 1]
        raw = np.clip(raw.astype(float), 1e-6, 1 - 1e-6)
        if self.calibrator is None:
            probabilities = raw
        else:
            logits = np.log(raw / (1 - raw)).reshape(-1, 1)
            probabilities = self.calibrator.predict_proba(logits)[:, 1]
        probabilities = np.clip(probabilities.astype(float), 1e-6, 1 - 1e-6)
        if not np.isfinite(probabilities).all():
            probabilities = np.full(len(frame), self.fallback_positive_rate, dtype=float)
        if self.market_weight > 0:
            market = market_probability_from_features(frame, self.target)
            probabilities = (1 - self.market_weight) * probabilities + self.market_weight * market
            probabilities = np.clip(probabilities.astype(float), 1e-6, 1 - 1e-6)
        return np.column_stack([1 - probabilities, probabilities])


def market_probability_from_features(frame: pd.DataFrame, target: str) -> np.ndarray:
    column = "market_place_probability" if target == "is_place" else "market_win_probability"
    if column in frame:
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0).to_numpy(dtype=float)
        return np.clip(values, 1e-6, 0.95)

    if "market_odds" not in frame:
        return np.full(len(frame), 1e-6, dtype=float)

    odds = pd.to_numeric(frame["market_odds"], errors="coerce").replace(0, np.nan)
    implied = (1 / odds).replace([np.inf, -np.inf], np.nan).fillna(0)
    if "race_id" in frame:
        race_total = implied.groupby(frame["race_id"]).transform("sum").replace(0, np.nan)
        win_probability = (implied / race_total).fillna(0)
    else:
        total = float(implied.sum())
        win_probability = (implied / total).fillna(0) if total else pd.Series(0, index=frame.index)
    if target == "is_place":
        field_size = (
            pd.to_numeric(frame["field_size"], errors="coerce")
            if "field_size" in frame
            else pd.Series(len(frame), index=frame.index)
        )
        field_values = field_size.fillna(len(frame)).to_numpy(dtype=float)
        values = win_probability.to_numpy(dtype=float) * np.minimum(field_values, 3)
        return np.clip(values, 1e-6, 0.95)
    return np.clip(win_probability.to_numpy(dtype=float), 1e-6, 0.95)


def positive_class_weight(target: pd.Series) -> float:
    positive_rate = float(target.astype(int).mean())
    if positive_rate <= 0 or positive_rate >= 0.5:
        return 1.0
    imbalance = (1 - positive_rate) / positive_rate
    return round(min(4.0, max(1.0, float(np.sqrt(imbalance)))), 4)


def calibrate_probabilities(
    base_model: Pipeline,
    validation: pd.DataFrame,
    target: str,
    features: list[str],
    train_positive_rate: float,
    seed: int,
) -> tuple[ProbabilityCalibratedPipeline, str, float]:
    y_valid = validation[target].astype(int)
    raw = base_model.predict_proba(validation[features])[:, 1]
    raw = np.clip(raw.astype(float), 1e-6, 1 - 1e-6)
    if y_valid.nunique() < 2 or float(np.nanstd(raw)) < 1e-9:
        model = ProbabilityCalibratedPipeline(base_model, None, train_positive_rate, target)
    else:
        logits = np.log(raw / (1 - raw)).reshape(-1, 1)
        calibrator = LogisticRegression(max_iter=1000, random_state=seed)
        calibrator.fit(logits, y_valid)
        model = ProbabilityCalibratedPipeline(base_model, calibrator, train_positive_rate, target)

    market = market_probability_from_features(validation[features], target)
    base = model.predict_proba(validation[features])[:, 1]
    candidates = [0.0, 0.25, 0.5, 0.75]
    best_weight = min(
        candidates,
        key=lambda weight: brier_score_loss(y_valid, (1 - weight) * base + weight * market),
    )
    model.market_weight = best_weight
    calibration_method = "none" if model.calibrator is None else "sigmoid_valid_split"
    return model, calibration_method, best_weight


def load_training_frame(csv_path: Path) -> pd.DataFrame:
    required_columns = {
        "race_id",
        "race_date",
        "finish_position",
        "is_win",
        "is_place",
        "race_no",
        "number",
        "horse_number",
        "runner_number",
        "bracket",
        "gate",
        "field_size",
        "horse_name",
        *ALL_FEATURES,
    }

    return pd.read_csv(
        csv_path,
        usecols=lambda name: name in required_columns,
        dtype={"race_id": "string", "race_date": "string"},
        low_memory=False,
    )


def bracket_from_runner_number(number: float | int | None) -> float:
    if number is None or pd.isna(number):
        return np.nan
    return float(min(max(int(np.ceil(float(number) / 2)), 1), 8))


def canonicalize_runner_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if "number" in frame:
        frame["number"] = pd.to_numeric(frame["number"], errors="coerce")
    if "gate" in frame:
        frame["gate"] = pd.to_numeric(frame["gate"], errors="coerce")

    if "runner_number" in frame:
        runner_number = pd.to_numeric(frame["runner_number"], errors="coerce")
    elif "horse_number" in frame:
        runner_number = pd.to_numeric(frame["horse_number"], errors="coerce")
    elif "number" in frame and "gate" in frame:
        # Older normalized CSVs stored race number in `number` and horse number in `gate`.
        number_unique = frame.groupby("race_id")["number"].transform("nunique")
        gate_unique = frame.groupby("race_id")["gate"].transform("nunique")
        use_gate_as_runner_number = (number_unique <= 2) & (gate_unique > number_unique)
        runner_number = frame["number"].where(~use_gate_as_runner_number, frame["gate"])
        if "race_no" not in frame:
            frame["race_no"] = frame["number"].where(use_gate_as_runner_number)
    elif "number" in frame:
        runner_number = frame["number"]
    else:
        raise ValueError(
            "missing runner number column: expected number, gate, runner_number, or horse_number"
        )

    frame["runner_number"] = pd.to_numeric(runner_number, errors="coerce").astype("float32")
    if "horse_number" not in frame:
        frame["horse_number"] = frame["runner_number"]
    if "bracket" in frame:
        frame["bracket"] = pd.to_numeric(frame["bracket"], errors="coerce")
    else:
        frame["bracket"] = frame["runner_number"].map(bracket_from_runner_number)
    frame["gate"] = frame["bracket"]
    if "field_size" not in frame:
        frame["field_size"] = frame.groupby("race_id")["race_id"].transform("size")
    return frame


def shifted_rolling_mean(series: pd.Series, window: int, min_periods: int = 1) -> pd.Series:
    return series.shift().rolling(window=window, min_periods=min_periods).mean()


def shifted_expanding_mean(series: pd.Series, min_periods: int = 3) -> pd.Series:
    return series.shift().expanding(min_periods=min_periods).mean()


def add_historical_features(frame: pd.DataFrame) -> pd.DataFrame:
    sort_columns = ["race_date", "race_id"]
    if "race_no" in frame:
        sort_columns.append("race_no")
    sort_columns.append("runner_number")
    frame = frame.sort_values(sort_columns).copy()

    if "horse_name" in frame:
        frame["horse_name"] = frame["horse_name"].replace("", pd.NA).fillna("unknown").astype(str)
        race_dates = pd.to_datetime(frame.get("race_date"), errors="coerce")
        frame["days_since_last_run"] = (
            race_dates.groupby(frame["horse_name"]).diff().dt.days.astype("float32")
        )

        if "best_time" in frame and "distance" in frame:
            best_time = pd.to_numeric(frame["best_time"], errors="coerce")
            distance = pd.to_numeric(frame["distance"], errors="coerce")
            historical_speed = (distance / best_time).where((best_time > 0) & (distance > 0))
            frame["avg_last3_speed"] = (
                historical_speed.groupby(frame["horse_name"])
                .transform(lambda series: shifted_rolling_mean(series, window=3))
                .astype("float32")
            )

        frame["horse_recent_win_rate"] = (
            frame.groupby("horse_name")["is_win"]
            .transform(lambda series: shifted_rolling_mean(series, window=3))
            .astype("float32")
        )
        frame["horse_recent_place_rate"] = (
            frame.groupby("horse_name")["is_place"]
            .transform(lambda series: shifted_rolling_mean(series, window=3))
            .astype("float32")
        )

        if "distance" in frame:
            distance = pd.to_numeric(frame["distance"], errors="coerce")
            frame["__distance_bucket"] = (distance / 200).round() * 200
            frame["horse_distance_place_rate"] = (
                frame.groupby(["horse_name", "__distance_bucket"], dropna=False)["is_place"]
                .transform(lambda series: shifted_expanding_mean(series, min_periods=2))
                .astype("float32")
            )

        if "surface" in frame:
            frame["horse_surface_place_rate"] = (
                frame.groupby(["horse_name", "surface"], dropna=False)["is_place"]
                .transform(lambda series: shifted_expanding_mean(series, min_periods=2))
                .astype("float32")
            )

    if "jockey" in frame:
        frame["jockey_win_rate"] = (
            frame.groupby("jockey", dropna=False)["is_win"]
            .transform(lambda series: shifted_expanding_mean(series, min_periods=10))
            .astype("float32")
        )
    if "trainer" in frame:
        frame["trainer_win_rate"] = (
            frame.groupby("trainer", dropna=False)["is_win"]
            .transform(lambda series: shifted_expanding_mean(series, min_periods=10))
            .astype("float32")
        )

    if {"venue", "surface", "distance", "bracket"}.issubset(frame.columns):
        if "__distance_bucket" not in frame:
            distance = pd.to_numeric(frame["distance"], errors="coerce")
            frame["__distance_bucket"] = (distance / 200).round() * 200
        frame["draw_bias"] = (
            frame.groupby(
                ["venue", "surface", "__distance_bucket", "bracket"],
                dropna=False,
            )["is_place"]
            .transform(lambda series: shifted_expanding_mean(series, min_periods=20))
            .astype("float32")
        )

    return frame.drop(columns=["__distance_bucket"], errors="ignore")


def add_market_features(frame: pd.DataFrame) -> pd.DataFrame:
    odds_source = (
        frame["market_odds"] if "market_odds" in frame else pd.Series(np.nan, index=frame.index)
    )
    odds = pd.to_numeric(odds_source, errors="coerce").replace(0, np.nan)
    implied = (1 / odds).replace([np.inf, -np.inf], np.nan)
    race_total = implied.groupby(frame["race_id"]).transform("sum").replace(0, np.nan)
    win_probability = (implied / race_total).fillna(0)
    field_size = pd.to_numeric(frame.get("field_size"), errors="coerce").fillna(
        frame.groupby("race_id")["race_id"].transform("size")
    )
    frame["market_win_probability"] = win_probability.astype("float32")
    frame["market_place_probability"] = np.clip(
        win_probability.to_numpy(dtype=float) * np.minimum(field_size.to_numpy(dtype=float), 3),
        1e-6,
        0.95,
    ).astype("float32")
    return frame


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "race_id" not in frame:
        raise ValueError("missing required column: race_id")

    frame["race_id"] = frame["race_id"].astype(str)
    frame = canonicalize_runner_columns(frame)

    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float32")

    if "is_win" not in frame:
        if "finish_position" not in frame:
            raise ValueError("missing required target: is_win or finish_position")
        frame["is_win"] = (frame["finish_position"] == 1).astype("int8")
    else:
        frame["is_win"] = pd.to_numeric(frame["is_win"], errors="coerce").fillna(0).astype("int8")

    if "is_place" not in frame:
        if "finish_position" not in frame:
            raise ValueError("missing required target: is_place or finish_position")
        frame["is_place"] = (frame["finish_position"] <= 3).astype("int8")
    else:
        frame["is_place"] = (
            pd.to_numeric(frame["is_place"], errors="coerce").fillna(0).astype("int8")
        )

    market_odds = (
        pd.to_numeric(frame["market_odds"], errors="coerce")
        if "market_odds" in frame
        else pd.Series(2.0, index=frame.index)
    )
    frame = frame[
        (pd.to_numeric(frame["finish_position"], errors="coerce") > 0)
        & (pd.to_numeric(frame["runner_number"], errors="coerce") > 0)
        & (market_odds > 1)
    ].copy()
    frame = frame.groupby("race_id", sort=False).filter(lambda group: len(group) >= 2)
    frame = add_market_features(frame)
    frame = add_historical_features(frame)

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

    if "race_date" in frame:
        frame["race_date"] = frame["race_date"].fillna("")

    return frame


def race_split_indices(frame: pd.DataFrame) -> tuple[pd.Index, pd.Index, pd.Index]:
    if "race_date" in frame:
        races = (
            frame[["race_id", "race_date"]]
            .drop_duplicates()
            .sort_values(["race_date", "race_id"])
        )
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


def calibration_curve(
    y_true: pd.Series,
    probabilities: np.ndarray,
    bins: int = 10,
) -> dict[str, Any]:
    clipped = np.clip(probabilities, 0.0, 1.0)
    edges = np.linspace(0, 1, bins + 1)
    rows: list[dict[str, float | int]] = []
    ece = 0.0
    total = len(clipped)

    for index in range(bins):
        lower = edges[index]
        upper = edges[index + 1]
        if index == bins - 1:
            mask = (clipped >= lower) & (clipped <= upper)
        else:
            mask = (clipped >= lower) & (clipped < upper)
        count = int(mask.sum())
        if count == 0:
            continue
        mean_pred = float(clipped[mask].mean())
        actual_rate = float(y_true.iloc[np.flatnonzero(mask)].mean())
        ece += (count / total) * abs(mean_pred - actual_rate)
        rows.append(
            {
                "lower": round(float(lower), 3),
                "upper": round(float(upper), 3),
                "count": count,
                "mean_pred": round(mean_pred, 5),
                "actual_rate": round(actual_rate, 5),
            }
        )

    return {"ece": round(float(ece), 6), "bins": rows}


def score_probabilities(y_true: pd.Series, probabilities: np.ndarray) -> dict[str, Any]:
    probabilities = np.clip(probabilities.astype(float), 1e-6, 1 - 1e-6)
    metrics: dict[str, Any] = {
        "rows": int(len(y_true)),
        "positive_rate": float(y_true.mean()),
        "brier": float(brier_score_loss(y_true, probabilities)),
        "calibration": calibration_curve(y_true, probabilities),
    }

    labels = set(y_true.tolist())
    if len(labels) == 2:
        metrics["auc"] = float(roc_auc_score(y_true, probabilities))
        metrics["log_loss"] = float(log_loss(y_true, probabilities, labels=[0, 1]))
    else:
        metrics["auc"] = None
        metrics["log_loss"] = None

    return metrics


def market_baseline_probabilities(subset: pd.DataFrame, target: str) -> np.ndarray:
    odds = pd.to_numeric(subset.get("market_odds"), errors="coerce").replace(0, np.nan)
    implied = (1 / odds).replace([np.inf, -np.inf], np.nan)
    race_total = implied.groupby(subset["race_id"]).transform("sum").replace(0, np.nan)
    win_prob = (implied / race_total).fillna(0)
    if target == "is_place":
        if "field_size" in subset:
            field_size = pd.to_numeric(subset["field_size"], errors="coerce").fillna(
                subset.groupby("race_id")["race_id"].transform("size")
            )
        else:
            field_size = subset.groupby("race_id")["race_id"].transform("size")
        place_prob = win_prob.to_numpy(dtype=float) * np.minimum(
            field_size.to_numpy(dtype=float),
            3,
        )
        return np.clip(place_prob, 1e-6, 0.95)
    return np.clip(win_prob.to_numpy(dtype=float), 1e-6, 0.95)


def binary_metrics(
    model: Any,
    frame: pd.DataFrame,
    target: str,
    index: pd.Index,
    features: list[str],
    train_positive_rate: float,
) -> dict[str, Any]:
    subset = frame.loc[index]
    y_true = subset[target].astype(int)
    probabilities = model.predict_proba(subset[features])[:, 1]
    metrics = score_probabilities(y_true, probabilities)
    constant = np.full(len(subset), train_positive_rate, dtype=float)
    market = market_baseline_probabilities(subset, target)
    metrics["baselines"] = {
        "constant_train_rate": score_probabilities(y_true, constant),
        "market_odds": score_probabilities(y_true, market),
    }
    metrics["brier_vs_market"] = round(
        metrics["brier"] - metrics["baselines"]["market_odds"]["brier"],
        6,
    )
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
) -> tuple[ProbabilityCalibratedPipeline, dict[str, Any]]:
    train = frame.loc[train_index]
    if train[target].nunique() < 2:
        raise ValueError(f"target {target} has only one class in train split")

    train_positive_rate = float(train[target].astype(int).mean())
    positive_weight = positive_class_weight(train[target])
    base_pipeline = build_pipeline(seed, numeric_features, categorical_features, positive_weight)
    base_pipeline.fit(train[features], train[target].astype(int))
    pipeline, calibration_method, market_weight = calibrate_probabilities(
        base_pipeline,
        frame.loc[valid_index],
        target,
        features,
        train_positive_rate,
        seed,
    )

    target_metrics = {
        "positive_weight": positive_weight,
        "calibration_method": calibration_method,
        "market_ensemble_weight": market_weight,
        "train": binary_metrics(
            pipeline, frame, target, train_index, features, train_positive_rate
        ),
        "valid": binary_metrics(
            pipeline, frame, target, valid_index, features, train_positive_rate
        ),
        "test": binary_metrics(pipeline, frame, target, test_index, features, train_positive_rate),
    }
    return pipeline, target_metrics


def feature_presence(frame: pd.DataFrame) -> dict[str, float]:
    return {column: float(frame[column].notna().mean()) for column in ALL_FEATURES}


def select_training_features(
    frame: pd.DataFrame,
    train_index: pd.Index,
) -> tuple[list[str], list[str], list[str]]:
    train = frame.loc[train_index]
    numeric_features = [
        column for column in TRAINING_NUMERIC_FEATURES if float(train[column].notna().mean()) > 0.0
    ]
    categorical_features = [
        column
        for column in CATEGORICAL_FEATURES
        if int(train[column].astype(str).nunique(dropna=True)) > 1
    ]
    features = [*numeric_features, *categorical_features]
    if not features:
        raise ValueError("no usable features in train split")
    return features, numeric_features, categorical_features


def limit_frame_by_races(frame: pd.DataFrame, race_limit: int | None) -> pd.DataFrame:
    if not race_limit or race_limit <= 0:
        return frame
    races = frame[["race_id", "race_date"]].drop_duplicates().sort_values(["race_date", "race_id"])
    selected = set(races["race_id"].head(race_limit))
    return frame[frame["race_id"].isin(selected)].copy()


def quality_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    targets = metrics.get("targets", {})
    checks: dict[str, bool] = {}
    for target in ["is_win", "is_place"]:
        test = targets.get(target, {}).get("test", {})
        market = test.get("baselines", {}).get("market_odds", {})
        checks[f"{target}_auc_at_least_0_56"] = bool((test.get("auc") or 0) >= 0.56)
        checks[f"{target}_brier_beats_constant"] = bool(
            test.get("brier", 1)
            < test.get("baselines", {}).get("constant_train_rate", {}).get("brier", 0)
        )
        checks[f"{target}_brier_not_worse_than_market_by_5pct"] = bool(
            test.get("brier", 1) <= market.get("brier", 0) * 1.05 if market else False
        )
        checks[f"{target}_ece_under_0_08"] = bool(test.get("calibration", {}).get("ece", 1) <= 0.08)
    return {
        "checks": checks,
        "publishable": all(checks.values()),
        "note": "Use full training/backtest for the public UI only when publishable is true.",
    }


def train_artifact(
    csv_path: Path,
    output_dir: Path,
    seed: int = 42,
    race_limit: int | None = None,
) -> dict[str, Any]:
    frame = prepare_frame(load_training_frame(csv_path))
    frame = limit_frame_by_races(frame, race_limit)
    train_index, valid_index, test_index = race_split_indices(frame)
    features, active_numeric_features, active_categorical_features = select_training_features(
        frame,
        train_index,
    )

    models: dict[str, ProbabilityCalibratedPipeline] = {}
    metrics: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(csv_path),
        "rows": int(len(frame)),
        "races": int(frame["race_id"].nunique()),
        "race_limit": race_limit or 0,
        "excluded_training_features": ["place_odds", "best_time", "last600m"],
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

    metrics["quality_gate"] = quality_gate(metrics)

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
