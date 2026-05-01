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
