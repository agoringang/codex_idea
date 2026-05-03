import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .jobs import plan_sync_job, plan_training_job
from .model import predict_race
from .schemas import (
    BackendStatus,
    LivePollingJobRequest,
    LivePollingJobResponse,
    LiveSnapshot,
    Race,
    RacePrediction,
    RaceRequest,
    SyncJobRequest,
    SyncJobResponse,
    TrainingJobRequest,
    TrainingJobResponse,
)
from .status import get_backend_status

# In-memory data store
races_store: list[Race] = []
snapshots_store: dict[str, LiveSnapshot] = {}


async def update_race_statuses():
    """Periodically update race statuses to simulate live changes."""
    from .live import default_live_snapshot, initial_races

    global races_store, snapshots_store
    if not races_store:
        races_store = initial_races()
        snapshots_store = {race.id: default_live_snapshot(race) for race in races_store}

    while True:
        await asyncio.sleep(10)  # Update every 10 seconds
        now = datetime.now()
        for race in races_store:
            try:
                start_time = datetime.fromisoformat(f"{race.date}T{race.start}")
                if race.status != "finished" and now > start_time + timedelta(minutes=2):
                    race.status = "finished"
                    print(f"Race {race.id} has finished.")
                elif race.status == "racecard-available" and now > start_time - timedelta(minutes=30):
                    race.status = "prediction-ready"
                    print(f"Race {race.id} is now prediction-ready.")
            except ValueError:
                continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting background task to update race statuses...")
    asyncio.create_task(update_race_statuses())
    yield
    # Shutdown
    print("Application shutdown.")


app = FastAPI(
    title="RaceQuant ML API",
    version="0.1.0",
    description="Horse-racing probability, expected value, and stake-sizing service.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", response_model=BackendStatus)
def status() -> BackendStatus:
    return get_backend_status()


@app.get("/races", response_model=list[Race])
def get_races() -> list[Race]:
    return races_store


@app.get("/snapshots", response_model=dict[str, LiveSnapshot])
def get_snapshots() -> dict[str, LiveSnapshot]:
    return snapshots_store


@app.get("/snapshots/{race_id}", response_model=Optional[LiveSnapshot])
def get_snapshot(race_id: str) -> LiveSnapshot | None:
    return snapshots_store.get(race_id)


@app.post("/predict", response_model=RacePrediction)
def predict(request: RaceRequest) -> RacePrediction:
    return predict_race(request)


@app.post("/jobs/sync", response_model=SyncJobResponse)
def create_sync_job(request: SyncJobRequest) -> SyncJobResponse:
    return plan_sync_job(request)


@app.post("/jobs/train", response_model=TrainingJobResponse)
def create_training_job(request: TrainingJobRequest) -> TrainingJobResponse:
    return plan_training_job(request)
