# UmaLab foundation rebuild

## Problem

The app should not keep rich historical racing data loaded in memory. Historical data is an asset, but the API and frontend should only read what they need.

## New architecture

```text
backend/data/raw/          # original CSV/HTML/export files, not committed
backend/data/normalized/   # clean parquet tables
backend/data/features/     # model-ready parquet tables
backend/models/            # joblib artifacts
backend/backtests/         # evaluation outputs
```

## Local workflow

```bash
cd backend
uv sync

# 1. Put your collected CSV here:
# backend/data/raw/race_history.csv

# 2. Convert CSV to normalized parquet
uv run python scripts/ingest_csv.py \
  --csv data/raw/race_history.csv \
  --output-name runners

# 3. Build model features
uv run python scripts/build_features.py \
  --input-table runners.parquet \
  --output-table runners_features.parquet

# 4. Train baseline win model
uv run python scripts/train_win_model.py \
  --feature-table runners_features.parquet \
  --target-column is_win

# 5. Start API
uv run uvicorn app.main:app --reload --port 8000
```

## Important principle

Do not train on information unavailable before the betting cutoff.

Final result, final odds, payout, and finishing time are labels/evaluation data, not pre-race features.
