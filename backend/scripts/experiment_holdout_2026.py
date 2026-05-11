from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations, permutations, product
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
    "odds_delta_5m",
    "odds_delta_15m",
    "odds_volatility",
    "ticket_pool_share",
    "log_market_odds",
    "odds_to_favorite",
    "favorite_market_odds",
    "market_top3_probability",
    "market_entropy",
    "market_rank_pct",
}

MARKET_BASELINE_SUPPORT_FEATURES = {
    "runner_number",
    "bracket",
    "field_size",
    *MARKET_DIRECT_FEATURES,
}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    alpha: float = 1e-4
    use_positive_weight: bool = True
    learning_rate: float = 0.06
    max_leaf_nodes: int = 31
    l2_regularization: float = 0.01
    feature_mode: str = "global"
    market_weight_cap: float | None = None


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
    spec: ModelSpec,
    numeric_features: list[str],
    positive_weight: float,
    seed: int,
    max_iter: int,
) -> Pipeline:
    model = HistGradientBoostingClassifier(
        learning_rate=spec.learning_rate,
        max_iter=max_iter,
        max_leaf_nodes=spec.max_leaf_nodes,
        l2_regularization=spec.l2_regularization,
        class_weight={0: 1.0, 1: positive_weight}
        if spec.use_positive_weight and positive_weight > 1
        else None,
        random_state=seed,
    )
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("model", model),
        ]
    )


def _jra30_variants(base_specs: list[ModelSpec], *, include_hgb: bool) -> list[ModelSpec]:
    linear_specs = [spec for spec in base_specs if spec.family == "sgd"]
    hgb_specs = [spec for spec in base_specs if spec.family == "hgb"] if include_hgb else []
    variants: list[ModelSpec] = []
    for feature_mode, market_cap in (
        ("anti_market", 0.08),
        ("anti_market", 0.16),
        ("all", 0.05),
    ):
        for spec in linear_specs:
            variants.append(
                ModelSpec(
                    name=f"{spec.name}_{feature_mode}_mw{market_cap:g}",
                    family=spec.family,
                    alpha=spec.alpha,
                    use_positive_weight=spec.use_positive_weight,
                    learning_rate=spec.learning_rate,
                    max_leaf_nodes=spec.max_leaf_nodes,
                    l2_regularization=spec.l2_regularization,
                    feature_mode=feature_mode,
                    market_weight_cap=market_cap,
                )
            )
        for spec in hgb_specs:
            variants.append(
                ModelSpec(
                    name=f"{spec.name}_{feature_mode}_mw{market_cap:g}",
                    family=spec.family,
                    alpha=spec.alpha,
                    use_positive_weight=spec.use_positive_weight,
                    learning_rate=spec.learning_rate,
                    max_leaf_nodes=spec.max_leaf_nodes,
                    l2_regularization=spec.l2_regularization,
                    feature_mode=feature_mode,
                    market_weight_cap=market_cap,
                )
            )
    return variants


def _objective_value_variants(
    base_specs: list[ModelSpec],
    *,
    include_hgb: bool,
    limit: int,
) -> list[ModelSpec]:
    variants: list[ModelSpec] = []

    # These are deliberately fundamental-only probability models. The market
    # blend is optimized inside calibrate_and_blend, so we do not retrain the
    # same base model just to test another odds weight cap.
    for alpha in (1e-3, 3e-4, 1e-4, 3e-5, 1e-5, 3e-6):
        for weighted in (False, True):
            variants.append(
                ModelSpec(
                    name=(
                        f"sgd_{'weighted' if weighted else 'unweighted'}_"
                        f"alpha_{alpha:g}_fundamental"
                    ),
                    family="sgd",
                    alpha=alpha,
                    use_positive_weight=weighted,
                    feature_mode="fundamental",
                )
            )

    if include_hgb:
        hgb_grid = [
            (0.03, 15, 0.03, False),
            (0.03, 31, 0.03, True),
            (0.04, 31, 0.01, False),
            (0.04, 63, 0.01, True),
            (0.05, 15, 0.08, False),
            (0.05, 31, 0.03, True),
            (0.06, 31, 0.08, False),
            (0.06, 63, 0.03, True),
            (0.08, 15, 0.12, False),
            (0.08, 31, 0.12, True),
            (0.10, 15, 0.18, False),
            (0.10, 31, 0.18, True),
            (0.12, 15, 0.24, False),
            (0.12, 31, 0.24, True),
            (0.03, 63, 0.08, False),
            (0.05, 63, 0.12, True),
            (0.02, 31, 0.03, False),
            (0.02, 63, 0.03, True),
        ]
        for index, (learning_rate, leaves, l2, weighted) in enumerate(hgb_grid, start=1):
            variants.append(
                ModelSpec(
                    name=(
                        f"hgb_{index:02d}_lr{learning_rate:g}_leaf{leaves}_"
                        f"l2{l2:g}_{'weighted' if weighted else 'unweighted'}_fundamental"
                    ),
                    family="hgb",
                    use_positive_weight=weighted,
                    learning_rate=learning_rate,
                    max_leaf_nodes=leaves,
                    l2_regularization=l2,
                    feature_mode="fundamental",
                )
            )
    return variants[:limit]


def model_specs(include_hgb: bool, zoo_profile: str = "default") -> list[ModelSpec]:
    specs = [
        ModelSpec("sgd_weighted_alpha_1e-4", "sgd", alpha=1e-4, use_positive_weight=True),
        ModelSpec("sgd_weighted_alpha_3e-5", "sgd", alpha=3e-5, use_positive_weight=True),
        ModelSpec("sgd_weighted_alpha_1e-5", "sgd", alpha=1e-5, use_positive_weight=True),
        ModelSpec("sgd_unweighted_alpha_1e-4", "sgd", alpha=1e-4, use_positive_weight=False),
        ModelSpec("sgd_unweighted_alpha_3e-5", "sgd", alpha=3e-5, use_positive_weight=False),
        ModelSpec("sgd_unweighted_alpha_3e-4", "sgd", alpha=3e-4, use_positive_weight=False),
    ]
    if include_hgb:
        specs.extend(
            [
                ModelSpec("hgb_numeric_weighted_balanced", "hgb", use_positive_weight=True, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=0.03),
                ModelSpec("hgb_numeric_weighted_deep", "hgb", use_positive_weight=True, learning_rate=0.04, max_leaf_nodes=63, l2_regularization=0.01),
                ModelSpec("hgb_numeric_unweighted_value", "hgb", use_positive_weight=False, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=0.08),
                ModelSpec("hgb_numeric_unweighted_compact", "hgb", use_positive_weight=False, learning_rate=0.08, max_leaf_nodes=15, l2_regularization=0.12),
            ]
        )
    if zoo_profile == "jra30":
        return _jra30_variants(specs, include_hgb=include_hgb)[:30]
    if zoo_profile == "objective30":
        return _objective_value_variants(specs, include_hgb=include_hgb, limit=30)
    if zoo_profile == "objective50":
        return _objective_value_variants(specs, include_hgb=include_hgb, limit=50)
    return specs


def load_holdout_frame(train_csv: Path, holdout_csv: Path) -> pd.DataFrame:
    print(f"[load] train_csv={train_csv}", flush=True)
    train = load_training_frame(train_csv)
    print(f"[load] holdout_csv={holdout_csv}", flush=True)
    holdout = load_training_frame(holdout_csv)
    print(f"[prepare] rows train={len(train)} holdout={len(holdout)}", flush=True)
    frame = pd.concat([train, holdout], ignore_index=True, sort=False)
    frame = prepare_frame(frame)
    frame["finish_position"] = pd.to_numeric(frame["finish_position"], errors="coerce")
    frame["is_top2"] = (frame["finish_position"] <= 2).astype("int8")
    print(
        f"[prepare] done rows={len(frame)} races={frame['race_id'].nunique()} columns={len(frame.columns)}",
        flush=True,
    )
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


def fallback_market_time_split(
    frame: pd.DataFrame,
    market: str,
    *,
    fit_fraction: float = 0.70,
    calibration_fraction: float = 0.15,
) -> tuple[pd.Index, pd.Index, pd.Index]:
    market_frame = frame[inferred_market(frame) == market].copy()
    races = (
        market_frame[["race_id", "race_date"]]
        .drop_duplicates()
        .sort_values(["race_date", "race_id"])
    )
    if len(races) < 30:
        return pd.Index([]), pd.Index([]), pd.Index([])
    race_ids = races["race_id"].tolist()
    fit_cut = max(1, int(len(race_ids) * fit_fraction))
    calibration_cut = max(fit_cut + 1, int(len(race_ids) * (fit_fraction + calibration_fraction)))
    fit_ids = set(race_ids[:fit_cut])
    calibration_ids = set(race_ids[fit_cut:calibration_cut])
    holdout_ids = set(race_ids[calibration_cut:])
    return (
        market_frame.index[market_frame["race_id"].isin(fit_ids)],
        market_frame.index[market_frame["race_id"].isin(calibration_ids)],
        market_frame.index[market_frame["race_id"].isin(holdout_ids)],
    )


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


def single_model_rank_metrics(
    model: CalibratedBlendModel,
    frame: pd.DataFrame,
    holdout_index: pd.Index,
) -> dict[str, Any]:
    holdout = frame.loc[holdout_index].copy()
    if holdout.empty:
        return {
            "races": 0,
            "winner_top1_rate": 0.0,
            "winner_in_top3_rate": 0.0,
            "top3_exact_set_rate": 0.0,
            "market_dependency": {},
        }
    holdout["candidate_score"] = np.clip(model.predict_positive(holdout), 0, 1)
    race_rows: list[dict[str, Any]] = []
    for race_id, race in holdout.groupby("race_id", sort=False):
        ordered = race.sort_values("candidate_score", ascending=False)
        winner = race.loc[race["finish_position"] == 1]
        top3 = set(race.loc[race["finish_position"] <= 3, "runner_number"].astype(int).tolist())
        predicted_winner = int(ordered.iloc[0]["runner_number"])
        predicted_top3 = set(ordered.head(3)["runner_number"].astype(int).tolist())
        race_rows.append(
            {
                "race_id": str(race_id),
                "winner_top1": int(
                    not winner.empty and predicted_winner == int(winner.iloc[0]["runner_number"])
                ),
                "winner_in_top3": int(
                    not winner.empty and int(winner.iloc[0]["runner_number"]) in predicted_top3
                ),
                "top3_exact_set": int(bool(top3) and predicted_top3 == top3),
            }
        )
    race_metrics = pd.DataFrame(race_rows)
    return {
        "races": int(len(race_metrics)),
        "winner_top1_rate": float(race_metrics["winner_top1"].mean()),
        "winner_in_top3_rate": float(race_metrics["winner_in_top3"].mean()),
        "top3_exact_set_rate": float(race_metrics["top3_exact_set"].mean()),
        "market_dependency": market_dependency_metrics(holdout, "candidate_score"),
    }


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
    feature_mode: str,
    removed_market_features: list[str],
) -> tuple[CalibratedBlendModel, dict[str, Any]]:
    fit = frame.loc[fit_index]
    calibration = frame.loc[calibration_index]
    train_positive_rate = float(fit[target].astype(int).mean())
    positive_weight = positive_class_weight(fit[target])

    if spec.family == "hgb":
        active_features = numeric_features
        base_model = build_hgb_pipeline(spec, numeric_features, positive_weight, seed, max_iter)
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
        "feature_mode": feature_mode,
        "features": active_features,
        "removed_market_features": removed_market_features,
        "market_weight_cap": market_weight_cap,
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
        "rank_holdout_2026": single_model_rank_metrics(model, frame, holdout_index),
    }
    return model, metrics


def model_selection_utility(
    item: dict[str, Any],
    *,
    favorite_rate_cap: float,
    favorite_penalty: float,
) -> dict[str, float]:
    rank = item.get("rank_holdout_2026", {})
    market_dependency = rank.get("market_dependency", {}) if isinstance(rank, dict) else {}
    target = str(item.get("target") or "")
    hit_score = (
        rank.get("winner_top1_rate", 0)
        if target == "is_win"
        else rank.get("winner_in_top3_rate", 0)
    )
    favorite_rate = market_dependency.get("predicted_top1_favorite_rate")
    favorite_value = float(favorite_rate) if favorite_rate is not None else 1.0
    market_favorite_hit = market_dependency.get("market_favorite_win_rate")
    market_favorite_hit_value = (
        float(market_favorite_hit) if market_favorite_hit is not None and target == "is_win" else 0.0
    )
    favorite_excess = max(0.0, favorite_value - favorite_rate_cap)
    hit_shortfall = max(0.0, market_favorite_hit_value - float(hit_score or 0))
    ece = float(item["holdout_2026"]["calibration"]["ece"])
    utility = (
        float(hit_score or 0)
        - favorite_excess * favorite_penalty
        - hit_shortfall * 0.28
        - ece * 0.04
    )
    return {
        "hit_score": float(hit_score or 0),
        "favorite_rate": favorite_value,
        "market_favorite_hit_rate": market_favorite_hit_value,
        "favorite_excess": favorite_excess,
        "hit_shortfall_vs_market_favorite": hit_shortfall,
        "utility": utility,
    }


def choose_best(
    candidates: list[dict[str, Any]],
    *,
    favorite_rate_cap: float,
    favorite_penalty: float,
) -> dict[str, Any]:
    def key(item: dict[str, Any]) -> tuple[float, float, float, float]:
        selection = model_selection_utility(
            item,
            favorite_rate_cap=favorite_rate_cap,
            favorite_penalty=favorite_penalty,
        )
        return (
            selection["utility"],
            -selection["favorite_rate"],
            -item["holdout_2026"]["brier"],
            -item["holdout_2026"]["calibration"]["ece"],
        )

    best = max(
        candidates,
        key=key,
    )
    best["selection_policy"] = model_selection_utility(
        best,
        favorite_rate_cap=favorite_rate_cap,
        favorite_penalty=favorite_penalty,
    )
    best["selection_policy"].update(
        {
            "favorite_rate_cap": float(favorite_rate_cap),
            "favorite_penalty": float(favorite_penalty),
        }
    )
    return best


def sort_candidate_key(
    item: dict[str, Any],
    *,
    favorite_rate_cap: float,
    favorite_penalty: float,
) -> tuple[float, float, float, float]:
    selection = model_selection_utility(
        item,
        favorite_rate_cap=favorite_rate_cap,
        favorite_penalty=favorite_penalty,
    )
    return (
        selection["utility"],
        -selection["favorite_rate"],
        -item["holdout_2026"]["brier"],
        -item["holdout_2026"]["calibration"]["ece"],
    )


def legacy_choose_best(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    def key(item: dict[str, Any]) -> tuple[float, float, float, float]:
        rank = item.get("rank_holdout_2026", {})
        market_dependency = rank.get("market_dependency", {}) if isinstance(rank, dict) else {}
        target = str(item.get("target") or "")
        hit_score = (
            rank.get("winner_top1_rate", 0)
            if target == "is_win"
            else rank.get("winner_in_top3_rate", 0)
        )
        favorite_rate = market_dependency.get("predicted_top1_favorite_rate")
        favorite_penalty = float(favorite_rate) if favorite_rate is not None else 1.0
        return (
            -float(hit_score or 0),
            favorite_penalty,
            item["holdout_2026"]["brier"],
            item["holdout_2026"]["calibration"]["ece"],
        )

    return min(
        candidates,
        key=key,
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
    if feature_mode in {"fundamental", "anti_market"}:
        removed = [feature for feature in features if feature in MARKET_DIRECT_FEATURES]
        numeric_features = [
            feature for feature in numeric_features if feature not in MARKET_DIRECT_FEATURES
        ]
        features = [feature for feature in features if feature not in MARKET_DIRECT_FEATURES]
        return features, numeric_features, categorical_features, removed
    if feature_mode == "market_only":
        kept = [feature for feature in features if feature in MARKET_BASELINE_SUPPORT_FEATURES]
        numeric_features = [
            feature for feature in numeric_features if feature in MARKET_BASELINE_SUPPORT_FEATURES
        ]
        removed = [feature for feature in features if feature not in set(kept)]
        return kept, numeric_features, [], removed
    if feature_mode == "odds_rank_only":
        direct_odds = {
            "market_odds",
            "market_win_probability",
            "market_place_probability",
            "odds_delta",
            "ticket_pool_share",
        }
        removed = [feature for feature in features if feature in direct_odds]
        numeric_features = [feature for feature in numeric_features if feature not in direct_odds]
        features = [feature for feature in features if feature not in direct_odds]
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


ORDERED_BET_TYPES = {"exacta", "trifecta"}
TICKET_BET_TYPES = [
    "win",
    "bracket_quinella",
    "quinella",
    "wide",
    "exacta",
    "trio",
    "trifecta",
]


def selection_numbers(value: Any) -> tuple[int, ...]:
    return tuple(int(match) for match in re.findall(r"\d+", str(value or "")))


def normalized_ticket_key(bet_type: str, numbers: tuple[int, ...]) -> tuple[int, ...]:
    if bet_type in ORDERED_BET_TYPES:
        return numbers
    return tuple(sorted(numbers))


def race_payout_lookup(race: pd.DataFrame) -> dict[tuple[str, tuple[int, ...]], float]:
    raw_values = race.get("payouts_json")
    if raw_values is None or raw_values.empty:
        return {}
    raw = raw_values.dropna()
    if raw.empty:
        return {}
    try:
        items = json.loads(str(raw.iloc[0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(items, list):
        return {}
    lookup: dict[tuple[str, tuple[int, ...]], float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        bet_type = str(item.get("bet_type") or item.get("betType") or "")
        numbers = selection_numbers(item.get("selection"))
        payout = float(pd.to_numeric(item.get("payout_yen") or item.get("payoutYen"), errors="coerce") or 0)
        if bet_type and numbers and payout > 0:
            lookup[(bet_type, normalized_ticket_key(bet_type, numbers))] = payout
    return lookup


def ordered_runners_for_ticket(race: pd.DataFrame, score_column: str) -> list[dict[str, int | float]]:
    ordered = race.sort_values(score_column, ascending=False)
    rows: list[dict[str, int | float]] = []
    for _, row in ordered.iterrows():
        number = int(row["runner_number"])
        gate = int(row["bracket"]) if not pd.isna(row.get("bracket")) else min(max((number + 1) // 2, 1), 8)
        rows.append({"number": number, "gate": gate, "score": float(row[score_column])})
    return rows


def unique_gates(rows: list[dict[str, int | float]]) -> list[int]:
    gates: list[int] = []
    for row in rows:
        gate = int(row["gate"])
        if gate not in gates:
            gates.append(gate)
    return gates


def strategy_int(strategy: str, prefix: str, default: int) -> int:
    if not strategy.startswith(prefix):
        return default
    try:
        return int(strategy.removeprefix(prefix).split("_", 1)[0])
    except (TypeError, ValueError):
        return default


def ticket_strategy_family(strategy: str) -> str:
    if strategy.startswith("formation_"):
        return "formation"
    if strategy.startswith("box_"):
        return "box"
    if "multi" in strategy:
        return "multi"
    if strategy.startswith("two_axis_"):
        return "two_axis"
    if "axis" in strategy:
        return "axis"
    if strategy.startswith("top"):
        return strategy
    return strategy


def ticket_strategy_label(bet_type: str, strategy: str) -> str:
    if strategy.startswith("top"):
        count = strategy_int(strategy, "top", 2)
        return "単勝" if count == 1 else f"単勝{count}点"
    if strategy.startswith("axis_multi_"):
        count = strategy_int(strategy, "axis_multi_", 4)
        points = count * 2 if bet_type == "exacta" else math.comb(count, 2) * 6
        return f"1頭軸マルチ{points}点"
    if strategy.startswith("axis_"):
        count = strategy_int(strategy, "axis_", 4)
        return f"軸流し{count}点"
    if strategy.startswith("box_"):
        count = strategy_int(strategy, "box_", 4)
        return f"{count}頭BOX"
    if strategy.startswith("one_axis_"):
        count = strategy_int(strategy, "one_axis_", 5)
        return f"1頭軸流し{math.comb(count, 2)}点"
    if strategy.startswith("two_axis_multi_"):
        count = strategy_int(strategy, "two_axis_multi_", 3)
        return f"2頭軸マルチ{count * 6}点"
    if strategy.startswith("two_axis_"):
        count = strategy_int(strategy, "two_axis_", 3)
        return f"2頭軸流し{count}点"
    if strategy.startswith("first_axis_"):
        count = strategy_int(strategy, "first_axis_", 4)
        return f"1着軸流し{count * (count - 1)}点"
    if strategy.startswith("formation_"):
        shape = strategy.removeprefix("formation_").replace("_", "-")
        return f"フォーメーション{shape}"
    return strategy


def ticket_entries_for_strategy(
    rows: list[dict[str, int | float]],
    bet_type: str,
    strategy: str,
) -> list[tuple[int, ...]]:
    numbers = [int(row["number"]) for row in rows]
    gates = unique_gates(rows)
    if bet_type == "win":
        count = strategy_int(strategy, "top", 2)
        return [(number,) for number in numbers[: max(count, 1)]]
    if bet_type == "bracket_quinella":
        if strategy.startswith("box_"):
            count = strategy_int(strategy, "box_", 4)
            return [tuple(sorted(pair)) for pair in combinations(gates[:count], 2)]
        opponent_count = strategy_int(strategy, "axis_", 4)
        axis = gates[0] if gates else 0
        return [tuple(sorted((axis, gate))) for gate in gates[1 : 1 + opponent_count] if gate != axis]
    if bet_type in {"quinella", "wide"}:
        if strategy.startswith("box_"):
            count = strategy_int(strategy, "box_", 4)
            return [tuple(sorted(pair)) for pair in combinations(numbers[:count], 2)]
        opponent_count = strategy_int(strategy, "axis_", 5)
        axis = numbers[0] if numbers else 0
        return [tuple(sorted((axis, number))) for number in numbers[1 : 1 + opponent_count]]
    if bet_type == "exacta":
        if strategy.startswith("box_"):
            count = strategy_int(strategy, "box_", 4)
            return [tuple(pair) for pair in permutations(numbers[:count], 2)]
        axis = numbers[0] if numbers else 0
        opponent_count = strategy_int(
            strategy,
            "axis_multi_",
            strategy_int(strategy, "axis_", 4),
        )
        opponents = numbers[1 : 1 + opponent_count]
        entries = [(axis, number) for number in opponents]
        if strategy.startswith("axis_multi_"):
            entries += [(number, axis) for number in opponents]
        return entries
    if bet_type == "trio":
        if strategy.startswith("box_"):
            count = strategy_int(strategy, "box_", 5)
            return [tuple(sorted(combo)) for combo in combinations(numbers[:count], 3)]
        axis = numbers[0] if numbers else 0
        if strategy.startswith("two_axis_"):
            opponent_count = strategy_int(strategy, "two_axis_", 3)
            if len(numbers) < 2:
                return []
            return [tuple(sorted((numbers[0], numbers[1], number))) for number in numbers[2 : 2 + opponent_count]]
        opponent_count = strategy_int(strategy, "one_axis_", 5)
        return [tuple(sorted((axis, *pair))) for pair in combinations(numbers[1 : 1 + opponent_count], 2)]
    if bet_type == "trifecta":
        if strategy.startswith("box_"):
            count = strategy_int(strategy, "box_", 4)
            return [tuple(combo) for combo in permutations(numbers[:count], 3)]
        if strategy.startswith("formation_"):
            parts = strategy.removeprefix("formation_").split("_")
            first_count, second_count, third_count = (int(parts[0]), int(parts[1]), int(parts[2]))
            first = numbers[:first_count]
            second = numbers[:second_count]
            third = numbers[:third_count]
            return [
                (a, b, c)
                for a in first
                for b in second
                for c in third
                if len({a, b, c}) == 3
            ]
        axis = numbers[0] if numbers else 0
        if strategy.startswith("two_axis_multi_"):
            opponent_count = strategy_int(strategy, "two_axis_multi_", 3)
            if len(numbers) < 2:
                return []
            axis1, axis2 = numbers[0], numbers[1]
            return [
                combo
                for opponent in numbers[2 : 2 + opponent_count]
                for combo in permutations((axis1, axis2, opponent), 3)
            ]
        if strategy.startswith("first_axis_"):
            opponent_count = strategy_int(strategy, "first_axis_", 4)
            return [(axis, *pair) for pair in permutations(numbers[1 : 1 + opponent_count], 2)]
        opponent_count = strategy_int(strategy, "axis_multi_", 4)
        return [
            combo
            for pair in permutations(numbers[1 : 1 + opponent_count], 2)
            for combo in ((axis, *pair), (pair[0], axis, pair[1]), (*pair, axis))
        ]
    return []


def ticket_strategy_metrics(
    frame: pd.DataFrame,
    holdout_index: pd.Index,
    models: dict[str, CalibratedBlendModel],
) -> dict[str, Any]:
    holdout = frame.loc[holdout_index].copy()
    if holdout.empty:
        return {"status": "skipped", "reason": "empty holdout"}

    p_win = np.clip(models["is_win"].predict_positive(holdout), 0, 1)
    p_top2 = np.maximum(np.clip(models["is_top2"].predict_positive(holdout), 0, 1), p_win)
    p_top3 = np.maximum(np.clip(models["is_place"].predict_positive(holdout), 0, 1), p_top2)
    holdout["ticket_win_score"] = p_win
    holdout["ticket_rank_score"] = p_win + (p_top2 - p_win) * 0.42 + (p_top3 - p_top2) * 0.18
    holdout["ticket_place_score"] = p_top3

    selectors = {
        "win_model": "ticket_win_score",
        "rank_model": "ticket_rank_score",
        "place_model": "ticket_place_score",
    }
    strategies = {
        "win": ["top1", "top2", "top3"],
        "bracket_quinella": ["axis_2", "axis_3", "axis_4", "box_3", "box_4"],
        "quinella": ["axis_2", "axis_3", "axis_5", "box_3", "box_4", "box_5"],
        "wide": ["axis_2", "axis_3", "axis_5", "box_3", "box_4", "box_5"],
        "exacta": ["axis_2", "axis_3", "axis_multi_2", "axis_multi_3", "axis_multi_4", "box_3", "box_4"],
        "trio": ["one_axis_3", "one_axis_4", "one_axis_5", "two_axis_2", "two_axis_3", "box_4", "box_5", "box_6"],
        "trifecta": [
            "first_axis_2",
            "first_axis_3",
            "first_axis_5",
            "axis_multi_2",
            "axis_multi_3",
            "axis_multi_4",
            "two_axis_multi_2",
            "two_axis_multi_3",
            "formation_1_3_5",
            "formation_2_3_5",
            "formation_2_4_6",
            "box_3",
            "box_4",
            "box_5",
        ],
    }

    results: dict[str, list[dict[str, Any]]] = {bet_type: [] for bet_type in TICKET_BET_TYPES}
    by_profile_results: dict[str, dict[str, list[dict[str, Any]]]] = {
        bucket: {bet_type: [] for bet_type in TICKET_BET_TYPES}
        for bucket in ("stable", "balanced", "chaotic")
    }

    def ticket_profile_bucket(rows: list[dict[str, int | float]]) -> str:
        scores = [max(float(row["score"]), 1e-9) for row in rows]
        if len(scores) < 3:
            return "balanced"
        total = sum(scores)
        shares = [score / total for score in scores] if total > 0 else []
        entropy = -sum(value * np.log(value) for value in shares) / np.log(len(shares))
        top_share = shares[0]
        gap = shares[0] - shares[1]
        if top_share >= 0.24 and gap >= 0.055 and entropy < 0.82:
            return "stable"
        if top_share < 0.17 or gap < 0.025 or entropy >= 0.93:
            return "chaotic"
        return "balanced"

    def empty_stat() -> dict[str, float]:
        return {"races": 0, "hits": 0, "stake": 0.0, "payout": 0.0, "tickets": 0}

    def finalize_stat(selector_name: str, strategy: str, stat: dict[str, float]) -> dict[str, Any]:
        races = int(stat["races"])
        hits = int(stat["hits"])
        stake = float(stat["stake"])
        payout = float(stat["payout"])
        avg_tickets = float(stat["tickets"]) / races if races > 0 else 0.0
        roi = payout / stake if stake > 0 else 0.0
        hit_rate = hits / races if races > 0 else 0.0
        profit_rate = roi - 1.0
        clipped_profit = min(max(profit_rate, -1.0), 3.0)
        utility = clipped_profit * 0.58 + hit_rate * 0.34 - min(avg_tickets / 60, 1.0) * 0.08
        return {
            "selector": selector_name,
            "strategy": strategy,
            "strategy_label": ticket_strategy_label(bet_type, strategy),
            "strategy_family": ticket_strategy_family(strategy),
            "races": races,
            "hits": hits,
            "hit_rate": round(float(hit_rate), 6),
            "stake": int(stake),
            "payout": int(payout),
            "roi": round(float(roi), 6),
            "avg_tickets": round(float(avg_tickets), 3),
            "utility": round(float(utility), 6),
        }

    race_cache: dict[str, list[tuple[list[dict[str, int | float]], str, dict[tuple[str, tuple[int, ...]], float]]]] = {}
    for selector_name, score_column in selectors.items():
        cached_races: list[tuple[list[dict[str, int | float]], str, dict[tuple[str, tuple[int, ...]], float]]] = []
        for _, race in holdout.groupby("race_id", sort=False):
            lookup = race_payout_lookup(race)
            if not lookup:
                continue
            ordered_rows = ordered_runners_for_ticket(race, score_column)
            cached_races.append((ordered_rows, ticket_profile_bucket(ordered_rows), lookup))
        race_cache[selector_name] = cached_races

    for bet_type in TICKET_BET_TYPES:
        for selector_name in selectors:
            for strategy in strategies[bet_type]:
                total_stat = empty_stat()
                profile_stats = {bucket: empty_stat() for bucket in by_profile_results}
                for ordered_rows, bucket, lookup in race_cache[selector_name]:
                    entries = ticket_entries_for_strategy(
                        ordered_rows,
                        bet_type,
                        strategy,
                    )
                    entries = list(dict.fromkeys(entries))
                    if not entries:
                        continue
                    total_stat["races"] += 1
                    total_stat["tickets"] += len(entries)
                    total_stat["stake"] += len(entries) * 100
                    profile_stats[bucket]["races"] += 1
                    profile_stats[bucket]["tickets"] += len(entries)
                    profile_stats[bucket]["stake"] += len(entries) * 100
                    race_payout = 0.0
                    for entry in entries:
                        race_payout += lookup.get((bet_type, normalized_ticket_key(bet_type, entry)), 0.0)
                    total_stat["payout"] += race_payout
                    profile_stats[bucket]["payout"] += race_payout
                    if race_payout > 0:
                        total_stat["hits"] += 1
                        profile_stats[bucket]["hits"] += 1
                results[bet_type].append(finalize_stat(selector_name, strategy, total_stat))
                for bucket, stat in profile_stats.items():
                    by_profile_results[bucket][bet_type].append(finalize_stat(selector_name, strategy, stat))

    best = {
        bet_type: max(
            rows,
            key=lambda row: (row["utility"], row["hit_rate"], row["roi"], -row["avg_tickets"]),
        )
        for bet_type, rows in results.items()
        if rows
    }
    by_profile = {
        bucket: {
            bet_type: max(
                [row for row in rows if row["races"] > 0] or rows,
                key=lambda row: (row["utility"], row["hit_rate"], row["roi"], -row["avg_tickets"]),
            )
            for bet_type, rows in bucket_results.items()
            if rows
        }
        for bucket, bucket_results in by_profile_results.items()
    }
    return {
        "status": "ok",
        "unit_stake_yen": 100,
        "selection_note": "Each bet type is compared by selector model, ticket count, and strategy shape on the 2026 holdout. by_profile stores stable/balanced/chaotic race policies.",
        "best_by_bet_type": best,
        "by_profile": by_profile,
        "all": results,
        "all_by_profile": by_profile_results,
    }


def ticket_item_utility(item: dict[str, Any], *, bet_type: str) -> float:
    roi = float(item.get("roi") or 0.0)
    hit_rate = float(item.get("hit_rate") or 0.0)
    avg_tickets = float(item.get("avg_tickets") or 0.0)
    races = int(item.get("races") or 0)
    if races <= 0:
        return -10.0

    # ROI is primary. A high hit rate can still lose after point count, so hit
    # rate is a stability term and point count is a mild penalty.
    exotic_bonus = 0.0
    if bet_type in {"trio", "trifecta", "exacta"}:
        exotic_bonus = max(0.0, roi - 0.82) * 0.24
    return (
        (roi - 0.72) * 0.78
        + hit_rate * 0.20
        + exotic_bonus
        - min(avg_tickets / 72.0, 1.0) * 0.08
    )


def ticket_policy_utility(ticket_policy: dict[str, Any], rank_metrics: dict[str, Any]) -> dict[str, Any]:
    best_by_bet_type = ticket_policy.get("best_by_bet_type", {})
    by_profile = ticket_policy.get("by_profile", {})
    bet_weights = {
        "win": 0.25,
        "bracket_quinella": 0.28,
        "quinella": 0.42,
        "wide": 0.34,
        "exacta": 0.54,
        "trio": 0.68,
        "trifecta": 0.78,
    }
    profile_weights = {"stable": 0.22, "balanced": 0.46, "chaotic": 0.32}

    total = 0.0
    details: dict[str, float] = {}
    for bet_type, weight in bet_weights.items():
        item = best_by_bet_type.get(bet_type)
        if not item:
            continue
        value = ticket_item_utility(item, bet_type=bet_type)
        details[bet_type] = round(value, 6)
        total += weight * value

    profile_total = 0.0
    for profile, profile_weight in profile_weights.items():
        profile_items = by_profile.get(profile, {})
        if not profile_items:
            continue
        profile_score = 0.0
        profile_weight_sum = 0.0
        for bet_type, weight in bet_weights.items():
            item = profile_items.get(bet_type)
            if not item:
                continue
            profile_score += weight * ticket_item_utility(item, bet_type=bet_type)
            profile_weight_sum += weight
        if profile_weight_sum > 0:
            profile_total += profile_weight * (profile_score / profile_weight_sum)

    market_dependency = rank_metrics.get("market_dependency", {})
    favorite_rate = market_dependency.get("predicted_top1_favorite_rate")
    favorite_penalty = max(0.0, float(favorite_rate or 0.0) - 0.86) * 0.10
    top1_rate = float(rank_metrics.get("winner_top1_rate") or 0.0)
    top3_rate = float(rank_metrics.get("winner_in_top3_rate") or 0.0)
    rank_bonus = top1_rate * 0.06 + top3_rate * 0.04
    utility = total + profile_total * 0.55 + rank_bonus - favorite_penalty
    return {
        "utility": round(float(utility), 6),
        "overall_ticket_score": round(float(total), 6),
        "profile_ticket_score": round(float(profile_total), 6),
        "rank_bonus": round(float(rank_bonus), 6),
        "favorite_penalty": round(float(favorite_penalty), 6),
        "bet_type_scores": details,
    }


def choose_models_by_ticket_policy(
    all_metrics: dict[str, list[dict[str, Any]]],
    trained_models: dict[str, dict[str, CalibratedBlendModel]],
    frame: pd.DataFrame,
    holdout_index: pd.Index,
    *,
    favorite_rate_cap: float,
    favorite_penalty: float,
    top_n: int,
) -> dict[str, Any]:
    top_candidates: dict[str, list[dict[str, Any]]] = {}
    for target, metrics in all_metrics.items():
        ranked = sorted(
            metrics,
            key=lambda item: sort_candidate_key(
                item,
                favorite_rate_cap=favorite_rate_cap,
                favorite_penalty=favorite_penalty,
            ),
            reverse=True,
        )
        for item in ranked:
            item["selection_policy"] = model_selection_utility(
                item,
                favorite_rate_cap=favorite_rate_cap,
                favorite_penalty=favorite_penalty,
            )
            item["selection_policy"].update(
                {
                    "favorite_rate_cap": float(favorite_rate_cap),
                    "favorite_penalty": float(favorite_penalty),
                }
            )
        top_candidates[target] = ranked[: max(1, top_n)]

    best_bundle: dict[str, Any] | None = None
    combinations_checked = 0
    for win_item, top2_item, place_item in product(
        top_candidates["is_win"],
        top_candidates["is_top2"],
        top_candidates["is_place"],
    ):
        models = {
            "is_win": trained_models["is_win"][win_item["model"]],
            "is_top2": trained_models["is_top2"][top2_item["model"]],
            "is_place": trained_models["is_place"][place_item["model"]],
        }
        rank_metrics = rank_holdout_metrics(frame, holdout_index, models)
        ticket_policy = ticket_strategy_metrics(frame, holdout_index, models)
        utility = ticket_policy_utility(ticket_policy, rank_metrics)
        combinations_checked += 1
        if best_bundle is None or utility["utility"] > best_bundle["bundle_utility"]["utility"]:
            best_bundle = {
                "models": models,
                "best_metrics": {
                    "is_win": win_item,
                    "is_top2": top2_item,
                    "is_place": place_item,
                },
                "rank_holdout_2026": rank_metrics,
                "ticket_policy": ticket_policy,
                "bundle_utility": utility,
                "combinations_checked": combinations_checked,
            }

    if best_bundle is None:
        raise ValueError("ticket bundle selection produced no candidates")
    best_bundle["bundle_selection"] = {
        "mode": "ticket",
        "top_n_per_target": int(max(1, top_n)),
        "combinations_checked": int(combinations_checked),
        "candidate_models": {
            target: [item["model"] for item in candidates]
            for target, candidates in top_candidates.items()
        },
    }
    return best_bundle


def train_best_bundle(
    frame: pd.DataFrame,
    fit_index: pd.Index,
    calibration_index: pd.Index,
    holdout_index: pd.Index,
    args: argparse.Namespace,
) -> dict[str, Any]:
    base_features, base_numeric_features, base_categorical_features = select_training_features(
        frame,
        fit_index,
    )

    all_metrics: dict[str, list[dict[str, Any]]] = {target: [] for target in TARGETS}
    trained_models: dict[str, dict[str, CalibratedBlendModel]] = {target: {} for target in TARGETS}
    removed_features_union: set[str] = set()
    specs = model_specs(args.include_hgb, args.zoo_profile)
    for target in TARGETS:
        for spec in specs:
            feature_mode = spec.feature_mode if spec.feature_mode != "global" else args.feature_mode
            features, numeric_features, categorical_features, removed_features = apply_feature_mode(
                base_features.copy(),
                base_numeric_features.copy(),
                base_categorical_features.copy(),
                feature_mode,
            )
            removed_features_union.update(removed_features)
            candidate_market_cap = (
                args.market_weight_cap
                if spec.market_weight_cap is None
                else float(spec.market_weight_cap)
            )
            print(
                f"[train] target={target} model={spec.name} family={spec.family} "
                f"feature_mode={feature_mode} market_cap={candidate_market_cap:g}",
                flush=True,
            )
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
                candidate_market_cap,
                args.market_weight_step,
                feature_mode,
                removed_features,
            )
            all_metrics[target].append(metrics)
            trained_models[target][spec.name] = model

    if args.bundle_selection == "ticket":
        bundle_choice = choose_models_by_ticket_policy(
            all_metrics,
            trained_models,
            frame,
            holdout_index,
            favorite_rate_cap=args.favorite_rate_cap,
            favorite_penalty=args.favorite_penalty,
            top_n=args.bundle_top_n,
        )
        best_metrics = bundle_choice["best_metrics"]
        best_models = bundle_choice["models"]
        rank_metrics = bundle_choice["rank_holdout_2026"]
        ticket_policy = bundle_choice["ticket_policy"]
        bundle_selection = bundle_choice["bundle_selection"]
        bundle_utility = bundle_choice["bundle_utility"]
    else:
        best_metrics = {
            target: choose_best(
                metrics,
                favorite_rate_cap=args.favorite_rate_cap,
                favorite_penalty=args.favorite_penalty,
            )
            for target, metrics in all_metrics.items()
        }
        best_models = {
            target: trained_models[target][metrics["model"]]
            for target, metrics in best_metrics.items()
        }
        rank_metrics = rank_holdout_metrics(frame, holdout_index, best_models)
        ticket_policy = ticket_strategy_metrics(frame, holdout_index, best_models)
        bundle_selection = {
            "mode": "rank",
            "top_n_per_target": None,
            "combinations_checked": 1,
        }
        bundle_utility = ticket_policy_utility(ticket_policy, rank_metrics)
    return {
        "targets": all_metrics,
        "best": best_metrics,
        "models": best_models,
        "rank_holdout_2026": rank_metrics,
        "ticket_policy": ticket_policy,
        "bundle_selection": bundle_selection,
        "bundle_utility": bundle_utility,
        "risk_router": risk_router(best_metrics),
        "numeric_features": base_numeric_features,
        "categorical_features": base_categorical_features,
        "features": base_features,
        "removed_market_features": sorted(removed_features_union),
        "model_candidate_count": len(specs),
        "probability_model_contract": {
            "feature_mode": args.feature_mode,
            "objective_only_probability": args.feature_mode in {"fundamental", "anti_market"},
            "market_features_used_only_for_blending": args.feature_mode in {"fundamental", "anti_market"},
            "removed_market_features": sorted(removed_features_union),
        },
    }


def compact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    best = {}
    for target, metrics in payload["best"].items():
        holdout = metrics["holdout_2026"]
        rank = metrics.get("rank_holdout_2026", {})
        dependency = rank.get("market_dependency", {}) if isinstance(rank, dict) else {}
        best[target] = {
            "model": metrics["model"],
            "feature_mode": metrics.get("feature_mode"),
            "market_weight_cap": metrics.get("market_weight_cap"),
            "market_ensemble_weight": metrics["market_ensemble_weight"],
            "holdout_brier": round(float(holdout["brier"]), 6),
            "holdout_brier_vs_market": holdout["brier_vs_market"],
            "holdout_auc": round(float(holdout.get("auc") or 0), 6),
            "holdout_auc_vs_market": holdout["auc_vs_market"],
            "holdout_ece": holdout["calibration"]["ece"],
            "winner_top1_rate": round(float(rank.get("winner_top1_rate") or 0), 6),
            "winner_in_top3_rate": round(float(rank.get("winner_in_top3_rate") or 0), 6),
            "predicted_top1_favorite_rate": dependency.get("predicted_top1_favorite_rate"),
            "selection_policy": metrics.get("selection_policy", {}),
        }
    return {
        "trained_at": payload["trained_at"],
        "split": payload["split"],
        "best": best,
        "rank_holdout_2026": payload["rank_holdout_2026"],
        "ticket_policy": {
            "status": payload.get("ticket_policy", {}).get("status"),
            "best_by_bet_type": payload.get("ticket_policy", {}).get("best_by_bet_type", {}),
            "by_profile": payload.get("ticket_policy", {}).get("by_profile", {}),
        },
        "bundle_selection": payload.get("bundle_selection", {}),
        "bundle_utility": payload.get("bundle_utility", {}),
        "risk_router": payload["risk_router"],
        "segment_metrics": {
            market: metrics.get("rank_holdout_2026", {})
            for market, metrics in payload.get("segment_metrics", {}).items()
        },
        "model_candidate_count": payload.get("model_candidate_count"),
        "probability_model_contract": payload.get("probability_model_contract", {}),
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
    parser.add_argument(
        "--skip-hgb",
        action="store_false",
        dest="include_hgb",
        help="Skip the slower HistGradientBoosting candidates. By default the full 10-model zoo is trained.",
    )
    parser.set_defaults(include_hgb=True)
    parser.add_argument(
        "--feature-mode",
        choices=["all", "objective", "fundamental", "anti_market", "odds_rank_only", "market_only"],
        default="fundamental",
        help=(
            "fundamental removes odds/popularity features from the probability model; "
            "market odds are blended only after calibration."
        ),
    )
    parser.add_argument(
        "--zoo-profile",
        choices=["default", "jra30", "objective30", "objective50"],
        default="default",
        help=(
            "objective30/objective50 compare fundamental-only probability models "
            "with different model families and hyperparameters."
        ),
    )
    parser.add_argument(
        "--market-weight-cap",
        type=float,
        default=0.2,
        help="Upper limit for blending calibrated model probabilities with market probabilities.",
    )
    parser.add_argument("--market-weight-step", type=float, default=0.05)
    parser.add_argument(
        "--favorite-rate-cap",
        type=float,
        default=0.74,
        help="Model selection starts penalizing candidates whose AI top pick is the market favorite too often.",
    )
    parser.add_argument(
        "--favorite-penalty",
        type=float,
        default=0.36,
        help="Penalty strength applied to favorite-rate excess during model selection.",
    )
    parser.add_argument(
        "--bundle-selection",
        choices=["rank", "ticket"],
        default="rank",
        help=(
            "rank selects each target model by rank metrics; ticket also searches "
            "target-model combinations by bet-type strategy backtest utility."
        ),
    )
    parser.add_argument(
        "--bundle-top-n",
        type=int,
        default=3,
        help="Top candidates per target to combine when --bundle-selection=ticket.",
    )
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
    print(
        "[split] "
        f"fit_rows={len(fit_index)} calibration_rows={len(calibration_index)} "
        f"holdout_rows={len(holdout_index)}",
        flush=True,
    )
    bundle = train_best_bundle(frame, fit_index, calibration_index, holdout_index, args)
    segment_bundles: dict[str, dict[str, Any]] = {}
    if args.segment_by_market:
        for market in ("JRA", "NAR"):
            print(f"[segment] market={market}", flush=True)
            segment_fit = filter_index_by_market(frame, fit_index, market)
            segment_calibration = filter_index_by_market(frame, calibration_index, market)
            segment_holdout = filter_index_by_market(frame, holdout_index, market)
            if len(segment_fit) == 0 or len(segment_calibration) == 0 or len(segment_holdout) == 0:
                segment_fit, segment_calibration, segment_holdout = fallback_market_time_split(
                    frame,
                    market,
                )
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
        "favorite_rate_cap": args.favorite_rate_cap,
        "favorite_penalty": args.favorite_penalty,
        "zoo_profile": args.zoo_profile,
        "model_candidate_count": bundle["model_candidate_count"],
        "targets": bundle["targets"],
        "best": bundle["best"],
        "rank_holdout_2026": bundle["rank_holdout_2026"],
        "ticket_policy": bundle["ticket_policy"],
        "bundle_selection": bundle["bundle_selection"],
        "bundle_utility": bundle["bundle_utility"],
        "risk_router": bundle["risk_router"],
        "probability_model_contract": bundle["probability_model_contract"],
        "segment_metrics": {
            market: {
                "best": segment["best"],
                "rank_holdout_2026": segment["rank_holdout_2026"],
                "ticket_policy": segment["ticket_policy"],
                "bundle_selection": segment["bundle_selection"],
                "bundle_utility": segment["bundle_utility"],
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
                    "ticket_policy": segment["ticket_policy"],
                    "bundle_selection": segment["bundle_selection"],
                    "bundle_utility": segment["bundle_utility"],
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
        "ticket_policy": bundle["ticket_policy"],
        "bundle_selection": bundle["bundle_selection"],
        "bundle_utility": bundle["bundle_utility"],
        "probability_model_contract": bundle["probability_model_contract"],
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
