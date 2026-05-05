from __future__ import annotations

import numpy as np
import pandas as pd

from app.storage.tables import read_table, write_table


NUMERIC_CANDIDATES = [
    "market_odds",
    "speed",
    "stamina",
    "pace",
    "distance",
    "carried_weight",
    "days_since_last_run",
    "body_weight",
    "body_weight_diff",
    "field_size",
    "odds_rank",
    "jockey_win_rate",
    "trainer_win_rate",
]

CATEGORICAL_CANDIDATES = [
    "venue",
    "surface",
    "going",
    "weather",
    "jockey",
    "trainer",
    "running_style",
    "sex",
]


def build_runner_features(input_table: str = "runners.parquet", output_table: str = "runners_features.parquet"):
    df = read_table(input_table, kind="normalized").copy()

    if "market_odds" in df.columns:
        odds = pd.to_numeric(df["market_odds"], errors="coerce").replace(0, np.nan)
        df["implied_probability"] = (1.0 / odds).clip(0, 1)
        if "race_id" in df.columns:
            df["odds_rank"] = odds.groupby(df["race_id"]).rank(method="min", ascending=True)
    else:
        df["implied_probability"] = np.nan

    if "race_id" in df.columns:
        df["field_size"] = df.groupby("race_id")["race_id"].transform("size")

    for col in NUMERIC_CANDIDATES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    keep = []
    identity_cols = ["race_id", "race_date", "horse_id", "horse_name", "number", "finish_position", "is_win", "is_place"]
    for col in identity_cols + NUMERIC_CANDIDATES + CATEGORICAL_CANDIDATES + ["implied_probability"]:
        if col in df.columns and col not in keep:
            keep.append(col)

    feature_df = df[keep].copy()

    if "is_win" not in feature_df.columns and "finish_position" in feature_df.columns:
        feature_df["is_win"] = (pd.to_numeric(feature_df["finish_position"], errors="coerce") == 1).astype(int)

    if "is_place" not in feature_df.columns and "finish_position" in feature_df.columns:
        pos = pd.to_numeric(feature_df["finish_position"], errors="coerce")
        feature_df["is_place"] = (pos <= 3).astype(int)

    summary = write_table(feature_df, output_table, kind="features")
    return summary
