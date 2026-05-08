# UmaLab model redesign 2026

## Why the current predictions drift toward odds

The current public prediction can still look like popularity order because the app has two strong market anchors:

- `baseWin` is derived from `1 / market_odds` when live model output is missing or incomplete.
- The production training flow blends calibrated ML probability with market-implied probability.
- Several non-market columns are not continuously populated yet: `training_score`, `bloodline_score`, `paddock_score`, `lap_3f`, `lap_4f`, `ticket_pool_share`, and true time-series `odds_delta`.

This is not only a UI issue. If the model mostly learns the market, it can be well calibrated while still failing to find profitable deviations from the market.

## Model suite to compare

Use multiple models with separate responsibilities instead of one all-purpose winner model.

1. Market baseline
   - Convert win/place odds to implied probabilities.
   - Apply favorite-longshot bias correction and calibration.
   - This is the benchmark. Any publishable model must beat it on 2026 holdout ROI and calibration.

2. Non-market horse model
   - Train without direct odds columns: no `market_odds`, `market_win_probability`, `market_place_probability`, `odds_rank`, or final payout labels.
   - Features: horse form, distance/surface aptitude, draw, pace, jockey/trainer form, body weight delta, training, pedigree, going, venue.
   - Candidate algorithms: LightGBM/CatBoost/XGBoost ranker, HistGradientBoosting, calibrated logistic/SGD baseline.

3. Blended probability model
   - Inputs: market baseline probability, non-market model probability, and market movement features available at the purchase cutoff.
   - Use a simple meta-model first, then tune market weight separately for JRA and NAR.
   - Output must be calibrated before expected-value betting.

4. Finish-rank distribution model
   - Predict top1/top2/top3 probabilities and pair/trio compatibility, not only win/place.
   - Use learning-to-rank for order and a calibrated probability layer for ticket construction.

5. Upset/race volatility model
   - Race-level labels:
     - favorite finishes outside top 3
     - winner odds >= 8.0
     - trio/trifecta payout in the top quartile for the market/venue
     - top-three contains at least one horse outside top 5 popularity
   - Output: `買い候補あり`, `直前確認`, `見送り`, or `情報不足`.
   - This should decide whether wider bets are justified; it should not be derived from a user risk button.

6. Ticket expected-value model
   - Train/evaluate with official payout columns only.
   - Do not use synthetic exotic payouts for public ROI.
   - Optimize ticket portfolios by expected profit rate, hit probability, max drawdown, and bet rate.

## JRA/NAR split

Train and evaluate JRA and NAR separately by default.

- JRA and NAR differ in venues, field composition, class structure, pools, surface patterns, and data availability.
- A shared model can still be tested as a third option, but it must include `market` and venue features and must be judged on JRA/NAR holdouts separately.

## Preprocessing rules

Every training row needs an `as_of_time` concept. A feature is usable only if it existed before that cutoff.

- Canonical identity: `race_id`, `race_date`, `market`, `venue`, `race_no`, `horse_id`, `horse_number`, `bracket`.
- Shift all history features by race date per horse/jockey/trainer.
- Normalize within race: odds rank, probability sum, draw position, field size, relative weight.
- Store odds snapshots, not only final odds:
  - opening odds
  - latest odds at prediction time
  - 60/30/10/5 minute deltas
  - volatility and rank changes
  - pool share changes where available
- Store official payouts as separate settlement labels:
  - win/place/wide/quinella/exacta/trio/trifecta
  - refunds/scratches
  - popularity for each winning combination

## Required data gaps

These columns are high priority because they are not just another version of the odds:

- training workout score and workout course
- paddock score and visible condition flags
- body weight and body weight delta at announcement time
- going/weather changes by time
- lap/pace historical aggregates shifted from prior races
- horse distance/surface/venue aptitude
- jockey/trainer recent form and pair statistics
- odds snapshots and late odds movement
- official exotic payouts for every settled race

## Current CSV coverage and missing inputs

`backend/data/keiba_history_with_2026.csv` already has the columns needed for a basic model:

- race identity: `race_id`, `race_date`, `venue`, `race_no`, `distance`, `surface`, `going`, `weather`, `field_size`
- runner identity/form: `horse_name`, `runner_number`, `bracket`, `sex`, `age`, `jockey`, `trainer`, `sire`, `dam_sire`
- market/result: `market_odds`, `odds_rank`, `finish_position`, `payout_*`, `payouts_json`
- body/time placeholders: `start_time`, `post_time`, `horse_weight`, `horse_weight_diff`
- feature placeholders: `odds_delta`, `ticket_pool_share`, `training_score`, `bloodline_score`, `paddock_score`, `lap_3f`, `lap_4f`

`scripts/enrich_netkeiba_2026_features.py` creates `netkeiba_2026_enriched.csv`
by joining 2026 rows to 2025-and-earlier history only. Current enriched 2026
coverage:

- market implied probabilities: 100.0%
- horse recent win/place, days since last run, prior 3F proxy: 66.9%
- horse weight delta: 99.2%
- jockey win rate: 41.6% overall, 99.2% on JRA rows
- trainer win rate: 43.0% overall, 98.7% on JRA rows after name normalization
- draw bias: 8.5% overall, 31.3% on JRA rows
- bloodline score: 0.0% because the scraped 2026 CSV currently lacks sire and dam-sire values

What is still weak or missing:

- Stable horse IDs, jockey IDs, trainer IDs, and race class IDs. Names alone cause joins to drift.
- True pre-race odds snapshots. The CSV mostly has one odds value, so late movement cannot be learned reliably.
- Pre-race exotic odds or pool distributions for wide, quinella, exacta, trio, and trifecta. Without these, exotic ticket odds are estimates.
- Raw workout data before score conversion: date, course, 4F/5F/6F, final 1F, rank, training partner.
- Paddock observations with timestamp: gait, sweat, focus, body tone, recommendation rank.
- Sectional/lap history shifted from previous races. Current `lap_3f`/`lap_4f` are placeholders or sparse.
- Race class, prize, track condition transition, rail position, and weather/going update timestamps.
- Scratches, jockey changes, weight announcement time, and refund flags.
- Purchase cutoff timestamp for each saved prediction. Without it, ROI can be contaminated by post-result or final-odds information.

## Current implementation status

- Removed the public `support` ticket type. Old records are treated as unsupported legacy data and are excluded from settlement totals.
- Public settlement now pays only when an exact official payout is available:
  - win/place can use runner-level official payout.
  - exotic tickets require a matching `payouts_json` selection.
  - race-level fallback payout columns are no longer used for public ROI.
- Place odds are no longer derived as a large fraction of win odds. Missing live place odds now use a conservative capped estimate so longshots cannot create fake EV.
- `scripts/verify_prediction_integrity.py` checks that non-official payout sources never produce positive payout and that unsupported ticket types do not reach the result UI.
- `scripts/train_upset_classifier.py` trains a separate race-level upset classifier and writes `models/upset_classifier/upset_classifier_metrics.json`.
  - Latest run: JRA holdout 2026 AUC 0.6955, high-upset-alert actual rate 81.5%.
  - NAR is skipped because the current pre-2026 training CSV is central-only.

## Validation gates

Use the same chronological rule for all model candidates:

- train: data through 2025
- calibration: late 2025 or the tail of the train period
- holdout: 2026 only
- report JRA and NAR separately

Required metrics:

- prediction: AUC, Brier, log loss, ECE
- ranking: NDCG@3, top1 hit, top3 containment, Spearman/Kendall where useful
- betting: official-payout ROI, profit rate, hit rate, bet rate, max drawdown, average stake, skipped races
- sanity: market baseline, favorite baseline, no synthetic payout ROI, no generated-after-result records in public stats

## Implementation order

1. Lock payout/settlement correctness.
2. Build odds snapshot and feature snapshot tables.
3. Add non-market model experiment mode.
4. Add JRA/NAR-separated holdout reports.
5. Add upset model labels and training script.
6. Add model comparison output for the UI/admin view.
7. Promote only if 2026 holdout beats the market baseline with official payouts.

## References used

- JRA FAQ: payout calculation and betting method list: https://jra.jp/faq/pop03/1_17.html
- NAR official refund page format: https://www.keiba.go.jp/KeibaWeb_IPAT/TodayRaceInfo/RefundMoneyList_ipat?k_babaCode=32&k_raceDate=2025%2F06%2F26
- Snowberg and Wolfers, favorite-longshot bias: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1597604
- Horse race rank prediction using learning-to-rank approaches: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003075791
- Last-minute dynamics in Japanese parimutuel betting: https://arxiv.org/abs/2509.14645
- Odds-to-probability conversion and favorite-longshot-bias adjusted GLM: https://arxiv.org/abs/2604.17194
- Japanese horse-racing odds dynamics: https://arxiv.org/abs/2503.16470
