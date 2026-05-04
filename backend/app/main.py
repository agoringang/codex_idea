import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .data_sources import get_races as load_real_races, get_snapshots as load_real_snapshots
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
from .history import get_all_history, get_history_for_date, record_prediction

# In-memory data store
races_store: list[Race] = []
snapshots_store: dict[str, LiveSnapshot] = {}


def _load_races_from_source() -> list[Race]:
    loaded_races = load_real_races()
    if loaded_races:
        return loaded_races

    from .live import initial_races

    return initial_races()


def _refresh_races_store() -> None:
    from .live import default_live_snapshot

    global races_store, snapshots_store
    fresh_races = _load_races_from_source()
    if not fresh_races:
        return
    fresh_ids = {race.id for race in fresh_races}
    races_store = fresh_races
    fresh_snapshots = load_real_snapshots()
    snapshots_store = fresh_snapshots
    for race in fresh_races:
        snapshots_store.setdefault(race.id, default_live_snapshot(race))
    for race_id in list(snapshots_store.keys()):
        if race_id not in fresh_ids:
            snapshots_store.pop(race_id, None)


def _sync_official_history(race: Race, snapshot: LiveSnapshot | None) -> None:
    if snapshot is None:
        return
    if snapshot.result.status != "official":
        return
    try:
        record_prediction(
            race.id,
            race.date,
            None,
            {
                "status": snapshot.result.status,
                "message": snapshot.result.message,
                "winning_selection": snapshot.result.winning_selection,
                "order": snapshot.result.order,
                "payout": snapshot.result.payout,
            },
        )
    except Exception:
        pass


async def update_race_statuses():
    """Periodically update race statuses to simulate live changes."""
    from .live import default_live_snapshot

    global races_store, snapshots_store
    if not races_store:
        races_store = _load_races_from_source()
        snapshots_store = load_real_snapshots()
        from .live import default_live_snapshot

        for race in races_store:
            snapshots_store.setdefault(race.id, default_live_snapshot(race))

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
    _refresh_races_store()
    return races_store


@app.get("/snapshots", response_model=dict[str, LiveSnapshot])
def get_snapshots() -> dict[str, LiveSnapshot]:
    _refresh_races_store()
    for race in races_store:
        _sync_official_history(race, snapshots_store.get(race.id))
    return snapshots_store


@app.get("/snapshots/{race_id}", response_model=Optional[LiveSnapshot])
def get_snapshot(race_id: str) -> LiveSnapshot | None:
    _refresh_races_store()
    snapshot = snapshots_store.get(race_id)
    race = next((item for item in races_store if item.id == race_id), None)
    if race is not None:
        _sync_official_history(race, snapshot)
    return snapshot


@app.post("/predict", response_model=RacePrediction)
def predict(request: RaceRequest) -> RacePrediction:
    prediction = predict_race(request)
    # try to record prediction into history with the race date if available
    try:
        race = next((r for r in races_store if r.id == request.race_id), None)
        date = race.date if race is not None else "unknown"
        record_prediction(request.race_id, date, {"request": request.dict(), "prediction": prediction.dict()}, None)
    except Exception:
        # never fail the API if history recording fails
        pass
    return prediction


@app.get("/history", response_model=dict)
def history_all() -> dict:
    return get_all_history()


@app.get("/history/{date}", response_model=list)
def history_date(date: str) -> list:
    return get_history_for_date(date)


@app.post("/jobs/sync", response_model=SyncJobResponse)
def create_sync_job(request: SyncJobRequest) -> SyncJobResponse:
    return plan_sync_job(request)


@app.post("/jobs/train", response_model=TrainingJobResponse)
def create_training_job(request: TrainingJobRequest) -> TrainingJobResponse:
    return plan_training_job(request)
