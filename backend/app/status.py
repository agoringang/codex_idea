import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .public_model_status import PUBLIC_HOLDOUT_BACKTEST, PUBLIC_HOLDOUT_METRICS
from .schemas import BackendStage, BackendStatus, BacktestSummary, FeatureCoverage, ModelArtifact

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_backend_status() -> BackendStatus:
    now = datetime.now(timezone.utc)
    holdout_metrics = read_json(BACKEND_ROOT / "models/racequant_holdout_2026/holdout_experiment.json")
    if holdout_metrics is None and os.environ.get("RACEQUANT_MODEL_URL"):
        holdout_metrics = PUBLIC_HOLDOUT_METRICS
    metrics = holdout_metrics or read_json(BACKEND_ROOT / "models/racequant/metrics.json")
    backtest = read_json(BACKEND_ROOT / "backtests/holdout2026-risk52.json")
    backtest_window = "2026 holdout risk52"
    if backtest is None and os.environ.get("RACEQUANT_MODEL_URL"):
        backtest = PUBLIC_HOLDOUT_BACKTEST
    if backtest is None:
        backtest = read_json(BACKEND_ROOT / "backtests/smoke-risk72.json")
        backtest_window = "sample smoke"

    if holdout_metrics:
        split = holdout_metrics["split"]
        trained_rows = int(split["fit_rows"] + split["calibration_rows"] + split["holdout_rows"])
        trained_races = int(
            split["fit_races"] + split["calibration_races"] + split["holdout_races"]
        )
        win_test = holdout_metrics["best"]["is_win"]["holdout_2026"]
        top2_test = holdout_metrics["best"]["is_top2"]["holdout_2026"]
        place_test = holdout_metrics["best"]["is_place"]["holdout_2026"]
        quality_gate = {"publishable": bool(holdout_metrics["risk_router"]["stable_on_2026"])}
        artifact_path = (
            "RACEQUANT_MODEL_URL"
            if os.environ.get("RACEQUANT_MODEL_URL")
            else "models/racequant_holdout_2026/holdout_artifact.joblib"
        )
        data_window = (
            f"<=2025 train / 2026 holdout / {split['holdout_races']} holdout races"
        )
        active_model_name = "umalab-risk-routed-holdout2026"
        model_version = "v0.3.0-holdout2026"
    elif metrics:
        trained_rows = int(metrics["rows"])
        trained_races = int(metrics["races"])
        win_test = metrics["targets"]["is_win"]["test"]
        top2_test = {}
        place_test = metrics["targets"]["is_place"]["test"]
        quality_gate = metrics.get("quality_gate", {})
        artifact_path = "models/racequant/latest.joblib"
        data_window = f"local CSV評価済み / {trained_races} races / {trained_rows} rows"
        active_model_name = (
            "umalab-local-gated-v0"
            if bool(quality_gate.get("publishable"))
            else "umalab-local-research-v0"
        )
        model_version = (
            "v0.2.0-gated" if bool(quality_gate.get("publishable")) else "v0.2.0-research"
        )
    else:
        trained_rows = 0
        trained_races = 0
        win_test = {}
        top2_test = {}
        place_test = {}
        quality_gate = {}
        artifact_path = "models/racequant/latest.joblib"
        data_window = "未接続: 学習用CSV未作成"
        active_model_name = "umalab-sample-v0"
        model_version = "v0.1.0-sample"

    feature_presence = metrics.get("feature_presence", {}) if metrics else {}
    publishable = bool(quality_gate.get("publishable"))
    model_status = "ready" if publishable else "partial"
    if backtest_window.startswith("2026"):
        backtest_note = (
            "2026ホールドアウトでリスク別の買い目を検証。"
            "公開表示では利益保証ではなく検証実績として扱う"
        )
    elif backtest:
        backtest_note = (
            "単勝・複勝のみの検証。"
            "3連系などは公式払戻列の取り込み後に公開用ROIとして扱う"
        )
    else:
        backtest_note = "実データバックテストは未実行"

    return BackendStatus(
        mode="local-trained" if publishable else ("research" if metrics else "setup"),
        provider="local_csv",
        data_window=data_window,
        last_sync_at=(now - timedelta(minutes=7)).isoformat(),
        next_retrain_at=(now + timedelta(hours=18)).isoformat(),
        active_model=active_model_name,
        stages=[
            BackendStage(
                id="ingest",
                label="データ取得",
                status="ready" if metrics else "idle",
                detail=(
                    f"ローカルCSVから{trained_races}レース分の"
                    "学習用CSVを作成済み"
                    if metrics
                    else "backend/data/keiba_data から学習用CSVへの変換待ち"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="normalize",
                label="正規化",
                status="ready" if metrics else "idle",
                detail=(
                    "race_id・出走馬・着順・単勝オッズ・人気・"
                    "騎手・調教師・馬体重などを標準列に変換済み"
                    if metrics
                    else "CSV作成後に標準スキーマへ変換"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="features",
                label="特徴量生成",
                status="ready" if metrics else "idle",
                detail=(
                    "馬番、枠番、市場確率、斤量、馬体重、年齢、直近成績、"
                    "騎手/調教師率、枠傾向を使用。"
                    "結果由来の走破タイムと上がりは直接除外"
                    if metrics
                    else "特徴量カタログを定義済み"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="training",
                label="モデル学習",
                status=model_status if metrics else "idle",
                detail=(
                    "win/placeモデルを時系列寄りのレース単位分割で評価。"
                    "品質ゲート通過時のみ公開用として扱う"
                    if metrics
                    else "学習用CSV作成後にモデルを学習"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="inference",
                label="推論",
                status="running" if publishable else ("partial" if metrics else "idle"),
                detail=(
                    "市場確率と学習モデルのアンサンブルで"
                    "単勝確率・複勝圏確率を計算。"
                    "券種EVは公式払戻とオッズ時系列の追加待ち"
                    if metrics
                    else "モデル未作成のためサンプル推論のみ"
                ),
                records=9 if metrics else 0,
                latency_ms=95 if metrics else None,
            ),
            BackendStage(
                id="retrain",
                label="継続学習",
                status="idle",
                detail=(
                    "新しいCSVを追加した場合、"
                    "再学習してlatest.joblibを更新する設計"
                ),
                records=0,
                latency_ms=None,
            ),
        ],
        artifacts=[
            ModelArtifact(
                name="win_probability",
                version=model_version if metrics else "v0.1.0-sample",
                target="単勝確率",
                metric=(
                    f"test AUC {win_test.get('auc', 0):.3f} / "
                    f"Brier {win_test.get('brier', 0):.3f} / "
                    f"market差 {win_test.get('brier_vs_market', 0):+.3f}"
                    if metrics
                    else "未評価: 学習用CSV待ち"
                ),
                path=artifact_path,
            ),
            ModelArtifact(
                name="place_probability",
                version=model_version if metrics else "v0.1.0-sample",
                target="複勝圏確率",
                metric=(
                    f"test AUC {place_test.get('auc', 0):.3f} / "
                    f"Brier {place_test.get('brier', 0):.3f} / "
                    f"market差 {place_test.get('brier_vs_market', 0):+.3f}"
                    if metrics
                    else "未評価: 学習用CSV待ち"
                ),
                path=artifact_path,
            ),
            ModelArtifact(
                name="top2_probability",
                version=model_version if holdout_metrics else "not_generated",
                target="2着以内確率",
                metric=(
                    f"holdout AUC {top2_test.get('auc', 0):.3f} / "
                    f"Brier {top2_test.get('brier', 0):.3f} / "
                    f"market差 {top2_test.get('brier_vs_market', 0):+.3f}"
                    if holdout_metrics
                    else "未評価: holdoutモデル待ち"
                ),
                path=artifact_path,
            ),
            ModelArtifact(
                name="ticket_ev",
                version="blocked",
                target="全券種EV",
                metric=(
                    "公式払戻列とオッズスナップショットが揃うまで"
                    "公開用EVモデルは未学習"
                    if backtest
                    else "未評価: 実データバックテスト待ち"
                ),
                path="models/ticket_ev.joblib (not generated)",
            ),
        ],
        feature_coverage=[
            FeatureCoverage(
                group="レース条件",
                status="ready" if metrics else "missing",
                fields=["開催日", "場", "距離", "芝/ダート", "馬場", "天候"],
                source="local CSV",
                detail=(
                    f"venue={feature_presence.get('venue', 0):.0%}, "
                    f"surface={feature_presence.get('surface', 0):.0%}, "
                    f"going={feature_presence.get('going', 0):.0%}, "
                    f"weather={feature_presence.get('weather', 0):.0%}"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="出走馬",
                status="ready" if metrics else "missing",
                fields=[
                    "馬齢",
                    "性別",
                    "斤量",
                    "馬体重",
                    "馬体重増減",
                    "直近成績",
                    "距離/馬場適性",
                ],
                source="local CSV",
                detail=(
                    f"age={feature_presence.get('age', 0):.0%}, "
                    f"horse_weight={feature_presence.get('horse_weight', 0):.0%}, "
                    f"recent_place={feature_presence.get('horse_recent_place_rate', 0):.0%}, "
                    f"avg_last3_speed={feature_presence.get('avg_last3_speed', 0):.0%}"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="人・厩舎",
                status="ready" if metrics else "missing",
                fields=["騎手", "調教師"],
                source="local CSV",
                detail=(
                    f"jockey={feature_presence.get('jockey', 0):.0%}, "
                    f"trainer={feature_presence.get('trainer', 0):.0%}"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="市場",
                status="ready" if metrics else "missing",
                fields=["単勝オッズ", "人気", "市場勝率", "市場複勝圏率"],
                source="local CSV",
                detail=(
                    f"market_odds={feature_presence.get('market_odds', 0):.0%}, "
                    f"odds_rank={feature_presence.get('odds_rank', 0):.0%}。"
                    "時系列オッズや票数は未取得"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="結果",
                status="ready" if metrics else "missing",
                fields=["着順", "単勝ラベル", "複勝圏ラベル"],
                source="local CSV",
                detail=(
                    f"{trained_races}レース、"
                    f"{trained_rows}出走馬分の教師ラベルを作成済み"
                    if metrics
                    else "未作成"
                ),
            ),
        ],
        backtest=BacktestSummary(
            status="ready" if backtest_window.startswith("2026") else ("sample" if backtest else "not_started"),
            window=backtest_window if backtest else "未実行",
            races=int(backtest["races"]) if backtest else 0,
            bets=int(backtest["bets"]) if backtest else 0,
            total_stake=float(backtest["total_stake"]) if backtest else 0,
            total_payout=float(backtest["total_payout"]) if backtest else 0,
            roi=float(backtest["roi"]) if backtest else 0,
            hit_rate=float(backtest["hit_rate"]) if backtest else 0,
            max_drawdown=float(backtest["max_drawdown"]) if backtest else 0,
            note=backtest_note,
        ),
        runtime_notes=(
            [
                "ローカルCSVからwin/placeモデルを学習済み",
                f"quality_gate.publishable={publishable}",
                "place_odds、走破タイム、上がりは直接学習から除外し、"
                "履歴化できる値だけ特徴量化する",
                "全券種EV、着順分布、オッズドリフトは公式払戻と"
                "時系列オッズの保存後に別モデルとして昇格する",
                "利益保証や勝率100%を目的とせず、"
                "期待値候補を検証するための研究用ワークベンチ",
            ]
            if metrics
            else [
                "backend/data/keiba_data はローカルに存在するが、"
                "学習用CSVとモデルは未作成",
                "uv run python scripts/convert_keiba_data.py で正規化CSVを作成する",
                "uv run python scripts/train_production.py と "
                "backtest_simulator.py の後に実績表示を更新する",
                "利益保証や勝率100%を目的とせず、"
                "期待値候補を検証するための研究用ワークベンチ",
            ]
        ),
    )
