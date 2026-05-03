# RaceQuant Backend

FastAPI service for horse-racing probability, expected value, and stake sizing.

The baseline model code is intentionally conservative:

- Normalize each runner into a win probability.
- Compare model probability with market odds.
- Expand recommendations across win, place, support, bracket quinella, quinella, wide, exacta, trio, and trifecta.
- Use `risk_level` as a risk-return preference: low values rank hit-rate bets higher, high values rank higher-payout bets higher.
- Cap stake size with fractional Kelly and per-bet exposure limits.
- Treat WIN5 as a multi-race portfolio model.

No betting model can guarantee profit.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

```bash
curl http://localhost:8000/status
curl http://localhost:8000/live/kyoto-20260503-11
```

See `docs/data_pipeline.md` for the 20-year historical data and continuous retraining plan.

## Production Training

Real training needs a normalized historical CSV from JRA-VAN Data Lab. or a compatible licensed export. JRA-VAN's official product pages describe data from 1986 onward, so ask for the maximum provider window rather than assuming a full 50 years exists.

```bash
uv run python scripts/train_production.py --csv data/race_history.csv --output-dir models/racequant
uv run python scripts/backtest_simulator.py --csv data/race_history.csv --risk 72 --bankroll 100000
```

Pipeline smoke test with synthetic data:

```bash
uv run python scripts/generate_synthetic_history.py --races 1200 --output data/smoke_history.csv
uv run python scripts/train_production.py --csv data/smoke_history.csv --output-dir models/racequant
uv run python scripts/backtest_simulator.py --csv data/smoke_history.csv --risk 72 --bankroll 100000
```

The API automatically uses `models/racequant/latest.joblib` when present. Override with `RACEQUANT_MODEL_PATH=/path/to/model.joblib`.

## netkeiba Import

Use this only for private research, public pages, and low-rate access. Do not use login-only or paid pages, do not bypass rate limits, and keep cached data private.

Generate daily race-list URLs:

```bash
uv run python scripts/netkeiba_generate_list_urls.py --start-year 2006 --end-year 2026 --output data/netkeiba_list_urls.txt
```

Fetch daily list HTML slowly, then extract concrete race URLs:

```bash
uv run python scripts/netkeiba_fetch.py --url-file data/netkeiba_list_urls.txt --output-dir raw/netkeiba/list_html --manifest raw/netkeiba/list_manifest.csv --delay-seconds 10
uv run python scripts/netkeiba_extract_race_urls.py --html-dir raw/netkeiba/list_html --output data/netkeiba_race_urls.txt
```

Fetch cached race-result HTML slowly:

```bash
uv run python scripts/netkeiba_fetch.py --url-file data/netkeiba_race_urls.txt --output-dir raw/netkeiba/html --manifest raw/netkeiba/race_manifest.csv --delay-seconds 10
```

Or start the full staged collector in the background:

```bash
uv run python scripts/netkeiba_start_collect.py --start-year 2006 --end-year 2026 --end-date 2026-05-02 --delay-seconds 10 --train-after
uv run python scripts/netkeiba_status.py
tail -f runtime/netkeiba_collect.log
```

Parse cached HTML to normalized CSV:

```bash
uv run python scripts/netkeiba_parse.py --html-dir raw/netkeiba/html --output data/netkeiba_race_history.csv
```

Convert local `data/keiba_data/*.CSV` (cp932/Shift_JIS, fixed 52 columns) to a normalized training CSV:

```bash
uv run python scripts/convert_keiba_data.py --input-dir data/keiba_data --output data/keiba_history_normalized.csv
```

Then train:

```bash
uv run python scripts/train_production.py --csv data/netkeiba_race_history.csv --output-dir models/racequant
```
