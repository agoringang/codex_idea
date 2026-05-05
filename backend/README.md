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

Run a risk-specific simulation:

```bash
uv run python scripts/backtest_simulator.py --csv data/keiba_history_normalized.csv --risk 72 --bankroll 100000 --output backtests/local-risk72.json
```

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
