from datetime import datetime, timedelta, timezone

from .schemas import BackendStage, BackendStatus, BacktestSummary, FeatureCoverage, ModelArtifact


def get_backend_status() -> BackendStatus:
    now = datetime.now(timezone.utc)

    return BackendStatus(
        mode="simulation",
        provider="jravan",
        data_window="未接続: 2006-2026を取得予定",
        last_sync_at=(now - timedelta(minutes=7)).isoformat(),
        next_retrain_at=(now + timedelta(hours=18)).isoformat(),
        active_model="racequant-rank-ensemble-v0-sample",
        stages=[
            BackendStage(
                id="ingest",
                label="データ同期",
                status="blocked",
                detail="JRA-VAN Data Lab. / CSV実データ未接続。20年分のraw投入待ち",
                records=0,
                latency_ms=None,
            ),
            BackendStage(
                id="normalize",
                label="正規化",
                status="idle",
                detail="レース、出走馬、オッズスナップショット、払戻を標準スキーマ化する設計のみ完了",
                records=0,
                latency_ms=None,
            ),
            BackendStage(
                id="features",
                label="特徴量生成",
                status="idle",
                detail="タイム、騎手、体重、調教師、血統、オッズ変動などの特徴量カタログを定義",
                records=0,
                latency_ms=None,
            ),
            BackendStage(
                id="training",
                label="モデル学習",
                status="idle",
                detail="実データ投入後に時系列分割で確率校正済みモデルを検証",
                records=0,
                latency_ms=None,
            ),
            BackendStage(
                id="inference",
                label="推論",
                status="running",
                detail="サンプル入力で単勝確率と順位分布から全券種の期待値を計算",
                records=9,
                latency_ms=95,
            ),
            BackendStage(
                id="retrain",
                label="継続学習",
                status="idle",
                detail="確定結果を取り込み、ドリフト検知後に再学習をキュー投入",
                records=0,
                latency_ms=None,
            ),
        ],
        artifacts=[
            ModelArtifact(
                name="win_probability",
                version="v0.1.0-sample",
                target="単勝確率",
                metric="未評価: 実データ学習待ち",
                path="models/win_probability.joblib",
            ),
            ModelArtifact(
                name="rank_distribution",
                version="v0.1.0-sample",
                target="順位分布",
                metric="未評価: 実データ学習待ち",
                path="models/rank_distribution.joblib",
            ),
            ModelArtifact(
                name="ticket_ev",
                version="v0.1.0-sample",
                target="全券種EV",
                metric="未評価: バックテストCSV待ち",
                path="models/ticket_ev.joblib",
            ),
        ],
        feature_coverage=[
            FeatureCoverage(
                group="レース条件",
                status="missing",
                fields=["開催日", "場", "距離", "芝/ダート", "馬場", "天候", "クラス", "頭数", "枠順"],
                source="JRA-VAN / CSV",
                detail="スキーマ定義済み。実データ未投入",
            ),
            FeatureCoverage(
                group="出走馬",
                status="missing",
                fields=["馬齢", "性別", "斤量", "馬体重", "馬体重増減", "脚質", "近走成績", "走破タイム", "上がり"],
                source="JRA-VAN / 公式結果",
                detail="馬体重は発走約60分前の速報値を取得対象",
            ),
            FeatureCoverage(
                group="人・血統",
                status="missing",
                fields=["騎手", "調教師", "馬主", "生産者", "父", "母父", "騎手勝率", "調教師勝率"],
                source="JRA-VAN",
                detail="血糖ではなく血統データを特徴量化する想定",
            ),
            FeatureCoverage(
                group="市場",
                status="missing",
                fields=["単勝", "複勝", "枠連", "馬連", "ワイド", "馬単", "3連複", "3連単", "時系列オッズ", "票数"],
                source="JRA-VAN速報オッズ/時系列オッズ",
                detail="購入締切時点だけでなく、発走前スナップショットを保持",
            ),
            FeatureCoverage(
                group="結果・払戻",
                status="missing",
                fields=["着順", "走破タイム", "着差", "払戻", "返還", "取消", "騎手変更"],
                source="JRA-VAN速報成績/払戻",
                detail="的中判定と回収率バックテストのラベル",
            ),
        ],
        backtest=BacktestSummary(
            status="not_started",
            window="未実行",
            races=0,
            bets=0,
            total_stake=0,
            total_payout=0,
            roi=0,
            hit_rate=0,
            max_drawdown=0,
            note="20年分の実データが未接続のため、実回収率はまだ出せません。CSV/JRA-VAN投入後に算出します。",
        ),
        runtime_notes=[
            "現状はサンプル推論。実データ学習済みとは扱わない",
            "JRA-VAN接続後はmodeをliveへ切替",
            "バックテストでは購入時点で見えていたオッズだけを使う",
        ],
    )
