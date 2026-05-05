from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    name: str
    path: str
    rows: int
    columns: list[str]
    updated_at: str | None = None


class PipelineStatus(BaseModel):
    raw_files: list[str]
    normalized_tables: list[DatasetSummary]
    feature_tables: list[DatasetSummary]
    latest_model: str | None
    message: str


class IngestRequest(BaseModel):
    csv_path: str = Field(..., description="Path under backend/, e.g. data/raw/netkeiba.csv")
    output_name: str = "runners"
    race_id_column: str = "race_id"
    horse_column: str = "horse_name"


class IngestResponse(BaseModel):
    table: DatasetSummary
    warnings: list[str]


class TrainRequest(BaseModel):
    feature_table: str = "runners_features.parquet"
    target_column: str = "is_win"
    model_name: str = "win_model"
    time_column: str | None = "race_date"


class TrainResponse(BaseModel):
    model_path: str
    rows: int
    auc: float | None
    accuracy: float | None
    features: list[str]
    warnings: list[str]


class RunnerInput(BaseModel):
    horse_id: str | None = None
    horse_name: str
    number: int | None = None
    market_odds: float | None = None
    speed: float | None = None
    stamina: float | None = None
    pace: float | None = None
    distance: float | None = None
    carried_weight: float | None = None
    days_since_last_run: float | None = None
    jockey: str | None = None
    trainer: str | None = None
    venue: str | None = None
    surface: str | None = None
    going: str | None = None


class RaceRequest(BaseModel):
    race_id: str
    bankroll: int = 10000
    runners: list[RunnerInput]


class RunnerPrediction(BaseModel):
    horse_name: str
    number: int | None
    win_probability: float
    fair_odds: float
    market_odds: float | None
    expected_value: float | None
    action: Literal["buy", "watch", "avoid"]
    reason: str


class RacePrediction(BaseModel):
    race_id: str
    model_version: str
    runners: list[RunnerPrediction]
