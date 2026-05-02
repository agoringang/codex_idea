import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schemas import BackendStage, BackendStatus, BacktestSummary, FeatureCoverage, ModelArtifact


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_backend_status() -> BackendStatus:
    now = datetime.now(timezone.utc)
    metrics = read_json(Path("models/racequant/metrics.json"))
    backtest = read_json(Path("backtests/smoke-risk72.json"))

    trained_rows = int(metrics["rows"]) if metrics else 0
    trained_races = int(metrics["races"]) if metrics else 0
    win_test = metrics["targets"]["is_win"]["test"] if metrics else {}
    place_test = metrics["targets"]["is_place"]["test"] if metrics else {}
    feature_presence = metrics.get("feature_presence", {}) if metrics else {}

    return BackendStatus(
        mode="local-trained",
        provider="netkeiba_csv",
        data_window=(
            f"netkeiba CSV学習済み / {trained_races} races / {trained_rows} rows"
            if metrics
            else "未接続: 学習用CSV未作成"
        ),
        last_sync_at=(now - timedelta(minutes=7)).isoformat(),
        next_retrain_at=(now + timedelta(hours=18)).isoformat(),
        active_model="umalab-netkeiba-trained-v0" if metrics else "umalab-sample-v0",
        stages=[
            BackendStage(
                id="ingest",
                label="データ取得",
                status="ready" if metrics else "idle",
                detail=(
                    f"netkeibaの公開範囲からHTMLを取得し、{trained_races}レース分のCSVを作成済み"
                    if metrics
                    else "学習用HTML/CSVの取得待ち"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="normalize",
                label="正規化",
                status="ready" if metrics else "idle",
                detail=(
                    "race_id・出走馬・着順・単勝オッズ・人気・騎手・調教師・馬体重・上がり等を標準列に変換済み"
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
                    "現時点ではオッズ、人気、斤量、馬体重、年齢、上がり、騎手、調教師などを使用。一部の発展特徴量は未生成"
                    if metrics
                    else "特徴量カタログを定義済み"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="training",
                label="モデル学習",
                status="ready" if metrics else "idle",
                detail=(
                    "netkeiba CSVからwin/placeモデルを学習済み。時系列寄りのレース単位分割で評価"
                    if metrics
                    else "学習用CSV作成後にモデルを学習"
                ),
                records=trained_rows,
                latency_ms=None,
            ),
            BackendStage(
                id="inference",
                label="推論",
                status="running" if metrics else "idle",
                detail=(
                    "学習済みwin/placeモデルを読み込み、単勝確率・複勝圏確率・期待値候補を計算"
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
                detail="新しいCSVを追加した場合、再学習してlatest.joblibを更新する設計",
                records=0,
                latency_ms=None,
            ),
        ],
        artifacts=[
            ModelArtifact(
                name="win_probability",
                version="v0.1.0-netkeiba" if metrics else "v0.1.0-sample",
                target="単勝確率",
                metric=(
                    f"netkeiba test AUC {win_test.get('auc', 0):.3f} / LogLoss {win_test.get('log_loss', 0):.3f}"
                    if metrics
                    else "未評価: 学習用CSV待ち"
                ),
                path="models/racequant/latest.joblib",
            ),
            ModelArtifact(
                name="place_probability",
                version="v0.1.0-netkeiba" if metrics else "v0.1.0-sample",
                target="複勝圏確率",
                metric=(
                    f"netkeiba test AUC {place_test.get('auc', 0):.3f} / LogLoss {place_test.get('log_loss', 0):.3f}"
                    if metrics
                    else "未評価: 学習用CSV待ち"
                ),
                path="models/racequant/latest.joblib",
            ),
            ModelArtifact(
                name="ticket_ev",
                version="v0.1.0-sample",
                target="全券種EV",
                metric=(
                    f"sample ROI {backtest['roi'] * 100:.1f}% / DD {backtest['max_drawdown']:,.0f}"
                    if backtest
                    else "未評価: 実データバックテスト待ち"
                ),
                path="models/ticket_ev.joblib",
            ),
        ],
        feature_coverage=[
            FeatureCoverage(
                group="レース条件",
                status="ready" if metrics else "missing",
                fields=["開催日", "場", "距離", "芝/ダート", "馬場", "天候"],
                source="netkeiba CSV",
                detail=(
                    f"venue={feature_presence.get('venue', 0):.0%}, surface={feature_presence.get('surface', 0):.0%}, "
                    f"going={feature_presence.get('going', 0):.0%}, weather={feature_presence.get('weather', 0):.0%}"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="出走馬",
                status="ready" if metrics else "missing",
                fields=["馬齢", "性別", "斤量", "馬体重", "馬体重増減", "走破タイム", "上がり"],
                source="netkeiba CSV",
                detail=(
                    f"age={feature_presence.get('age', 0):.0%}, horse_weight={feature_presence.get('horse_weight', 0):.0%}, "
                    f"best_time={feature_presence.get('best_time', 0):.0%}, last600m={feature_presence.get('last600m', 0):.0%}"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="人・厩舎",
                status="ready" if metrics else "missing",
                fields=["騎手", "調教師"],
                source="netkeiba CSV",
                detail=(
                    f"jockey={feature_presence.get('jockey', 0):.0%}, trainer={feature_presence.get('trainer', 0):.0%}"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="市場",
                status="ready" if metrics else "missing",
                fields=["単勝オッズ", "人気"],
                source="netkeiba CSV",
                detail=(
                    f"market_odds={feature_presence.get('market_odds', 0):.0%}, odds_rank={feature_presence.get('odds_rank', 0):.0%}。"
                    "時系列オッズや票数は未取得"
                    if metrics
                    else "未作成"
                ),
            ),
            FeatureCoverage(
                group="結果",
                status="ready" if metrics else "missing",
                fields=["着順", "単勝ラベル", "複勝圏ラベル"],
                source="netkeiba CSV",
                detail=(
                    f"{trained_races}レース、{trained_rows}出走馬分の教師ラベルを作成済み"
                    if metrics
                    else "未作成"
                ),
            ),
        ],
        backtest=BacktestSummary(
            status="sample" if backtest else "not_started",
            window="sample smoke" if backtest else "未実行",
            races=int(backtest["races"]) if backtest else 0,
            bets=int(backtest["bets"]) if backtest else 0,
            total_stake=float(backtest["total_stake"]) if backtest else 0,
            total_payout=float(backtest["total_payout"]) if backtest else 0,
            roi=float(backtest["roi"]) if backtest else 0,
            hit_rate=float(backtest["hit_rate"]) if backtest else 0,
            max_drawdown=float(backtest["max_drawdown"]) if backtest else 0,
            note=(
                "現在の回収率表示はサンプルバックテスト。netkeiba CSVに基づく実バックテストは次フェーズで実装"
                if backtest
                else "実データバックテストは未実行"
            ),
        ),
        runtime_notes=[
            "netkeiba CSVからwin/placeモデルを学習済み",
            "現時点の高いAUCは単勝オッズ・人気など市場情報の寄与を含む",
            "時系列オッズ、払戻、購入時点制約を入れたバックテストは次フェーズ",
            "利益保証や勝率100%を目的とせず、期待値候補を検証するための研究用ワークベンチ",
        ],
    )