# RaceQuant Data Pipeline

## Goal

Train on roughly 20 years of historical racing data, then keep the system current with race-week entries, live odds snapshots, final results, and payouts.

## Source Strategy

Primary source:

- JRA-VAN Data Lab. via JV-Link for JRA historical and realtime data.

Fallback/import source:

- CSV or parquet exports with the RaceQuant standard schema.

## Raw To Feature Flow

1. `raw/jravan/`
   - Original race, runner, odds, result, payout, horse, jockey, trainer, pedigree, and training records.
2. `normalized/`
   - One row per race runner.
   - One row per odds snapshot per race runner or ticket pool.
   - One row per confirmed payout.
3. `features/`
   - Runner form, speed figures, distance/surface aptitude, jockey/trainer form, pace map, draw bias, market movement.
4. `models/`
   - Win probability model.
   - Place probability model.
   - Finish-rank distribution model.
   - Ticket expected-value model for all bet types.
5. `backtests/`
   - Time-split simulations using only odds snapshots available before cutoff.

## Feature Catalog

Use every field that is legally and practically available before the simulated purchase cutoff.

- Race: date, venue, meeting, race number, class, grade, distance, surface, going, weather, field size, barrier draw.
- Runner: horse id, age, sex, carried weight, body weight, body weight delta, running style, days since last run.
- Performance: recent finishes, speed figures, best time, last-three average speed, final 600m, distance/surface aptitude.
- People: jockey, trainer, owner, breeder, jockey win/place rates, trainer win/place rates, jockey-trainer pair stats.
- Pedigree: sire, dam sire, family line, distance/surface aptitude scores.
- Market: win/place odds, all exotic pools, odds rank, odds movement, ticket pool share, time-series odds snapshots.
- Race-week changes: scratches, jockey changes, weather changes, going changes, body weight announcement.
- Labels: finish position, margin, running time, final sectional, payouts, refunds.

Do not train on data that was not available at the simulated purchase time. For example, final odds or final race result fields are labels/evaluation inputs, not pre-race features for an earlier cutoff.

Current training exclusions:

- `place_odds`: the local normalized export is not reliable enough to use as a pre-race feature.
- `best_time`, `last600m`: final race-result values, usable only after shifting into historical aggregates.

Current derived features:

- canonical `runner_number`, `bracket`, and `field_size`
- race-normalized `market_win_probability` and estimated `market_place_probability`
- shifted horse recent win/place rate, last-three speed, days since last run
- shifted jockey/trainer win rate, distance/surface aptitude, and draw bias

## Bet Type Coverage

Single-race tickets:

- win
- place
- support
- bracket_quinella
- quinella
- wide
- exacta
- trio
- trifecta

Multi-race ticket:

- win5

WIN5 should be modeled as a portfolio problem across five designated races, not as a single-race recommendation.

## Continuous Update Loop

Race week:

1. Sync entries and race cards.
2. Recompute pre-race features.
3. Pull odds snapshots on a schedule.
4. Refresh recommendations with the latest odds.

Live monitoring:

1. Detect finalized race cards and mark the race as `parsed`.
2. Store odds snapshots and calculate changes from the previous snapshot.
3. Detect scratches and remove those runners from recommendations.
4. Pull official results and payout data.
5. Set settlement status to `hit`, `miss`, `refund`, or `pending`.

After race finalization:

1. Sync official result and payout.
2. Append labels and settlement records.
3. Re-run daily backtest checks.
4. Queue model retraining if drift or enough new data is detected.

Retraining:

- Use time-based validation splits.
- Never train on future odds or final odds when simulating earlier purchase cutoffs.
- Calibrate probabilities before using them for expected-value betting.
- Promote a model only if it improves ROI, drawdown, and calibration on recent holdout races.
- Check `quality_gate.publishable` before using a model in the public UI.

## Backtest

The simulator entry point is:

```bash
cd backend
uv run python scripts/backtest_simulator.py --csv data/race_history.csv --risk 72 --bankroll 100000
```

The normalized CSV needs at least `race_id`, `finish_position`, and one runner-number source such as `number`, `gate`, `runner_number`, or `horse_number`. More columns from the feature catalog improve model quality. The output includes races, bets, total stake, total payout, ROI, hit rate, max drawdown, bet types, payout mode, and diagnostics.

Current default betting filters are deliberately conservative:

- `--min-edge 0.12`
- `--min-probability 0.20`
- `--max-odds 40`
- `--max-edge 0.8`
- `--limit 3`

The summary also reports skipped races, bet race rate, bet-type breakdowns, edge-band breakdowns, and a market-favorite win baseline. Use `--skip-races` for holdout checks; an in-sample ROI spike is not publishable evidence.

Current repo status: the local normalized keiba data has no official exotic payout columns. Default simulations therefore use win/place only. Exotic-bet ROI is publishable only after official payout columns are ingested; `--synthetic-exotics` is for exploratory estimates.
