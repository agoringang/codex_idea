from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml_pipeline import (
    NUMERIC_COLUMNS,
    add_market_features,
    canonicalize_runner_columns,
)


EXTRA_COLUMNS = [
    "market_win_probability",
    "market_place_probability",
    "days_since_last_run",
    "avg_last3_speed",
    "jockey_win_rate",
    "trainer_win_rate",
    "horse_recent_win_rate",
    "horse_recent_place_rate",
    "horse_distance_place_rate",
    "horse_surface_place_rate",
    "draw_bias",
    "bloodline_score",
    "lap_3f",
    "horse_weight_diff",
]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, low_memory=False, dtype={"race_id": "string", "race_date": "string"})


def normalize_labels(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    finish = pd.to_numeric(frame.get("finish_position"), errors="coerce")
    frame["finish_position"] = finish
    frame["is_win"] = np.where(finish.notna(), (finish == 1).astype("int8"), np.nan)
    frame["is_place"] = np.where(finish.notna(), (finish <= 3).astype("int8"), np.nan)
    return frame


def shifted_rolling_mean(series: pd.Series, window: int, min_periods: int = 1) -> pd.Series:
    return series.shift().rolling(window=window, min_periods=min_periods).mean()


def shifted_expanding_mean(series: pd.Series, min_periods: int = 10) -> pd.Series:
    return series.shift().expanding(min_periods=min_periods).mean()


def prepare_for_feature_build(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["race_id"] = frame["race_id"].astype(str)
    frame = canonicalize_runner_columns(frame)
    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = normalize_labels(frame)
    frame = add_market_features(frame)
    return frame


def clean_key(series: pd.Series) -> pd.Series:
    return series.replace("", pd.NA).fillna("unknown").astype(str)


def clean_person_key(series: pd.Series) -> pd.Series:
    cleaned = clean_key(series)
    cleaned = cleaned.str.replace(r"^\[[^\]]+\]\s*", "", regex=True)
    cleaned = cleaned.str.replace(r"\([^)]+\)$", "", regex=True)
    return cleaned.str.strip().replace("", "unknown")


def fill_missing(frame: pd.DataFrame, column: str, values: pd.Series) -> None:
    existing = pd.to_numeric(frame[column], errors="coerce") if column in frame else pd.Series(np.nan, index=frame.index)
    frame[column] = existing.where(existing.notna(), values).astype("float32")


def group_mean_with_min(
    frame: pd.DataFrame,
    keys: list[str],
    value: str,
    *,
    min_count: int,
    output: str,
) -> pd.DataFrame:
    stats = (
        frame.groupby(keys, dropna=False)[value]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": output})
    )
    stats.loc[stats["count"] < min_count, output] = np.nan
    return stats.drop(columns=["count"])


def last_n_mean(frame: pd.DataFrame, group_key: str, value: str, n: int, output: str) -> pd.DataFrame:
    subset = frame[[group_key, value]].dropna(subset=[value])
    if subset.empty:
        return pd.DataFrame(columns=[group_key, output])
    return (
        subset.groupby(group_key, sort=False)
        .tail(n)
        .groupby(group_key, sort=False)[value]
        .mean()
        .rename(output)
        .reset_index()
    )


def build_history_maps(base: pd.DataFrame) -> dict[str, Any]:
    base = prepare_for_feature_build(base)
    sort_columns = ["race_date", "race_id"]
    if "race_no" in base:
        sort_columns.append("race_no")
    sort_columns.append("runner_number")
    base = base.sort_values(sort_columns).copy()

    for column in ("horse_name", "jockey", "sire", "dam_sire", "surface", "venue"):
        if column in base:
            base[column] = clean_key(base[column])
    if "trainer" in base:
        base["trainer"] = clean_person_key(base["trainer"])

    if "distance" in base:
        distance = pd.to_numeric(base["distance"], errors="coerce")
        base["__distance_bucket"] = (distance / 200).round() * 200

    best_time = pd.to_numeric(base.get("best_time"), errors="coerce")
    distance = pd.to_numeric(base.get("distance"), errors="coerce")
    base["__speed"] = (distance / best_time).where((best_time > 0) & (distance > 0))

    base["__race_date_dt"] = pd.to_datetime(base.get("race_date"), errors="coerce")
    horse_latest = (
        base.dropna(subset=["horse_name", "__race_date_dt"])
        .groupby("horse_name", sort=False)
        .tail(1)[["horse_name", "__race_date_dt", "horse_weight"]]
        .rename(columns={"__race_date_dt": "__last_race_date", "horse_weight": "__last_horse_weight"})
    )

    horse_features = horse_latest.copy()
    for stats in (
        last_n_mean(base, "horse_name", "__speed", 3, "avg_last3_speed"),
        last_n_mean(base, "horse_name", "is_win", 3, "horse_recent_win_rate"),
        last_n_mean(base, "horse_name", "is_place", 3, "horse_recent_place_rate"),
        last_n_mean(base, "horse_name", "last600m", 3, "lap_3f"),
    ):
        horse_features = horse_features.merge(stats, on="horse_name", how="left")

    distance_place = group_mean_with_min(
        base,
        ["horse_name", "__distance_bucket"],
        "is_place",
        min_count=2,
        output="horse_distance_place_rate",
    )
    surface_place = group_mean_with_min(
        base,
        ["horse_name", "surface"],
        "is_place",
        min_count=2,
        output="horse_surface_place_rate",
    )
    jockey = group_mean_with_min(base, ["jockey"], "is_win", min_count=10, output="jockey_win_rate")
    trainer = group_mean_with_min(base, ["trainer"], "is_win", min_count=10, output="trainer_win_rate")
    draw = group_mean_with_min(
        base,
        ["venue", "surface", "__distance_bucket", "bracket"],
        "is_place",
        min_count=20,
        output="draw_bias",
    )

    fallback_place = float(pd.to_numeric(base["is_place"], errors="coerce").mean())
    if not np.isfinite(fallback_place):
        fallback_place = 0.23
    sire = group_mean_with_min(base, ["sire"], "is_place", min_count=20, output="__sire_place_rate")
    dam_sire = group_mean_with_min(base, ["dam_sire"], "is_place", min_count=20, output="__dam_sire_place_rate")

    return {
        "horse_features": horse_features,
        "distance_place": distance_place,
        "surface_place": surface_place,
        "jockey": jockey,
        "trainer": trainer,
        "draw": draw,
        "sire": sire,
        "dam_sire": dam_sire,
        "fallback_place": fallback_place,
    }


def enrich_netkeiba_with_history(netkeiba: pd.DataFrame, maps: dict[str, Any]) -> pd.DataFrame:
    frame = prepare_for_feature_build(netkeiba)
    for column in ("horse_name", "jockey", "sire", "dam_sire", "surface", "venue"):
        if column in frame:
            frame[column] = clean_key(frame[column])
    if "trainer" in frame:
        frame["trainer"] = clean_person_key(frame["trainer"])

    distance = pd.to_numeric(frame.get("distance"), errors="coerce")
    frame["__distance_bucket"] = (distance / 200).round() * 200
    frame["__race_date_dt"] = pd.to_datetime(frame.get("race_date"), errors="coerce")

    frame = frame.merge(maps["horse_features"], on="horse_name", how="left", suffixes=("", "__hist"))
    days_since = (frame["__race_date_dt"] - frame["__last_race_date"]).dt.days
    fill_missing(frame, "days_since_last_run", days_since.where(days_since > 0))
    fill_missing(
        frame,
        "horse_weight_diff",
        pd.to_numeric(frame.get("horse_weight"), errors="coerce") - pd.to_numeric(frame.get("__last_horse_weight"), errors="coerce"),
    )
    for column in ("avg_last3_speed", "horse_recent_win_rate", "horse_recent_place_rate", "lap_3f"):
        hist_column = f"{column}__hist"
        if hist_column in frame:
            fill_missing(frame, column, pd.to_numeric(frame[hist_column], errors="coerce"))

    frame = frame.merge(maps["distance_place"], on=["horse_name", "__distance_bucket"], how="left", suffixes=("", "__hist"))
    if "horse_distance_place_rate__hist" in frame:
        fill_missing(frame, "horse_distance_place_rate", frame["horse_distance_place_rate__hist"])

    frame = frame.merge(maps["surface_place"], on=["horse_name", "surface"], how="left", suffixes=("", "__hist"))
    if "horse_surface_place_rate__hist" in frame:
        fill_missing(frame, "horse_surface_place_rate", frame["horse_surface_place_rate__hist"])

    frame = frame.merge(maps["jockey"], on="jockey", how="left", suffixes=("", "__hist"))
    if "jockey_win_rate__hist" in frame:
        fill_missing(frame, "jockey_win_rate", frame["jockey_win_rate__hist"])

    frame = frame.merge(maps["trainer"], on="trainer", how="left", suffixes=("", "__hist"))
    if "trainer_win_rate__hist" in frame:
        fill_missing(frame, "trainer_win_rate", frame["trainer_win_rate__hist"])

    frame = frame.merge(maps["draw"], on=["venue", "surface", "__distance_bucket", "bracket"], how="left", suffixes=("", "__hist"))
    if "draw_bias__hist" in frame:
        fill_missing(frame, "draw_bias", frame["draw_bias__hist"])

    frame = frame.merge(maps["sire"], on="sire", how="left")
    frame = frame.merge(maps["dam_sire"], on="dam_sire", how="left")
    sire_rate = pd.to_numeric(frame.get("__sire_place_rate"), errors="coerce")
    dam_sire_rate = pd.to_numeric(frame.get("__dam_sire_place_rate"), errors="coerce")
    fallback = float(maps["fallback_place"])
    bloodline_source = sire_rate.notna() | dam_sire_rate.notna()
    bloodline = ((sire_rate * 0.65 + dam_sire_rate * 0.35).fillna(fallback) - fallback) * 145 + 55
    bloodline = bloodline.where(bloodline_source)
    fill_missing(frame, "bloodline_score", bloodline.clip(35, 85))

    return frame.drop(
        columns=[column for column in frame.columns if column.startswith("__") or column.endswith("__hist")],
        errors="ignore",
    )


def coverage(frame: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    return {
        column: round(float(frame[column].notna().mean()), 6)
        for column in columns
        if column in frame.columns
    }


def enrich(
    *,
    base_csv: Path,
    netkeiba_csv: Path,
    output_2026: Path,
    output_combined: Path,
) -> dict[str, Any]:
    base = read_csv(base_csv)
    netkeiba = read_csv(netkeiba_csv)
    maps = build_history_maps(base)
    enriched_2026 = enrich_netkeiba_with_history(netkeiba, maps)
    enriched_combined = pd.concat([base, enriched_2026], ignore_index=True, sort=False)

    output_2026.parent.mkdir(parents=True, exist_ok=True)
    output_combined.parent.mkdir(parents=True, exist_ok=True)
    enriched_2026.to_csv(output_2026, index=False)
    enriched_combined.to_csv(output_combined, index=False)

    return {
        "base_rows": int(len(base)),
        "netkeiba_rows": int(len(netkeiba)),
        "enriched_2026_rows": int(len(enriched_2026)),
        "combined_rows": int(len(enriched_combined)),
        "enriched_2026_races": int(enriched_2026["race_id"].nunique()),
        "combined_races": int(enriched_combined["race_id"].nunique()),
        "output_2026": str(output_2026),
        "output_combined": str(output_combined),
        "coverage_2026": coverage(enriched_2026, EXTRA_COLUMNS),
        "coverage_combined": coverage(enriched_combined, EXTRA_COLUMNS),
        "unrecoverable_from_csv": [
            "true odds snapshots / odds_delta",
            "exotic pre-race pools / ticket_pool_share",
            "raw training workout tables",
            "paddock observations",
            "stable horse/jockey/trainer IDs",
            "scratches/refunds before settlement",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Add prior-history features to scraped 2026 netkeiba CSV.")
    parser.add_argument("--base-csv", type=Path, default=Path("data/keiba_history_normalized.csv"))
    parser.add_argument("--netkeiba-csv", type=Path, default=Path("data/netkeiba_2026_normalized.csv"))
    parser.add_argument("--output-2026", type=Path, default=Path("data/netkeiba_2026_enriched.csv"))
    parser.add_argument(
        "--output-combined",
        type=Path,
        default=Path("data/keiba_history_with_2026_enriched.csv"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = enrich(
        base_csv=args.base_csv,
        netkeiba_csv=args.netkeiba_csv,
        output_2026=args.output_2026,
        output_combined=args.output_combined,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
