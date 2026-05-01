# 3連単 Strategy Notes

## Official Betting Patterns

JRA defines 3連単 as predicting the first, second, and third horses in exact order. The practical purchase patterns to model are:

- `single`: one exact order.
- `formation`: separate horse sets for 1st, 2nd, and 3rd. This is the main way to reduce combinations versus broad boxes.
- `one_axis_multi`: one axis horse plus opponents, with the axis allowed in any of the top three positions.
- `two_axis_multi`: two axis horses plus opponents, with both axes and one opponent permuted across the top three positions.
- `box`: all ordered top-three permutations from the selected horses.

## App Implementation

The backend now emits grouped 3連単 recommendations with:

- `strategy`
- `tickets`
- `unit_stake`
- `covered_selections`
- effective `odds` adjusted by ticket count

For grouped tickets, `odds` is treated as effective odds against total stake, not the gross odds of one winning line. This keeps expected value and ROI simulation from overstating returns.

## Risk Mapping

- 守り: grouped 3連単 is filtered out.
- 標準: 3連複 and 馬単 can appear, broad 3連単 generally stays out.
- 攻め: 3連単フォーメーション, 1頭軸マルチ, 2頭軸マルチ, and 4頭ボックス are eligible.

The simulator should compare these strategies by hit rate, ROI, max drawdown, and average stake per race. A higher hit rate does not automatically mean a better ROI because combination count increases total stake.
