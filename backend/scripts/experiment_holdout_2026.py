from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feature_catalog import CATEGORICAL_FEATURES, TRAINING_NUMERIC_FEATURES
from app.ml_pipeline import (
    ALL_FEATURES,
    feature_presence,
    load_training_frame,
    positive_class_weight,
    prepare_frame,
    score_probabilities,
    select_training_features,
)
from app.risk_model import CalibratedBlendModel, market_probability


TARGETS = {
    "is_win": {
        "label": "win",
        "positive": "finish_position == 1",
        "market_multiplier": 1.0,
    },
    "is_top2": {
        "label": "top2",
        "positive": "finish_position <= 2",
        "market_multiplier": 2.0,
    },
    "is_place": {
        "label": "place",
        "positive": "finish_position <= 3",
        "market_multiplier": 3.0,
    },
}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    alpha: float = 1e-4
    use_positive_weight: bool = True


def build_sgd_pipeline(
    spec: ModelSpec,
    numeric_features: list[str],
    categorical_features: list[str],
    positive_weight: float,
    seed: int,
    max_iter: int,
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
    class_weight = (
        {0: 1.0, 1: positive_weight}
        if spec.use_positive_weight and positive_weight > 1.0
        else None
    )
    model = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=spec.alpha,
        max_iter=max_iter,
        tol=1e-3,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=3,
        class_weight=class_weight,
        random_state=seed,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def build_hgb_pipeline(
    numeric_features: list[str],
    positive_weight: float,
    seed: int,
    max_iter: int,
) -> Pipeline:
    model = HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_iter=max_iter,
        max_leaf_nodes=31,
        l2_regularization=0.01,
        class_weight={0: 1.0, 1: positive_weight} if positive_weight > 1 else None,
        random_state=seed,
    )
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("model", model),
        ]
    )


def model_specs(include_hgb: bool) -> list[ModelSpec]:
    specs = [
        ModelSpec("sgd_weighted_alpha_1e-4", "sgd", alpha=1e-4, use_positive_weight=True),
        ModelSpec("sgd_weighted_alpha_3e-5", "sgd", alpha=3e-5, use_positive_weight=True),
        ModelSpec("sgd_unweighted_alpha_1e-4", "sgd", alpha=1e-4, use_positive_weight=False),
    ]
    if include_hgb:
        specs.append(ModelSpec("hgb_numeric_weighted", "hgb", use_positive_weight=True))
    return specs


def load_holdout_frame(train_csv: Path, holdout_csv: Path) -> pd.DataFrame:
    train = load_training_frame(train_csv)
    holdout = load_training_frame(holdout_csv)
    frame = pd.concat([train, holdout], ignore_index=True, sort=False)
    frame = prepare_frame(frame)
    frame["finish_position"] = pd.to_numeric(frame["finish_position"], errors="coerce")
    frame["is_top2"] = (frame["finish_position"] <= 2).astype("int8")
    return frame


def race_time_split(
    frame: pd.DataFrame,
    *,
    train_end_date: str,
    holdout_start_date: str,
    holdout_end_date: str,
    calibration_fraction: float,
    train_race_limit: int,
) -> tuple[pd.Index, pd.Index, pd.Index]:
    dates = pd.to_datetime(frame["race_date"], errors="coerce")
    train_pool = frame[dates <= pd.Timestamp(train_end_date)]
    if train_pool.empty:
        raise ValueError("no training rows before train_end_date")

    races = (
        train_pool[["race_id", "race_date"]]
        .drop_duplicates()
        .sort_values(["race_date", "race_id"])
    )
    if train_race_limit > 0:
        races = races.tail(train_race_limit)
    race_ids = races["race_id"].tolist()
    split_at = max(1, int(len(race_ids) * (1 - calibration_fraction)))
    fit_ids = set(race_ids[:split_at])
    calibration_ids = set(race_ids[split_at:])

    holdout_mask = dates >= pd.Timestamp(holdout_start_date)
    if holdout_end_date:
        holdout_mask &= dates <= pd.Timestamp(holdout_end_date)

    fit_index = frame.index[frame["race_id"].isin(fit_ids)]
    calibration_index = frame.index[frame["race_id"].isin(calibration_ids)]
    holdout_index = frame.index[holdout_mask]
    return fit_index, calibration_index, holdout_index


def calibrate_and_blend(
    base_model: Pipeline,
    calibration: pd.DataFrame,
    target: str,
    features: list[str],
    fallback_rate: float,
    seed: int,
) -> tuple[CalibratedBlendModel, str, float]:
    y_cal = calibration[target].astype(int)
    raw = base_model.predict_proba(calibration[features])[:, 1]
    raw = np.clip(raw.astype(float), 1e-6, 1 - 1e-6)
    if y_cal.nunique() < 2 or float(np.nanstd(raw)) < 1e-9:
        calibrator = None
        calibration_method = "none"
    else:
        logits = np.log(raw / (1 - raw)).reshape(-1, 1)
        calibrator = LogisticRegression(max_iter=1000, random_state=seed)
        calibrator.fit(logits, y_cal)
        calibration_method = "sigmoid_train_tail"

    base = CalibratedBlendModel(
        base_model=base_model,
        calibrator=calibrator,
        target=target,
        features=features,
        market_weight=0.0,
        fallback_rate=fallback_rate,
    )
    calibrated = base.predict_positive(calibration)
    market = market_probability(calibration, target)
    candidates = [round(value, 2) for value in np.linspace(0.0, 1.0, 11)]
    best_weight = min(
        candidates,
        key=lambda weight: brier_score_loss(y_cal, (1 - weight) * calibrated + weight * market),
    )
    base.market_weight = best_weight
    return base, calibration_method, best_weight


def evaluate_model(
    model: CalibratedBlendModel,
    frame: pd.DataFrame,
    index: pd.Index,
    target: str,
    train_positive_rate: float,
) -> dict[str, Any]:
    subset = frame.loc[index]
    y_true = subset[target].astype(int)
    probabilities = model.predict_positive(subset)
    market = market_probability(subset, target)
    constant = np.full(len(subset), train_positive_rate, dtype=float)
    metrics = score_probabilities(y_true, probabilities)
    metrics["baselines"] = {
        "constant_train_rate": score_probabilities(y_true, constant),
        "market_odds": score_probabilities(y_true, market),
    }
    metrics["brier_vs_market"] = round(
        metrics["brier"] - metrics["baselines"]["market_odds"]["brier"],
        6,
    )
    metrics["auc_vs_market"] = round(
        (metrics.get("auc") or 0) - (metrics["baselines"]["market_odds"].get("auc") or 0),
        6,
    )
    return metrics


def train_candidate(
    spec: ModelSpec,
    frame: pd.DataFrame,
    target: str,
    fit_index: pd.Index,
    calibration_index: pd.Index,
    holdout_index: pd.Index,
    numeric_features: list[str],
    categorical_features: list[str],
    features: list[str],
    seed: int,
    max_iter: int,
) -> tuple[CalibratedBlendModel, dict[str, Any]]:
    fit = frame.loc[fit_index]
    calibration = frame.loc[calibration_index]
    train_positive_rate = float(fit[target].astype(int).mean())
    positive_weight = positive_class_weight(fit[target])

    if spec.family == "hgb":
        active_features = numeric_features
        base_model = build_hgb_pipeline(numeric_features, positive_weight, seed, max_iter)
    else:
        active_features = features
        base_model = build_sgd_pipeline(
            spec,
            numeric_features,
            categorical_features,
            positive_weight,
            seed,
            max_iter,
        )

    base_model.fit(fit[active_features], fit[target].astype(int))
    model, calibration_method, market_weight = calibrate_and_blend(
        base_model,
        calibration,
        target,
        active_features,
        train_positive_rate,
        seed,
    )
    metrics = {
        "model": spec.name,
        "family": spec.family,
        "target": target,
        "features": active_features,
        "positive_weight": positive_weight,
        "calibration_method": calibration_method,
        "market_ensemble_weight": market_weight,
        "fit": evaluate_model(model, frame, fit_index, target, train_positive_rate),
        "calibration": evaluate_model(
            model,
            frame,
            calibration_index,
            target,
            train_positive_rate,
        ),
        "holdout_2026": evaluate_model(model, frame, holdout_index, target, train_positive_rate),
    }
    return model, metrics


def choose_best(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        candidates,
        key=lambda item: (
            item["holdout_2026"]["brier"],
            item["holdout_2026"]["calibration"]["ece"],
            -(item["holdout_2026"].get("auc") or 0),
        ),
    )


def rank_holdout_metrics(
    frame: pd.DataFrame,
    holdout_index: pd.Index,
    models: dict[str, CalibratedBlendModel],
) -> dict[str, Any]:
    holdout = frame.loc[holdout_index].copy()
    p_win = models["is_win"].predict_positive(holdout)
    p_top2 = models["is_top2"].predict_positive(holdout)
    p_top3 = models["is_place"].predict_positive(holdout)
    p_top2 = np.maximum(p_top2, p_win)
    p_top3 = np.maximum(p_top3, p_top2)
    holdout["p_win"] = np.clip(p_win, 0, 1)
    holdout["p_second"] = np.clip(p_top2 - p_win, 0, 1)
    holdout["p_third"] = np.clip(p_top3 - p_top2, 0, 1)
    holdout["p_out"] = np.clip(1 - p_top3, 0, 1)

    race_rows: list[dict[str, Any]] = []
    for race_id, race in holdout.groupby("race_id", sort=False):
        ordered_win = race.sort_values("p_win", ascending=False)
        ordered_place = race.sort_values("p_third", ascending=False)
        winner = race.loc[race["finish_position"] == 1]
        top3 = set(race.loc[race["finish_position"] <= 3, "runner_number"].astype(int).tolist())
        predicted_winner = int(ordered_win.iloc[0]["runner_number"])
        predicted_top3 = set(ordered_win.head(3)["runner_number"].astype(int).tolist())
        race_rows.append(
            {
                "race_id": str(race_id),
                "winner_top1": int(
                    not winner.empty and predicted_winner == int(winner.iloc[0]["runner_number"])
                ),
                "winner_in_top3": int(
                    not winner.empty
                    and int(winner.iloc[0]["runner_number"])
                    in predicted_top3
                ),
                "top3_exact_set": int(bool(top3) and predicted_top3 == top3),
                "predicted_third_candidate": int(ordered_place.iloc[0]["runner_number"]),
            }
        )

    race_metrics = pd.DataFrame(race_rows)
    return {
        "races": int(len(race_metrics)),
        "winner_top1_rate": float(race_metrics["winner_top1"].mean()),
        "winner_in_top3_rate": float(race_metrics["winner_in_top3"].mean()),
        "top3_exact_set_rate": float(race_metrics["top3_exact_set"].mean()),
        "rank_probability_columns": ["p_win", "p_second", "p_third", "p_out"],
    }


def risk_router(best_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    win = best_metrics["is_win"]["holdout_2026"]
    top2 = best_metrics["is_top2"]["holdout_2026"]
    place = best_metrics["is_place"]["holdout_2026"]
    win_stable = win["brier_vs_market"] <= 0.001 and win["calibration"]["ece"] <= 0.03
    top2_stable = top2["brier_vs_market"] <= 0.0015 and top2["calibration"]["ece"] <= 0.04
    place_stable = place["brier_vs_market"] <= 0 and place["calibration"]["ece"] <= 0.05
    return {
        "stable_on_2026": bool((win_stable or top2_stable) and place_stable),
        "low_risk": {
            "primary_target": "is_place",
            "model": best_metrics["is_place"]["model"],
            "bet_families": ["place", "wide"],
        },
        "middle_risk": {
            "primary_target": "is_top2" if top2_stable else "is_place",
            "model": best_metrics["is_top2" if top2_stable else "is_place"]["model"],
            "bet_families": ["wide", "quinella", "trio"],
        },
        "high_risk": {
            "primary_target": "is_win" if win_stable else "is_top2",
            "model": best_metrics["is_win" if win_stable else "is_top2"]["model"],
            "bet_families": ["exacta", "trio", "trifecta" if win_stable else "trio_axis_only"],
            "trifecta_enabled": bool(win_stable),
        },
        "checks": {
            "win_stable": bool(win_stable),
            "top2_stable": bool(top2_stable),
            "place_stable": bool(place_stable),
        },
    }


def compact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    best = {}
    for target, metrics in payload["best"].items():
        holdout = metrics["holdout_2026"]
        best[target] = {
            "model": metrics["model"],
            "market_ensemble_weight": metrics["market_ensemble_weight"],
            "holdout_brier": round(float(holdout["brier"]), 6),
            "holdout_brier_vs_market": holdout["brier_vs_market"],
            "holdout_auc": round(float(holdout.get("auc") or 0), 6),
            "holdout_auc_vs_market": holdout["auc_vs_market"],
            "holdout_ece": holdout["calibration"]["ece"],
        }
    return {
        "trained_at": payload["trained_at"],
        "split": payload["split"],
        "best": best,
        "rank_holdout_2026": payload["rank_holdout_2026"],
        "risk_router": payload["risk_router"],
        "metrics_path": payload["metrics_path"],
        "artifact_path": payload["artifact_path"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train multiple risk-oriented models on <=2025 and validate on 2026."
    )
    parser.add_argument("--train-csv", type=Path, default=Path("data/keiba_history_normalized.csv"))
    parser.add_argument(
        "--holdout-csv",
        type=Path,
        default=Path("data/netkeiba_2026_normalized.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("models/racequant_holdout_2026"))
    parser.add_argument("--train-end-date", default="2025-12-31")
    parser.add_argument("--holdout-start-date", default="2026-01-01")
    parser.add_argument("--holdout-end-date", default="")
    parser.add_argument("--calibration-fraction", type=float, default=0.15)
    parser.add_argument("--train-race-limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=35)
    parser.add_argument("--include-hgb", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    frame = load_holdout_frame(args.train_csv, args.holdout_csv)
    fit_index, calibration_index, holdout_index = race_time_split(
        frame,
        train_end_date=args.train_end_date,
        holdout_start_date=args.holdout_start_date,
        holdout_end_date=args.holdout_end_date,
        calibration_fraction=args.calibration_fraction,
        train_race_limit=args.train_race_limit,
    )
    features, numeric_features, categorical_features = select_training_features(frame, fit_index)

    all_metrics: dict[str, list[dict[str, Any]]] = {target: [] for target in TARGETS}
    trained_models: dict[str, dict[str, CalibratedBlendModel]] = {target: {} for target in TARGETS}
    for target in TARGETS:
        for spec in model_specs(args.include_hgb):
            model, metrics = train_candidate(
                spec,
                frame,
                target,
                fit_index,
                calibration_index,
                holdout_index,
                numeric_features,
                categorical_features,
                features,
                args.seed,
                args.max_iter,
            )
            all_metrics[target].append(metrics)
            trained_models[target][spec.name] = model

    best_metrics = {target: choose_best(metrics) for target, metrics in all_metrics.items()}
    best_models = {
        target: trained_models[target][metrics["model"]]
        for target, metrics in best_metrics.items()
    }
    rank_metrics = rank_holdout_metrics(frame, holdout_index, best_models)
    router = risk_router(best_metrics)

    payload = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_csv": str(args.train_csv),
        "holdout_csv": str(args.holdout_csv),
        "split": {
            "fit_rows": int(len(fit_index)),
            "fit_races": int(frame.loc[fit_index, "race_id"].nunique()),
            "calibration_rows": int(len(calibration_index)),
            "calibration_races": int(frame.loc[calibration_index, "race_id"].nunique()),
            "holdout_rows": int(len(holdout_index)),
            "holdout_races": int(frame.loc[holdout_index, "race_id"].nunique()),
            "train_end_date": args.train_end_date,
            "holdout_start_date": args.holdout_start_date,
            "holdout_end_date": args.holdout_end_date or None,
        },
        "targets": all_metrics,
        "best": best_metrics,
        "rank_holdout_2026": rank_metrics,
        "risk_router": router,
        "feature_presence": feature_presence(frame),
        "active_numeric_features": numeric_features,
        "active_categorical_features": categorical_features,
    }

    artifact = {
        "models": best_models,
        "metrics": payload,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "rank_probability_columns": ["p_win", "p_second", "p_third", "p_out"],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output_dir / "holdout_experiment.json"
    artifact_path = args.output_dir / "holdout_artifact.joblib"
    payload["metrics_path"] = str(metrics_path)
    payload["artifact_path"] = str(artifact_path)
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    joblib.dump(artifact, artifact_path)

    print(json.dumps(compact_summary(payload), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
