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

Train the current win/place production baseline:

```bash
uv run python scripts/train_production.py --csv data/keiba_history_normalized.csv --output-dir models/racequant
```

Smoke-train before spending time on the full archive:

```bash
uv run python scripts/train_production.py --csv data/keiba_history_normalized.csv --output-dir models/racequant-smoke --race-limit 500
```

Use a model for the public UI only when `quality_gate.publishable` is `true`. The production pipeline excludes direct `place_odds`, final time, and final sectional values from training, adds shifted historical features, and reports constant/market-odds baselines.

Run a risk-specific simulation:

```bash
uv run python scripts/backtest_simulator.py --csv data/keiba_history_normalized.csv --risk 72 --bankroll 100000 --output backtests/local-risk72.json
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
curl http://localhost:8000/races
curl http://localhost:8000/live/tokyo-20260506-11
```

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
