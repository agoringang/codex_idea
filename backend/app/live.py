from .schemas import LivePollingJobRequest, LivePollingJobResponse, LiveSnapshot, Race


def default_live_snapshot(race: Race) -> LiveSnapshot:
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
    from .races_data import races as mock_races

    return [Race(**race) for race in mock_races]
