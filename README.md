# UmaLab

Python ML で競馬の勝率・期待値・賭け金を計算し、Next.js で確認する予想ワークベンチです。

重要: 競馬で「絶対に勝てる」「勝率100%」は作れません。このアプリは回収率100%超を狙う候補を、バックテスト・期待値・資金上限で検証するためのものです。

## Frontend

```bash
npm install
npm run dev
```

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

サンプル推論:

```bash
curl http://localhost:8000/status
curl http://localhost:8000/live/kyoto-20260503-11

curl -X POST http://localhost:8000/predict \
  -H 'content-type: application/json' \
  --data @data/sample_race.json
```

計画ジョブ:

```bash
curl -X POST http://localhost:8000/jobs/sync \
  -H 'content-type: application/json' \
  -d '{"provider":"jravan","years":20,"include_realtime":true}'

curl -X POST http://localhost:8000/jobs/train \
  -H 'content-type: application/json' \
  -d '{"start_year":2006,"end_year":2026,"target":"rank","include_odds_snapshots":true}'

curl -X POST http://localhost:8000/jobs/live-polling \
  -H 'content-type: application/json' \
  -d '{"provider":"simulation","interval_seconds":60,"race_ids":["kyoto-20260503-11"]}'
```

## Training

CSV に `speed`, `stamina`, `pace`, `condition`, `market_odds`, `distance`, `carried_weight`, `days_since_last_run`, `venue`, `surface`, `going`, `jockey`, `trainer`, `running_style`, `is_win` を用意します。

```bash
cd backend
python scripts/train_baseline.py --csv data/race_history.csv --output models/baseline.joblib
python scripts/train_production.py --csv data/race_history.csv --output-dir models/racequant
```

`models/racequant/latest.joblib` が存在する場合、FastAPI の推論はその学習済み `win/place` モデルを使います。未作成の場合はヒューリスティック推論へフォールバックします。

netkeibaの公開ページを個人研究用にCSV化する場合:

```bash
cd backend
uv run python scripts/netkeiba_generate_list_urls.py --start-year 2006 --end-year 2026 --output data/netkeiba_list_urls.txt
uv run python scripts/netkeiba_fetch.py --url-file data/netkeiba_list_urls.txt --output-dir raw/netkeiba/list_html --manifest raw/netkeiba/list_manifest.csv --delay-seconds 10
uv run python scripts/netkeiba_extract_race_urls.py --html-dir raw/netkeiba/list_html --output data/netkeiba_race_urls.txt
uv run python scripts/netkeiba_fetch.py --url-file data/netkeiba_race_urls.txt --output-dir raw/netkeiba/html --manifest raw/netkeiba/race_manifest.csv --delay-seconds 10
uv run python scripts/netkeiba_parse.py --html-dir raw/netkeiba/html --output data/netkeiba_race_history.csv
```

ログイン後・有料ページ・通信制限回避は対象外です。取得CSVは公開せず、学習用のローカルファイルとして扱います。

## Data Phase

実データ学習は `backend/docs/data_pipeline.md` の流れで進めます。

- JRA-VAN/CSVから取得可能な最大年数の過去データを `raw/` に保存
- JRA-VAN公式データは1986年以降が中心。50年分は提供元に存在する範囲までに制限されます
- レース、出走馬、オッズスナップショット、払戻、結果を正規化
- 単勝・複勝確率を学習
- 順位分布から枠連、馬連、ワイド、馬単、3連複、3連単、WIN5へ展開
- 開催中はオッズを更新し、確定後に結果を追加して再学習

継続更新ループの雛形:

```bash
cd backend
python scripts/retraining_loop.py --once
python scripts/live_update_loop.py --once --race-id kyoto-20260503-11
python scripts/backtest_simulator.py --csv data/race_history.csv --risk 72 --bankroll 100000
```

## Backend Visualization

フロントの「処理フローとモデル状態」パネルは、最終的に FastAPI の `GET /status` と同じ構造を表示します。

- データ同期
- 正規化
- 特徴量生成
- モデル学習
- 推論
- 継続学習
- Model registry
- Realtime loop

ライブ監視では、出馬表確定、オッズ変動、出走取消、公式結果、的中/不的中/返還を `GET /live/{race_id}` で返す想定です。

現時点では実データ20年分を同期済みとは扱いません。バックエンドの `/status` は、特徴量カバレッジとバックテスト状態を `not_started` として返し、CSV/JRA-VAN接続後に実回収率へ更新する前提です。
