import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response

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
from app.ingestion import import_netkeiba_race_cards, ingest_netkeiba_window
from app.jobs import plan_sync_job, plan_training_job
from app.live import default_live_snapshot
from app.race_schedule import get_race_schedule
from app.settlement import settle_history
from app.services.ingest import ingest_csv
from app.services.status import get_status
from app.status import get_backend_status

router = APIRouter()
JST = timezone(timedelta(hours=9))
_MANUAL_REFRESH_LAST_AT = 0.0


def _compact_history_for_list(payload: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Trim heavy per-runner predictions for history list views."""
    compact: dict[str, list[dict[str, Any]]] = {}
    for day, entries in payload.items():
        compact_entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            prediction = item.get("prediction")
            if isinstance(prediction, dict):
                compact_prediction = dict(prediction)
                compact_prediction.pop("runners", None)
                item["prediction"] = compact_prediction
            compact_entries.append(item)
        compact[day] = compact_entries
    return compact


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
    response: Response,
    start_date: str | None = None,
    end_date: str | None = None,
    race_id: str | None = None,
) -> list[strategy_schemas.Race]:
    response.headers["Cache-Control"] = "s-maxage=45, stale-while-revalidate=60"
    return get_races(start_date=start_date, end_date=end_date, race_id=race_id)


@router.get("/schedule")
def race_schedule(
    response: Response,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    response.headers["Cache-Control"] = "s-maxage=60, stale-while-revalidate=120"
    return get_race_schedule(start_date=start_date, end_date=end_date)


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
    response: Response,
    start_date: str | None = None,
    end_date: str | None = None,
    compact: bool = False,
) -> dict:
    response.headers["Cache-Control"] = "s-maxage=45, stale-while-revalidate=60"
    today = datetime.now(JST).date()
    start = start_date or (today - timedelta(days=30)).isoformat()
    end = end_date or today.isoformat()
    history = get_all_history(start, end)
    races = get_races(start_date=start, end_date=end)
    settled = settle_history(history, races)
    return _compact_history_for_list(settled) if compact else settled


@router.get("/history/race/{race_id}")
def prediction_history_for_race(
    response: Response,
    race_id: str,
    date: str | None = None,
    compact: bool = False,
) -> dict:
    response.headers["Cache-Control"] = "s-maxage=30, stale-while-revalidate=45"
    race_date = date or datetime.now(JST).date().isoformat()
    history = get_all_history(race_date, race_date)
    filtered = {
        day: [entry for entry in entries if str(entry.get("race_id") or "") == race_id]
        for day, entries in history.items()
    }
    settled = settle_history(filtered, get_races(start_date=race_date, end_date=race_date, race_id=race_id))
    return _compact_history_for_list(settled) if compact else settled


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


def _authorize_ingest_job(authorization: str | None, x_cron_secret: str | None = None) -> None:
    secret = os.getenv("UMALAB_CRON_SECRET") or os.getenv("CRON_SECRET")
    if secret:
        if authorization != f"Bearer {secret}" and x_cron_secret != secret:
            raise HTTPException(status_code=401, detail="invalid cron secret")
        return
    if os.getenv("VERCEL"):
        raise HTTPException(status_code=401, detail="UMALAB_CRON_SECRET or CRON_SECRET is required in production")


def _netkeiba_response(summary: dict) -> strategy_schemas.NetkeibaIngestResponse:
    return strategy_schemas.NetkeibaIngestResponse(
        status=summary.get("status", "error"),
        source=summary.get("source", "netkeiba"),
        start_date=summary.get("start_date", ""),
        end_date=summary.get("end_date", ""),
        rows_found=summary.get("rows_found", 0),
        races_found=summary.get("races_found", 0),
        races_stored=summary.get("races_stored", 0),
        auto_predictions=summary.get("auto_predictions", 0),
        backfilled_predictions=summary.get("backfilled_predictions", 0),
        message=summary.get("message", ""),
    )


@router.get("/jobs/ingest/netkeiba", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_ingest_job(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 1,
    days_ahead: int = 2,
    max_requests: int | None = None,
    delay: float | None = None,
    refresh: bool = False,
    prefer_results: bool = False,
    backfill_finished_predictions: bool = False,
    market: str = "all",
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization, x_cron_secret)
    summary = ingest_netkeiba_window(
        start_date=start_date,
        end_date=end_date,
        days=days,
        days_ahead=days_ahead,
        max_requests=max_requests if max_requests is not None else 220,
        delay=delay if delay is not None else 0.35,
        refresh=refresh,
        prefer_results=prefer_results,
        backfill_finished_predictions=backfill_finished_predictions,
        market=market if market in {"JRA", "NAR"} else "all",
    )
    return _netkeiba_response(summary)


@router.get("/jobs/ingest/netkeiba/preday", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_preday_ingest_job(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    max_requests: int | None = None,
    delay: float | None = None,
    market: str = "all",
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization, x_cron_secret)
    tomorrow = (datetime.now(JST).date() + timedelta(days=1)).isoformat()
    summary = ingest_netkeiba_window(
        start_date=tomorrow,
        end_date=tomorrow,
        max_requests=max_requests if max_requests is not None else 260,
        delay=delay if delay is not None else 0.30,
        refresh=True,
        prefer_results=False,
        backfill_finished_predictions=False,
        market=market if market in {"JRA", "NAR"} else "all",
    )
    return _netkeiba_response(summary)


@router.get("/jobs/ingest/netkeiba/jra-odds", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_jra_odds_ingest_job(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    days: int = 1,
    days_ahead: int = 1,
    max_requests: int | None = None,
    delay: float | None = None,
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization, x_cron_secret)
    summary = ingest_netkeiba_window(
        days=days,
        days_ahead=days_ahead,
        max_requests=max_requests if max_requests is not None else 260,
        delay=delay if delay is not None else 0.12,
        refresh=True,
        prefer_results=False,
        backfill_finished_predictions=False,
        market="JRA",
    )
    return _netkeiba_response(summary)


@router.get("/jobs/ingest/netkeiba/manual-refresh", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_manual_refresh_job(
    start_date: str | None = None,
    end_date: str | None = None,
    race_id: str | None = None,
    days: int = 1,
    days_ahead: int = 1,
    max_requests: int | None = None,
    delay: float | None = None,
    prefer_results: bool = True,
    market: str = "all",
) -> strategy_schemas.NetkeibaIngestResponse:
    global _MANUAL_REFRESH_LAST_AT

    now = time.monotonic()
    if now - _MANUAL_REFRESH_LAST_AT < 20:
        return _netkeiba_response(
            {
                "status": "skipped",
                "source": "netkeiba",
                "start_date": start_date or "",
                "end_date": end_date or "",
                "message": "manual refresh is throttled; please retry shortly",
            }
        )
    _MANUAL_REFRESH_LAST_AT = now

    market_scope = market if market in {"JRA", "NAR"} else "all"
    request_cap = 12 if race_id else 72 if market_scope == "all" else 48
    summary = ingest_netkeiba_window(
        start_date=start_date,
        end_date=end_date,
        race_id=race_id,
        days=max(1, min(days, 2)),
        days_ahead=max(0, min(days_ahead, 2)),
        max_requests=min(max_requests if max_requests is not None else request_cap, 96),
        delay=max(delay if delay is not None else 0.06, 0.04),
        refresh=True,
        prefer_results=prefer_results,
        backfill_finished_predictions=False,
        market=market_scope,
    )
    return _netkeiba_response(summary)


@router.get("/jobs/ingest/netkeiba/live-lite", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_live_lite_ingest_job(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    max_requests: int | None = None,
    delay: float | None = None,
    market: str = "all",
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization, x_cron_secret)
    summary = ingest_netkeiba_window(
        days=1,
        days_ahead=1,
        max_requests=max_requests if max_requests is not None else 90,
        delay=delay if delay is not None else 0.10,
        refresh=True,
        prefer_results=True,
        backfill_finished_predictions=False,
        market=market if market in {"JRA", "NAR"} else "all",
    )
    return _netkeiba_response(summary)


@router.get("/jobs/ingest/netkeiba/results", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_result_ingest_job(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    days: int = 2,
    days_ahead: int = 1,
    max_requests: int | None = None,
    delay: float | None = None,
    backfill_finished_predictions: bool = False,
    market: str = "all",
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization, x_cron_secret)
    summary = ingest_netkeiba_window(
        days=days,
        days_ahead=days_ahead,
        max_requests=max_requests if max_requests is not None else 320,
        delay=delay if delay is not None else 0.25,
        refresh=True,
        prefer_results=True,
        backfill_finished_predictions=backfill_finished_predictions,
        market=market if market in {"JRA", "NAR"} else "all",
    )
    return _netkeiba_response(summary)


@router.post("/jobs/ingest/netkeiba/import", response_model=strategy_schemas.NetkeibaIngestResponse)
def netkeiba_import_job(
    request: strategy_schemas.NetkeibaRaceImportRequest,
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
) -> strategy_schemas.NetkeibaIngestResponse:
    _authorize_ingest_job(authorization, x_cron_secret)
    summary = import_netkeiba_race_cards(
        [race.model_dump(mode="json") for race in request.races],
        source=request.source,
        auto_predict=request.auto_predict,
    )
    return _netkeiba_response({**summary, "source": summary.get("source", request.source)})


@router.get("/jobs/backfill/history")
def history_backfill_job(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    start_date: str | None = None,
    end_date: str | None = None,
    market: str = "JRA",
    limit: int = 80,
    include_existing: bool = False,
) -> dict:
    _authorize_ingest_job(authorization, x_cron_secret)
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="start_date and end_date are required")

    from app.ingestion import _existing_prediction_ids, _record_prediction_for_race

    existing = set() if include_existing else _existing_prediction_ids(start_date, end_date)
    races = get_races(start_date=start_date, end_date=end_date)
    candidates: list[dict] = []
    for race in races:
        if race.status != "finished":
            continue
        if market != "all" and race.market != market:
            continue
        if not include_existing and race.id in existing:
            continue
        candidates.append(race.model_dump(mode="json"))

    if limit > 0:
        candidates = candidates[:limit]

    saved = 0
    failed: list[str] = []
    for race in candidates:
        race_id = str(race.get("id") or "")
        if _record_prediction_for_race(race, generated_after_result=True):
            saved += 1
            existing.add(race_id)
        else:
            failed.append(race_id)

    return {
        "status": "ok" if not failed else "partial",
        "start_date": start_date,
        "end_date": end_date,
        "market": market,
        "candidate_races": len(candidates),
        "saved": saved,
        "failed": len(failed),
        "failed_sample": failed[:10],
    }


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
