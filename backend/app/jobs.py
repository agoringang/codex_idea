from .schemas import SyncJobRequest, SyncJobResponse, TrainingJobRequest, TrainingJobResponse


def plan_sync_job(request: SyncJobRequest) -> SyncJobResponse:
    if request.provider == "jravan":
        steps = [
            "JRA-VAN Data Lab.の利用キーを環境変数またはローカル設定に保存",
            "JV-Link経由で過去データ、出馬表、オッズ、結果、払戻をraw領域へ同期",
            "レース単位のparquetへ正規化し、学習用feature tableを更新",
            "開催日はオッズ更新を短周期で取り込み、確定後に結果を追記",
        ]
    else:
        steps = [
            "CSV/raw_pathから過去レース、出走馬、オッズ、払戻を読み込む",
            "列名をRaceQuantの標準スキーマへ変換",
            "学習用feature tableとバックテスト用odds snapshotを作成",
        ]

    return SyncJobResponse(
        provider=request.provider,
        years=request.years,
        status="planned",
        next_steps=steps,
    )


def plan_training_job(request: TrainingJobRequest) -> TrainingJobResponse:
    targets = ["win_probability", "top2_probability", "finish_rank_distribution"]
    if request.include_odds_snapshots:
        targets.extend(["ticket_expected_value", "closing_odds_calibration"])

    return TrainingJobResponse(
        status="planned",
        dataset=f"{request.start_year}-{request.end_year}",
        targets=targets,
        next_steps=[
            "時系列分割でtrain/validation/testを作成し、未来情報リークを防ぐ",
            "単勝・連対・着順分布モデルを学習し、Platt/Isotonicで確率校正",
            "順位分布から馬連・馬単・ワイド・3連複・3連単の結合確率へ展開",
            "オッズ時点別のバックテストで回収率、最大ドローダウン、購入点数を評価",
            "本番モデルをmodel registryへ保存し、開催後に増分再学習する",
        ],
    )
