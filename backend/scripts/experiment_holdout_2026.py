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


JRA_VENUES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}


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

MARKET_DIRECT_FEATURES = {
    "market_odds",
    "market_win_probability",
    "market_place_probability",
    "odds_rank",
    "odds_delta",
    "ticket_pool_share",
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


def inferred_market(frame: pd.DataFrame) -> pd.Series:
    if "market" in frame.columns:
        market = frame["market"].astype(str).str.upper()
        return market.where(market.isin(["JRA", "NAR"]), "NAR")
    venue = frame.get("venue", pd.Series("", index=frame.index)).astype(str)
    return pd.Series(np.where(venue.isin(JRA_VENUES), "JRA", "NAR"), index=frame.index)


def filter_index_by_market(frame: pd.DataFrame, index: pd.Index, market: str) -> pd.Index:
    market = market.upper()
    if market not in {"JRA", "NAR"}:
        return index
    subset = frame.loc[index]
    mask = inferred_market(subset) == market
    return subset.index[mask]


def calibrate_and_blend(
    base_model: Pipeline,
    calibration: pd.DataFrame,
    target: str,
    features: list[str],
    fallback_rate: float,
    seed: int,
    market_weight_cap: float,
    market_weight_step: float,
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
    cap = float(np.clip(market_weight_cap, 0, 1))
    step = max(0.01, min(float(market_weight_step), 1.0))
    candidates = sorted(
        {
            0.0,
            round(cap, 2),
            *[
                round(value, 2)
                for value in np.arange(0.0, cap + step / 2, step)
                if value <= cap + 1e-9
            ],
        }
    )
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
    market_weight_cap: float,
    market_weight_step: float,
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
        market_weight_cap,
        market_weight_step,
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


def market_dependency_metrics(holdout: pd.DataFrame, score_column: str) -> dict[str, Any]:
    rows: list[dict[str, float | int]] = []
    for _, race in holdout.groupby("race_id", sort=False):
        if race.empty:
            continue
        predicted = race.sort_values(score_column, ascending=False).iloc[0]
        odds = pd.to_numeric(race.get("market_odds"), errors="coerce")
        if odds.isna().all():
            continue
        favorite_index = odds.idxmin()
        favorite = race.loc[favorite_index]
        winner = race.loc[race["finish_position"] == 1]
        predicted_number = int(predicted["runner_number"])
        favorite_number = int(favorite["runner_number"])
        rows.append(
            {
                "predicted_is_favorite": int(predicted_number == favorite_number),
                "favorite_won": int(
                    not winner.empty and favorite_number == int(winner.iloc[0]["runner_number"])
                ),
                "predicted_odds": float(predicted.get("market_odds") or np.nan),
                "favorite_odds": float(favorite.get("market_odds") or np.nan),
            }
        )
    if not rows:
        return {
            "races_with_odds": 0,
            "predicted_top1_favorite_rate": None,
            "market_favorite_win_rate": None,
        }
    metrics = pd.DataFrame(rows)
    return {
        "races_with_odds": int(len(metrics)),
        "predicted_top1_favorite_rate": float(metrics["predicted_is_favorite"].mean()),
        "market_favorite_win_rate": float(metrics["favorite_won"].mean()),
        "predicted_top1_mean_odds": float(metrics["predicted_odds"].mean()),
        "market_favorite_mean_odds": float(metrics["favorite_odds"].mean()),
    }


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
    holdout["rank_score"] = (
        holdout["p_win"] * 1.0
        + holdout["p_second"] * 0.42
        + holdout["p_third"] * 0.18
    )

    race_rows: list[dict[str, Any]] = []
    for race_id, race in holdout.groupby("race_id", sort=False):
        ordered_win = race.sort_values("rank_score", ascending=False)
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
        "market_dependency": market_dependency_metrics(holdout, "rank_score"),
        "rank_probability_columns": ["p_win", "p_second", "p_third", "p_out"],
    }


def apply_feature_mode(
    features: list[str],
    numeric_features: list[str],
    categorical_features: list[str],
    feature_mode: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    if feature_mode == "anti_market":
        removed = [feature for feature in features if feature in MARKET_DIRECT_FEATURES]
        numeric_features = [
            feature for feature in numeric_features if feature not in MARKET_DIRECT_FEATURES
        ]
        features = [feature for feature in features if feature not in MARKET_DIRECT_FEATURES]
        return features, numeric_features, categorical_features, removed
    return features, numeric_features, categorical_features, []


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


def train_best_bundle(
    frame: pd.DataFrame,
    fit_index: pd.Index,
    calibration_index: pd.Index,
    holdout_index: pd.Index,
    args: argparse.Namespace,
) -> dict[str, Any]:
    features, numeric_features, categorical_features = select_training_features(frame, fit_index)
    features, numeric_features, categorical_features, removed_features = apply_feature_mode(
        features,
        numeric_features,
        categorical_features,
        args.feature_mode,
    )

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
                args.market_weight_cap,
                args.market_weight_step,
            )
            all_metrics[target].append(metrics)
            trained_models[target][spec.name] = model

    best_metrics = {target: choose_best(metrics) for target, metrics in all_metrics.items()}
    best_models = {
        target: trained_models[target][metrics["model"]]
        for target, metrics in best_metrics.items()
    }
    return {
        "targets": all_metrics,
        "best": best_metrics,
        "models": best_models,
        "rank_holdout_2026": rank_holdout_metrics(frame, holdout_index, best_models),
        "risk_router": risk_router(best_metrics),
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "features": features,
        "removed_market_features": removed_features,
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
        "segment_metrics": {
            market: metrics.get("rank_holdout_2026", {})
            for market, metrics in payload.get("segment_metrics", {}).items()
        },
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
    parser.add_argument("--train-market", choices=["", "JRA", "NAR"], default="")
    parser.add_argument("--holdout-market", choices=["", "JRA", "NAR"], default="")
    parser.add_argument(
        "--segment-by-market",
        action="store_true",
        help="Train additional JRA/NAR specialist models in the same artifact.",
    )
    parser.add_argument("--calibration-fraction", type=float, default=0.15)
    parser.add_argument("--train-race-limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=35)
    parser.add_argument("--include-hgb", action="store_true")
    parser.add_argument(
        "--feature-mode",
        choices=["all", "anti_market"],
        default="all",
        help="anti_market removes direct odds/popularity features from the trained model.",
    )
    parser.add_argument(
        "--market-weight-cap",
        type=float,
        default=1.0,
        help="Upper limit for blending calibrated model probabilities with market probabilities.",
    )
    parser.add_argument("--market-weight-step", type=float, default=0.05)
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
    if args.train_market:
        fit_index = filter_index_by_market(frame, fit_index, args.train_market)
        calibration_index = filter_index_by_market(frame, calibration_index, args.train_market)
    if args.holdout_market:
        holdout_index = filter_index_by_market(frame, holdout_index, args.holdout_market)
    if len(fit_index) == 0 or len(calibration_index) == 0 or len(holdout_index) == 0:
        raise ValueError("market filters produced an empty fit/calibration/holdout split")
    bundle = train_best_bundle(frame, fit_index, calibration_index, holdout_index, args)
    segment_bundles: dict[str, dict[str, Any]] = {}
    if args.segment_by_market:
        for market in ("JRA", "NAR"):
            segment_fit = filter_index_by_market(frame, fit_index, market)
            segment_calibration = filter_index_by_market(frame, calibration_index, market)
            segment_holdout = filter_index_by_market(frame, holdout_index, market)
            if len(segment_fit) == 0 or len(segment_calibration) == 0 or len(segment_holdout) == 0:
                continue
            segment_bundles[market] = train_best_bundle(
                frame,
                segment_fit,
                segment_calibration,
                segment_holdout,
                args,
            )

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
            "train_market": args.train_market or "ALL",
            "holdout_market": args.holdout_market or "ALL",
        },
        "feature_mode": args.feature_mode,
        "segment_by_market": args.segment_by_market,
        "removed_market_features": bundle["removed_market_features"],
        "market_weight_cap": args.market_weight_cap,
        "market_weight_step": args.market_weight_step,
        "targets": bundle["targets"],
        "best": bundle["best"],
        "rank_holdout_2026": bundle["rank_holdout_2026"],
        "risk_router": bundle["risk_router"],
        "segment_metrics": {
            market: {
                "best": segment["best"],
                "rank_holdout_2026": segment["rank_holdout_2026"],
                "risk_router": segment["risk_router"],
                "active_numeric_features": segment["numeric_features"],
                "active_categorical_features": segment["categorical_features"],
            }
            for market, segment in segment_bundles.items()
        },
        "feature_presence": feature_presence(frame),
        "active_numeric_features": bundle["numeric_features"],
        "active_categorical_features": bundle["categorical_features"],
    }

    artifact = {
        "models": bundle["models"],
        "segment_models": {
            market: {
                "models": segment["models"],
                "metrics": {
                    "best": segment["best"],
                    "rank_holdout_2026": segment["rank_holdout_2026"],
                    "risk_router": segment["risk_router"],
                },
                "numeric_features": segment["numeric_features"],
                "categorical_features": segment["categorical_features"],
            }
            for market, segment in segment_bundles.items()
        },
        "metrics": payload,
        "numeric_features": bundle["numeric_features"],
        "categorical_features": bundle["categorical_features"],
        "rank_probability_columns": ["p_win", "p_second", "p_third", "p_out"],
        "feature_mode": args.feature_mode,
        "removed_market_features": bundle["removed_market_features"],
        "market_weight_cap": args.market_weight_cap,
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
