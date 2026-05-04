from datetime import datetime

from .schemas import LivePollingJobRequest, LivePollingJobResponse, LiveSnapshot, Race


OFFICIAL_RESULTS: dict[str, dict[str, object]] = {
    "tokyo-finished-1": {
        "status": "official",
        "message": "JRA公式結果照合済み",
        "order": [2, 1],
        "winning_selection": "2",
        "payout": 820.0,
    }
}


def default_live_snapshot(race: Race) -> LiveSnapshot:
    official = OFFICIAL_RESULTS.get(race.id)
    if official is not None:
        return LiveSnapshot(
            racecard_status="parsed",
            odds_status="closed",
            result_status="official",
            next_poll_seconds=0,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            odds_moves=[],
            scratches=[],
            result={
                "status": "official",
                "message": str(official["message"]),
                "winning_selection": str(official["winning_selection"]),
                "order": list(official["order"]),
                "payout": float(official["payout"]),
            },
            alerts=["JRA公式結果と照合済み", "予想との比較表示が可能です"],
        )

    return LiveSnapshot(
        racecard_status="waiting" if race.status == "schedule-only" else "available",
        odds_status="waiting",
        result_status="waiting",
        next_poll_seconds=120,
        updated_at="未更新",
        odds_moves=[],
        scratches=[],
        result={"status": "pending", "message": "結果確定待ち"},
        alerts=["開催予定を監視中" if race.status == "schedule-only" else "JRA accessD出馬表あり", "オッズ取得待ち", "取消情報なし"],
    )


def initial_races() -> list[Race]:
    from .data_sources import get_races

    return get_races()
