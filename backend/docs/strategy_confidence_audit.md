# UmaLab strategy confidence audit

Date: 2026-05-07

## Current confidence

I am not 100% confident that the current product can beat the market yet.
I am confident that the next strategy below is the right direction because it
removes the major ways the app can mislead users: missing data, post-result
prediction leakage, odds-only ranking, synthetic ROI, and incomplete payouts.

The product must not claim profitable performance until the gates in this file
pass on official pre-race predictions.

## Fixed in this pass

- 2026 JRA race cards are available from Blob-backed CSV.
- The API no longer reads only the final 32 MB for 2026 CSVs; the full enriched
  2026 file is read, so January to early March JRA dates no longer disappear.
- 2026-01-01 to 2026-05-07 public race API now returns 5,628 races, including
  1,194 JRA races across 38 JRA dates.
- JRA post-result prediction simulations were backfilled for 1,194 races.
- Supabase history retrieval now pages beyond the default 1,000-row cap.
- Post-result simulations are marked `generated_after_result=true` and
  `official_prediction=false`, so they are excluded from official ROI.

## Highest-risk loopholes

1. Post-result contamination
   - Risk: predictions generated after the result look like real historical
     predictions.
   - Rule: official ROI only uses records with `official_prediction=true` and
     `generated_after_result=false`.

2. Payout incompleteness
   - Risk: ROI becomes inflated or nonsensical when official payout rows are
     missing.
   - Rule: ticket ROI is publishable only when the exact official payout for
     that bet type and selection exists.

3. Odds overfitting
   - Risk: AI ranking becomes simple popularity order or extreme reverse betting.
   - Rule: compare every model against market baseline, favorite baseline, and
     odds-only FL-bias-corrected baseline.

4. Data timestamp leakage
   - Risk: final odds, final body weight, or result-derived fields leak into a
     pre-race prediction.
   - Rule: every feature snapshot needs `as_of_time`; train and validate using
     only values available before that cutoff.

5. JRA/NAR mixing
   - Risk: local and central racing have different pools, venues, classes, and
     data completeness.
   - Rule: train, calibrate, and report JRA and NAR separately by default.

6. Missing non-market features
   - Current gaps: training workout, paddock score, sire/dam-sire for many 2026
     rows, raw odds snapshots, pool shares, scratches, and refund timing.
   - Rule: do not market the app as a strong non-market model until these are
     continuously captured.

7. Backtest selection bias
   - Risk: only races with attractive or complete records are counted.
   - Rule: report bet rate, skipped races, missing-payout count, and max
     drawdown alongside ROI.

8. UI trust risk
   - Risk: users see high expected return without understanding whether it is
     historical, simulated, or live.
   - Rule: every result card labels one of: live prediction, post-result
     simulation, official settled result, or missing payout.

## Model strategy

Use a model suite, not one model:

1. Market baseline
   - Converts odds to calibrated implied probabilities.
   - Includes favorite-longshot bias adjustment.

2. Non-market ranking model
   - Excludes direct odds columns.
   - Uses horse form, recent speed, distance/surface aptitude, draw, jockey,
     trainer, body weight change, going, venue, and eventually training/paddock.
   - Candidates: LightGBM/CatBoost ranking, HistGradientBoosting, regularized
     logistic baseline.

3. Blended probability model
   - Combines market baseline and non-market model.
   - Market weight must be tuned separately for JRA and NAR.
   - Output must be calibrated before EV calculation.

4. Upset classifier
   - Race-level target: favorite misses top 3, winner odds >= 8.0, trifecta/trio
     payout high, or top 3 contains outside-top-5 popularity.
   - Decides whether to buy wide/exotic tickets or show `見送り`.

5. Ticket optimizer
   - Optimizes bet types using official payouts only.
   - Displays odds/payout per 100 yen and stake percentage, not unsupported
     expected ROI claims.

## Validation gates

A model is publishable only if all pass:

- Chronological split: train through 2025, validate/calibrate on tail period,
  report 2026 and live-forward after 2026-05-07 separately.
- Metrics: AUC, Brier, log loss, ECE, NDCG@3, top3 containment.
- Betting metrics: official-payout ROI, hit rate, bet rate, skipped races,
  max drawdown, missing-payout count.
- Baselines: market, favorite, odds-only FL-adjusted, no-bet.
- JRA and NAR are reported separately.
- Public ROI excludes post-result simulations.
- Confidence intervals are shown for ROI; small samples cannot be promoted.

## Product strategy

The user-facing page should answer:

1. 買う / 見送り
2. どの券種か
3. 何%だけ賭けるか
4. 当たったら100円あたりいくら戻るか
5. AI評価、人気との差、不安要素
6. 結果後は的中、券種、払戻、損益率を明示

Internal terms such as model IDs, backend status, CSV readiness, and synthetic
ROI belong in an admin/debug view, not the public prediction screen.

## References

- JRA betting type rules: https://www.jra.go.jp/kouza/beginner/baken/
- JRA betting rules: https://www.jra.go.jp/kouza/baken/index.html
- Favorite-longshot bias literature: https://users.nber.org/~jwolfers/papers/Favorite_Longshot_Bias%28NBER%29.pdf
- Pari-mutuel market efficiency and FL bias: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=964438
- Last-minute Japanese pari-mutuel dynamics: https://arxiv.org/abs/2509.14645
- Japanese odds dynamics: https://arxiv.org/abs/2503.16470
- Odds-to-probability FL-adjusted GLM: https://arxiv.org/abs/2604.17194
- Horse-race learning-to-rank example: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003075791
