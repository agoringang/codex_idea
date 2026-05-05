from fastapi import APIRouter

from app.core.schemas import (
    IngestRequest,
    IngestResponse,
    PipelineStatus,
    RacePrediction,
    RaceRequest,
    TrainRequest,
    TrainResponse,
)
from app.ml.features import build_runner_features
from app.ml.predict import predict_race
from app.ml.train import train_model
from app.services.ingest import ingest_csv
from app.services.status import get_status

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status", response_model=PipelineStatus)
def status() -> PipelineStatus:
    return get_status()


@router.post("/ingest/csv", response_model=IngestResponse)
def ingest_csv_endpoint(request: IngestRequest) -> IngestResponse:
    return ingest_csv(request)


@router.post("/features/runners")
def build_runner_features_endpoint(input_table: str = "runners.parquet", output_table: str = "runners_features.parquet"):
    return build_runner_features(input_table=input_table, output_table=output_table)


@router.post("/train", response_model=TrainResponse)
def train_endpoint(request: TrainRequest) -> TrainResponse:
    return train_model(request)


@router.post("/predict", response_model=RacePrediction)
def predict_endpoint(request: RaceRequest) -> RacePrediction:
    return predict_race(request)
