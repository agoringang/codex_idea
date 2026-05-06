# UmaLab Backend

FastAPI service for race ingestion, model training, multi-bet prediction, live odds monitoring, and backtest reporting.

Use uv only for the Python environment:

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

## Main Commands

Convert the local central-racing CSV archive:

```bash
uv run python scripts/convert_keiba_data.py --input-dir data/keiba_data --output data/keiba_history_normalized.csv
```

Import manually saved 2026 netkeiba CSV/HTML result tables, including payout
tables when present, and merge them with the existing training archive:

```bash
uv run python scripts/import_netkeiba_exports.py \
  --input-dir data/raw/netkeiba_2026 \
  --output data/netkeiba_2026_normalized.csv \
  --base-csv data/keiba_history_normalized.csv \
  --combined-output data/keiba_history_with_2026.csv
```

Scrape public netkeiba DB race pages for a 2026 date range, cache the HTML, and
then run the same importer automatically:

```bash
uv run python scripts/scrape_netkeiba_2026.py \
  --start-date 2026-01-01 \
  --end-date 2026-05-06 \
  --delay 1.5 \
  --output data/netkeiba_2026_normalized.csv \
  --combined-output data/keiba_history_with_2026.csv
```

Train the current win/place production baseline:

```bash
uv run python scripts/train_production.py --csv data/keiba_history_normalized.csv --output-dir models/racequant
```

Train and validate the current risk-routed model setup with 2025 and older races
as training data and 2026 as the holdout:

```bash
uv run python scripts/experiment_holdout_2026.py \
  --train-csv data/keiba_history_normalized.csv \
  --holdout-csv data/netkeiba_2026_normalized.csv \
  --output-dir models/racequant_holdout_2026
```

When `models/racequant_holdout_2026/holdout_artifact.joblib` exists, inference
uses it by default. Override with `RACEQUANT_MODEL_PATH` if needed.

For Vercel, keep the model artifact out of Git and load it from Blob or another
public file URL:

```bash
npm run upload:model -- backend/models/racequant_holdout_2026/holdout_artifact.joblib
```

Set the printed values in the Vercel project:

```text
RACEQUANT_MODEL_URL=https://...
RACEQUANT_MODEL_SHA256=...
```

At runtime the API downloads the artifact once into `/tmp/umalab-racequant-models`.
Use `RACEQUANT_MODEL_CACHE_DIR` only when you need a different writable cache
directory.

Smoke-train before spending time on the full archive:

```bash
uv run python scripts/train_production.py --csv data/keiba_history_normalized.csv --output-dir models/racequant-smoke --race-limit 500
```

Use a model for the public UI only when `quality_gate.publishable` is `true`. The production pipeline excludes direct `place_odds`, final time, and final sectional values from training, adds shifted historical features, and reports constant/market-odds baselines.

Run a risk-specific simulation:

```bash
uv run python scripts/backtest_simulator.py --csv data/keiba_history_normalized.csv --risk 72 --bankroll 100000 --output backtests/local-risk72.json
```

Run the 2026 holdout simulations used by the product UI:

```bash
uv run python scripts/backtest_simulator.py --csv data/netkeiba_2026_normalized.csv --risk 24 --bankroll 100000 --output backtests/holdout2026-risk24.json
uv run python scripts/backtest_simulator.py --csv data/netkeiba_2026_normalized.csv --risk 52 --bankroll 100000 --output backtests/holdout2026-risk52.json
uv run python scripts/backtest_simulator.py --csv data/netkeiba_2026_normalized.csv --risk 84 --bankroll 100000 --output backtests/holdout2026-risk84.json
```

The simulator now defaults to conservative filters: `min_edge=0.12`, `min_probability=0.20`, `max_odds=40`, `max_edge=0.8`, and `limit=3`. Use `--skip-races` to evaluate a later holdout window instead of the same early races used for smoke training.

By default this simulates win/place only when the CSV has no official exotic payout columns. Use `--synthetic-exotics` only for exploratory, non-publishable exotic-bet estimates.

Render a README/shareable SVG card:

```bash
uv run python scripts/render_prediction_card.py --metrics models/racequant/metrics.json --backtest backtests/local-risk72.json --output ../public/model-output.svg
```

## API

```bash
curl http://localhost:8000/health
curl http://localhost:8000/status
curl http://localhost:8000/status/product
curl 'http://localhost:8000/races?start_date=2026-04-20&end_date=2026-05-20'
curl http://localhost:8000/live/tokyo-20260506-11
```

Prediction history can use Supabase in production. Run `docs/supabase_prediction_history.sql`
in Supabase SQL Editor, then set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
Without those variables the backend falls back to local JSON storage.

Plan sync/train/live jobs:

```bash
curl -X POST http://localhost:8000/jobs/sync \
  -H 'content-type: application/json' \
  -d '{"provider":"csv","years":20,"include_realtime":true,"raw_path":"data/keiba_data"}'

curl -X POST http://localhost:8000/jobs/train \
  -H 'content-type: application/json' \
  -d '{"start_year":2000,"end_year":2025,"target":"rank","include_odds_snapshots":true}'

curl -X POST http://localhost:8000/jobs/live-polling \
  -H 'content-type: application/json' \
  -d '{"provider":"simulation","interval_seconds":60,"race_ids":["tokyo-20260506-11"]}'
```

## Source Layout

- `app/api/`: FastAPI route layer
- `app/core/`: settings and lightweight pipeline schemas
- `app/ml/`: parquet feature generation and simple training endpoints
- `app/model.py`: strategy-level multi-bet prediction
- `app/ml_pipeline.py`: production win/place training pipeline
- `app/data_sources.py`: local race calendar projection from normalized CSV
- `scripts/`: conversion, training, backtesting, live loop, SVG rendering

Generated local files stay outside Git:

- `data/**`
- `models/**`
- `backtests/**`
- `runtime/**`
