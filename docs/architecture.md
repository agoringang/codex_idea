# UmaLab Architecture

UmaLab は、これから行われるレースを対象に、複数のAIモデルで勝率、複勝圏確率、着順分布、券種別期待値、購入金額を出す予想ワークベンチです。netkeiba.com の情報閲覧体験を土台にしつつ、予測、資金管理、回収率検証、直前オッズ監視までを一画面で扱う設計にします。

競馬で利益や的中を保証するモデルは作れません。このアプリは「買う/見送る根拠を数値化し、過去データで検証できる状態」を目的にします。

## Product Surface

- 開催カレンダー: JRA と地方競馬を同じUIで扱う。
- レース予測: 単勝、複勝、枠連、馬連、ワイド、馬単、3連複、3連単、WIN5へ展開する。
- リスク調整: ユーザーがリスク許容度と軍資金を選び、券種、点数、購入上限を変える。
- 実績表示: シミュレーション回収率、的中率、最大ドローダウン、対象レース数を表示する。
- 直前監視: パドック中から締切前まで、オッズ変動、取消、馬体重、気配メモを取り込み、購入候補を再計算する。
- README用出力: モデル評価とバックテスト結果をSVGカードとして出力する。

## Data Flow

1. Raw cache
   - 中央競馬: `backend/data/keiba_data/*.CSV`
   - 地方競馬: 今後 `backend/data/raw/nar/` にアダプタを追加
   - ライブ情報: 出馬表、オッズ、取消、結果、払戻を時刻付きで保存
2. Normalize
   - `backend/scripts/convert_keiba_data.py` でローカルCSVを標準列へ変換
   - 変換後CSVやparquetは `backend/data/**` に置き、Gitには載せない
3. Feature Store
   - `backend/data/features/` に学習用特徴量を保存
   - 馬、騎手、調教師、血統、コース、馬場、オッズ順位、オッズ変化を分離して拡張する
4. Model Registry
   - `backend/models/` に `win/place/rank/ticket_ev/odds_drift` の成果物を保存
   - 生成物はGitに載せない
5. Backtest
   - `backend/backtests/` にリスク値、軍資金、券種別の結果を保存
   - Webは最新バックテストを読み、回収率とリスク指標を表示する
6. API
   - FastAPI はカレンダー、予測、ライブ監視、学習、バックテスト状態を返す
7. Frontend
   - Next.js は予測画面、リスク/軍資金操作、実績、ライブアラートを表示する

## Model Plan

- `win/place`: 単勝確率と複勝圏確率。まずは現在の `train_production.py` を中核にする。
- `rank_distribution`: 着順分布。馬連、馬単、ワイド、3連複、3連単に必要。
- `ticket_ev`: 券種ごとの控除率、的中確率、期待値、購入点数を出す。
- `odds_drift`: パドック中のオッズ変化から過熱、妙味、見送りを検知する。
- `ensemble`: 上記の結果を統合し、リスク許容度に合わせて最終推薦を出す。

## Repository Policy

Tracked:

- `app/**`: Next.js UI
- `backend/app/**`: FastAPI と推論ロジック
- `backend/scripts/**`: 変換、学習、バックテスト、画像出力
- `backend/docs/**`, `docs/**`: 設計と運用メモ
- `backend/pyproject.toml`, `backend/uv.lock`: uv 管理

Ignored:

- `backend/data/**`: ローカルデータ、正規化CSV、特徴量
- `backend/models/**`: 学習済みモデル
- `backend/backtests/**`: バックテスト出力
- `.venv/`, `backend/.venv/`, `.next/`, `node_modules/`, `__pycache__/`

## Near-Term Implementation

1. `keiba_data` を標準CSVへ変換し、欠損率と列品質を確認する。
2. 単勝/複勝モデルを再学習し、未来情報リークを避けた時系列分割に固定する。
3. リスク別バックテストを `risk=20/50/80` で保存する。
4. Webが `GET /status/product` とバックテストJSONを表示する。
5. 地方競馬用の `ProviderAdapter` を追加する。
6. ライブオッズスナップショットの保存形式を決める。
