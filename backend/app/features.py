from .schemas import RunnerInput


def clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def normalized_optional(value: float | int | None, center: float, scale: float, lower: float, upper: float) -> float:
    if value is None:
        return 1
    return clamp(1 + (float(value) - center) / scale, lower, upper)


def rate_factor(value: float | None, center: float = 0.08, scale: float = 0.28) -> float:
    if value is None:
        return 1
    return clamp(1 + (value - center) / scale, 0.88, 1.14)


def composite_index(runner: RunnerInput) -> float:
    """Compact proxy for speed, stamina, race shape, and current condition."""
    base = (
        runner.speed * 0.32
        + runner.stamina * 0.22
        + runner.pace * 0.20
        + runner.condition * 0.26
    )
    recent_speed = runner.avg_last3_speed if runner.avg_last3_speed is not None else runner.speed
    training = runner.training_score if runner.training_score is not None else runner.condition
    pedigree = runner.bloodline_score if runner.bloodline_score is not None else 50
    return base * 0.72 + recent_speed * 0.12 + training * 0.10 + pedigree * 0.06


def feature_adjustment(runner: RunnerInput) -> float:
    body_factor = normalized_optional(runner.horse_weight_diff, 0, 70, 0.94, 1.05)
    rest_factor = normalized_optional(runner.days_since_last_run, 35, 180, 0.93, 1.05)
    weight_factor = normalized_optional(runner.carried_weight, 56, -160, 0.94, 1.04)
    odds_factor = normalized_optional(runner.odds_rank, 6, -24, 0.94, 1.10)
    time_factor = normalized_optional(runner.last600m, 35.5, -80, 0.94, 1.08)
    draw_factor = clamp(1 + (runner.draw_bias or 0) * 0.05, 0.95, 1.05)

    return (
        body_factor
        * rest_factor
        * weight_factor
        * odds_factor
        * time_factor
        * draw_factor
        * rate_factor(runner.jockey_win_rate)
        * rate_factor(runner.trainer_win_rate)
        * rate_factor(runner.horse_recent_place_rate, 0.28, 0.5)
    )


def raw_probability_score(runner: RunnerInput, model_mode: str) -> float:
    index_score = composite_index(runner)
    mode_factor = {
        "ensemble": 1.00,
        "deep": 1.05,
        "value": 0.96,
    }[model_mode]
    value_adjustment = clamp(runner.market_odds / 12, 0.82, 1.26) if model_mode == "value" else 1
    deep_adjustment = (
        clamp((runner.condition + runner.pace) / 172, 0.90, 1.12) if model_mode == "deep" else 1
    )

    return (
        runner.base_win
        * mode_factor
        * value_adjustment
        * deep_adjustment
        * feature_adjustment(runner)
        * clamp(index_score / 86, 0.84, 1.16)
    )
