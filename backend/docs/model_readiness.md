# UmaLab Model Readiness

This note tracks the seven checks required before running expensive full training or showing model performance in the app.

## Current Status

1. Runner columns are canonicalized.
   - New conversions write `race_no`, `horse_number`, `runner_number`, and `bracket`.
   - Older normalized CSVs where `number` means race number and `gate` means horse number are handled in training and backtest code.
2. Unsafe direct features are excluded from training.
   - `place_odds`, `best_time`, and `last600m` remain in the catalog for display or historical transforms, but are not active training features.
3. Historical features are generated with a shift.
   - Recent horse win/place rate, last-three speed, distance/surface place rate, days since last run, jockey/trainer win rate, and draw bias use only prior rows.
4. Smoke training is available.
   - Use `--race-limit` before the full archive.
   - The smoke output includes split sizes, feature coverage, calibration, market baselines, and `quality_gate`.
5. Market baseline comparison is required.
   - Metrics include constant-rate and market-odds baselines.
   - The current win/place model is an ensemble of calibrated ML probabilities and market-implied probabilities, with market weight capped at `0.75`.
6. Full training is gated.
   - Do not publish a model unless `quality_gate.publishable` is `true` and the following backtest is plausible.
   - Reject results with impossible signs such as `hit_rate=1.0`, `max_drawdown=0`, or ROI based on synthetic exotic payouts.
   - Compare against a market-favorite baseline and a later holdout window using `--skip-races`.
7. Rank, ticket EV, and odds drift are separate workstreams.
   - Strategy code can produce multi-bet recommendations from win/place probabilities.
   - Publishable ticket EV still needs official payout columns.
   - Odds drift still needs time-stamped odds snapshots from pre-race monitoring.
   - Rank distribution should be trained after runner identity and purchase-time features are stable.

## Smoke Commands

```bash
uv run python scripts/train_production.py \
  --csv data/keiba_history_normalized.csv \
  --output-dir models/racequant-smoke \
  --race-limit 500

uv run python scripts/backtest_simulator.py \
  --csv data/keiba_history_normalized.csv \
  --risk 72 \
  --bankroll 100000 \
  --race-limit 500 \
  --model-path models/racequant-smoke/latest.joblib \
  --output backtests/smoke-risk72.json
```

The simulator defaults to a selective purchase filter:

- `--min-edge 0.12`
- `--min-probability 0.20`
- `--max-odds 40`
- `--max-edge 0.8`
- `--limit 3`

To test a later window:

```bash
uv run python scripts/backtest_simulator.py \
  --csv data/keiba_history_normalized.csv \
  --risk 72 \
  --bankroll 100000 \
  --skip-races 100000 \
  --model-path models/racequant/latest.joblib \
  --output backtests/holdout-risk72.json
```

## Full Training

```bash
uv run python scripts/train_production.py \
  --csv data/keiba_history_normalized.csv \
  --output-dir models/racequant
```

Run this only after the smoke model passes the gate. After full training, run backtests for several risk levels before copying any metrics into the Web UI.
