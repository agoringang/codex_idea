import os
from datetime import date, timedelta

from fastapi import APIRouter, Header, HTTPException

from app import schemas as strategy_schemas
from app.core.schemas import (
    IngestRequest,
    IngestResponse,
    PipelineStatus,
    RacePrediction as BasicRacePrediction,
    RaceRequest as BasicRaceRequest,
    TrainRequest,
    TrainResponse,
)
from app.data_sources import get_races, get_snapshots
from app.history import get_all_history, get_history_for_date, record_prediction
from app.ingestion import ingest_netkeiba_window
from app.jobs import plan_sync_job, plan_training_job
from app.live import default_live_snapshot
from app.settlement import settle_history
from app.services.ingest import ingest_csv
from app.services.status import get_status
from app.status import get_backend_status

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status", response_model=PipelineStatus)
def status() -> PipelineStatus:
    return get_status()


@router.get("/status/product", response_model=strategy_schemas.BackendStatus)
def product_status() -> strategy_schemas.BackendStatus:
    return get_backend_status()


@router.get("/races", response_model=list[strategy_schemas.Race])
def races(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[strategy_schemas.Race]:
    return get_races(start_date=start_date, end_date=end_date)


@router.get("/live/{race_id}", response_model=strategy_schemas.LiveSnapshot)
def live_snapshot(race_id: str) -> strategy_schemas.LiveSnapshot:
    snapshots = get_snapshots()
    if race_id in snapshots:
        return snapshots[race_id]

    for race in get_races():
        if race.id == race_id:
            return default_live_snapshot(race)

    return strategy_schemas.LiveSnapshot(
        racecard_status="waiting",
        odds_status="waiting",
        result_status="waiting",
        updated_at="未更新",
        next_poll_seconds=300,
        odds_moves=[],
        scratches=[],
        result=strategy_schemas.LiveResult(status="pending", message="race_id is not in the local calendar"),
        alerts=["未登録のレースIDです"],
    )


@router.get("/history")
def prediction_history(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    today = date.today()
    start = start_date or (today - timedelta(days=30)).isoformat()
    end = end_date or today.isoformat()
    history = get_all_history(start, end)
    races = get_races(start_date=start, end_date=end)
    return settle_history(history, races)


@router.get("/history/{date}")
def prediction_history_for_date(date: str) -> list[dict]:
    return settle_history({date: get_history_for_date(date)}, get_races(start_date=date, end_date=date)).get(date, [])


@router.post("/ingest/csv", response_model=IngestResponse)
def ingest_csv_endpoint(request: IngestRequest) -> IngestResponse:
    return ingest_csv(request)


@router.post("/features/runners")
def build_runner_features_endpoint(
    input_table: str = "runners.parquet",
    output_table: str = "runners_features.parquet",
):
    from app.ml.features import build_runner_features

    return build_runner_features(input_table=input_table, output_table=output_table)


@router.post("/train", response_model=TrainResponse)
def train_endpoint(request: TrainRequest) -> TrainResponse:
    from app.ml.train import train_model

    return train_model(request)


@router.post("/predict", response_model=strategy_schemas.RacePrediction)
def predict_endpoint(request: strategy_schemas.RaceRequest) -> strategy_schemas.RacePrediction:
    from app.model import predict_race as predict_strategy_race

    prediction = predict_strategy_race(request)
    metadata = {
        "race_date": request.race_date,
        "venue": request.venue,
        "title": request.title,
        "race_no": request.race_no,
        "course": request.course,
        "market": request.market,
        "risk_level": request.risk_level,
        "bankroll": request.bankroll,
        "model_mode": request.model_mode,
        "model_version": request.model_version,
    }
    try:
        record_prediction(
            request.race_id,
            request.race_date or date.today().isoformat(),
            prediction=prediction.model_dump(mode="json"),
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
    except Exception:
        pass
    return prediction


@router.post("/predict/basic", response_model=BasicRacePrediction)
def predict_basic_endpoint(request: BasicRaceRequest) -> BasicRacePrediction:
    from app.ml.predict import predict_race as predict_basic_race

    return predict_basic_race(request)


@router.post("/jobs/sync", response_model=strategy_schemas.SyncJobResponse)
def sync_job(request: strategy_schemas.SyncJobRequest) -> strategy_schemas.SyncJobResponse:
    return plan_sync_job(request)


@router.post("/jobs/train", response_model=strategy_schemas.TrainingJobResponse)
def training_job(request: strategy_schemas.TrainingJobRequest) -> strategy_schemas.TrainingJobResponse:
    return plan_training_job(request)


def _authorize_ingest_job(authorization: str | None) -> None:
    secret = os.getenv("CRON_SECRET")
    if secret:
        if authorization != f"Bearer {secret}":
            raise HTTPException(status_code=401, detail="invalid cron secret")
        return
    if os.getenv("VERCEL"):
        raise HTTPException(status_code=401, detail="CRON_SECRET is required in production")


@router.get("/jobs/ingest/netkeiba", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_ingest_job(
    authorization: str | None = Header(default=None),
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 2,
    max_requests: int | None = None,
    delay: float | None = None,
    refresh: bool = False,
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization)
    summary = ingest_netkeiba_window(
        start_date=start_date,
        end_date=end_date,
        days=days,
        max_requests=max_requests,
        delay=delay,
        refresh=refresh,
    )
    return strategy_schemas.NetkeibaIngestResponse(
        status=summary.get("status", "error"),
        source=summary.get("source", "netkeiba"),
        start_date=summary.get("start_date", ""),
        end_date=summary.get("end_date", ""),
        rows_found=summary.get("rows_found", 0),
        races_found=summary.get("races_found", 0),
        races_stored=summary.get("races_stored", 0),
        auto_predictions=summary.get("auto_predictions", 0),
        message=summary.get("message", ""),
    )


@router.post("/jobs/live-polling", response_model=strategy_schemas.LivePollingJobResponse)
def live_polling_job(
    request: strategy_schemas.LivePollingJobRequest,
) -> strategy_schemas.LivePollingJobResponse:
    return strategy_schemas.LivePollingJobResponse(
        status="planned",
        provider=request.provider,
        interval_seconds=request.interval_seconds,
        watched_races=len(request.race_ids),
        next_steps=[
            "出馬表確定後に対象race_idを監視キューへ登録",
            "パドック開始後はオッズ、取消、馬体重、気配メモを短周期で更新",
            "締切前に期待値と購入上限を再計算",
        ],
    )
