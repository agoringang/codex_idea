from fastapi import FastAPI

from .jobs import plan_sync_job, plan_training_job
from .live import get_live_snapshot, plan_live_polling_job
from .model import predict_race
from .status import get_backend_status
from .schemas import (
    BackendStatus,
    LivePollingJobRequest,
    LivePollingJobResponse,
    LiveSnapshot,
    RacePrediction,
    RaceRequest,
    SyncJobRequest,
    SyncJobResponse,
    TrainingJobRequest,
    TrainingJobResponse,
)

app = FastAPI(
    title="RaceQuant ML API",
    version="0.1.0",
    description="Horse-racing probability, expected value, and stake-sizing service.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", response_model=BackendStatus)
def status() -> BackendStatus:
    return get_backend_status()


@app.get("/live/{race_id}", response_model=LiveSnapshot)
def live_snapshot(race_id: str) -> LiveSnapshot:
    return get_live_snapshot(race_id)


@app.post("/predict", response_model=RacePrediction)
def predict(request: RaceRequest) -> RacePrediction:
    return predict_race(request)


@app.post("/jobs/sync", response_model=SyncJobResponse)
def create_sync_job(request: SyncJobRequest) -> SyncJobResponse:
    return plan_sync_job(request)


@app.post("/jobs/train", response_model=TrainingJobResponse)
def create_training_job(request: TrainingJobRequest) -> TrainingJobResponse:
    return plan_training_job(request)


@app.post("/jobs/live-polling", response_model=LivePollingJobResponse)
def create_live_polling_job(request: LivePollingJobRequest) -> LivePollingJobResponse:
    return plan_live_polling_job(request)
