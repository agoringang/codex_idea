# UmaLab

UmaLab は、これから行われる競馬レースをAIで予測し、券種別の期待値、軍資金配分、バックテスト回収率、直前オッズ監視を一画面で扱う予想ワークベンチです。

利益保証や的中保証は目的にしません。過去データで検証した根拠を見ながら、買う/見送る判断を安定させるためのアプリです。

## Current Direction

- 複数AIモデル: win/place、着順分布、ticket EV、odds drift、ensemble
- 複数券種: 単勝、複勝、枠連、馬連、ワイド、馬単、3連複、3連単、WIN5
- カレンダー: 中央競馬と地方競馬を同じ画面で表示
- リスク/軍資金: スライダーと軍資金から購入点数、券種、金額を変更
- 実績: シミュレーション回収率、的中率、最大ドローダウンをWebに表示
- ライブ: パドック中から締切直前までオッズ変動を監視
- データ: `backend/data/keiba_data` の中央全レースCSVを学習元にする

詳細設計は [docs/architecture.md](docs/architecture.md) を参照してください。

## Directory

```text
app/                 Next.js UI
backend/app/         FastAPI, schemas, prediction logic
backend/scripts/     CSV変換、学習、バックテスト、SVG出力
backend/data/        ローカルデータ置き場（Git管理外）
backend/models/      学習済みモデル（Git管理外）
backend/backtests/   シミュレーション結果（Git管理外）
docs/                アプリ全体の設計メモ
```

## Frontend

```bash
npm install
npm run dev
```

http://localhost:3000 を開きます。

## Backend With uv

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

確認:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/status
curl http://localhost:8000/status/product
curl http://localhost:8000/races
```

## Local Data Pipeline

中央の既存CSVを標準CSVへ変換:

```bash
cd backend
uv run python scripts/convert_keiba_data.py \
  --input-dir data/keiba_data \
  --output data/keiba_history_normalized.csv
```

学習:

```bash
uv run python scripts/train_production.py \
  --csv data/keiba_history_normalized.csv \
  --output-dir models/racequant
```

慎重に進める場合は、先に小規模ゲートを通します:

```bash
uv run python scripts/train_production.py \
  --csv data/keiba_history_normalized.csv \
  --output-dir models/racequant-smoke \
  --race-limit 500
```

出力の `quality_gate.publishable` が `true` になってからフル学習結果をWeb表示に使います。現在の学習は `place_odds`、走破タイム、上がりを直接特徴量に使わず、市場確率と履歴特徴量を使う構成です。

バックテスト:

```bash
uv run python scripts/backtest_simulator.py \
  --csv data/keiba_history_normalized.csv \
  --risk 72 \
  --bankroll 100000 \
  --output backtests/local-risk72.json
```

バックテストはデフォルトで `min_edge=0.12`、`min_probability=0.20`、`max_odds=40`、`max_edge=0.8` の保守的な購入フィルタを使います。`--skip-races` で学習期間の後ろだけを検証できます。

現在の `keiba_history_normalized.csv` には馬連・3連単などの公式払い戻し列がないため、デフォルトでは単勝・複勝のみを市場オッズベースで検証します。3連系まで仮オッズで試す場合だけ `--synthetic-exotics` を付けてください。

READMEや共有用のSVGカード出力:

```bash
uv run python scripts/render_prediction_card.py \
  --metrics models/racequant/metrics.json \
  --backtest backtests/local-risk72.json \
  --output ../public/model-output.svg
```

## API Surface

- `GET /health`
- `GET /status`
- `GET /status/product`
- `GET /races`
- `GET /live/{race_id}`
- `GET /history`
- `POST /predict`
- `POST /predict/basic`
- `POST /ingest/csv`
- `POST /features/runners`
- `POST /train`
- `POST /jobs/sync`
- `POST /jobs/train`
- `POST /jobs/live-polling`

## Data Policy

`backend/data/**`, `backend/models/**`, `backend/backtests/**` はGit管理外です。`backend/data/keiba_data` の実データはローカル学習に使い、リポジトリへは載せません。
