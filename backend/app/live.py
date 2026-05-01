from datetime import datetime, timezone

from .schemas import (
    LiveOddsMove,
    LivePollingJobRequest,
    LivePollingJobResponse,
    LiveResult,
    LiveSnapshot,
)


def get_live_snapshot(race_id: str) -> LiveSnapshot:
    now = datetime.now(timezone.utc).isoformat()

    if race_id == "kyoto-20260503-11":
        return LiveSnapshot(
            race_id=race_id,
            provider="simulation",
            racecard_status="parsed",
            odds_status="monitoring",
            result_status="waiting",
            updated_at=now,
            next_poll_seconds=60,
            odds_moves=[
                LiveOddsMove(
                    number=12,
                    name="ヘデントール",
                    previous_odds=3.5,
                    current_odds=3.2,
                    direction="down",
                    reason="本命側に買いが入っています",
                ),
                LiveOddsMove(
                    number=14,
                    name="ホーエリート",
                    previous_odds=15.1,
                    current_odds=12.8,
                    direction="down",
                    reason="相手候補として評価上昇",
                ),
            ],
            scratches=[],
            result=LiveResult(status="pending", message="結果確定待ち"),
            alerts=[
                "出馬表解析済み",
                "オッズ監視中",
                "取消発表があれば買い目を自動再計算",
            ],
        )

    return LiveSnapshot(
        race_id=race_id,
        provider="simulation",
        racecard_status="available",
        odds_status="waiting",
        result_status="waiting",
        updated_at=now,
        next_poll_seconds=120,
        odds_moves=[],
        scratches=[],
        result=LiveResult(status="pending", message="結果確定待ち"),
        alerts=["JRA accessD出馬表あり", "馬名・オッズの解析待ち", "取消情報なし"],
    )


def plan_live_polling_job(request: LivePollingJobRequest) -> LivePollingJobResponse:
    return LivePollingJobResponse(
        status="planned",
        provider=request.provider,
        interval_seconds=request.interval_seconds,
        watched_races=len(request.race_ids),
        next_steps=[
            "出馬表確定を検知したらracecard_statusをparsedへ更新",
            "オッズ差分を保存し、急変した馬をalertsへ追加",
            "出走取消を検知したら該当馬を除外して買い目を再計算",
            "公式結果と払戻を取り込み、的中時はresult.status=hitで通知",
        ],
    )
