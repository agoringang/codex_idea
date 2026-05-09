NUMERIC_FEATURES = [
    "speed",
    "stamina",
    "pace",
    "condition",
    "runner_number",
    "bracket",
    "field_size",
    "market_odds",
    "market_win_probability",
    "market_place_probability",
    "place_odds",
    "carried_weight",
    "horse_weight",
    "horse_weight_diff",
    "distance",
    "age",
    "days_since_last_run",
    "avg_last3_speed",
    "best_time",
    "last600m",
    "jockey_win_rate",
    "trainer_win_rate",
    "horse_recent_win_rate",
    "horse_recent_place_rate",
    "horse_distance_place_rate",
    "horse_surface_place_rate",
    "training_score",
    "bloodline_score",
    "paddock_score",
    "lap_3f",
    "lap_4f",
    "odds_delta_5m",
    "odds_delta_15m",
    "odds_volatility",
    "body_weight_announced_minutes",
    "day_prev_races",
    "day_prev_upset_rate",
    "day_prev_favorite_win_rate",
    "day_prev_winner_avg_odds",
    "venue_day_prev_races",
    "venue_day_prev_upset_rate",
    "venue_day_prev_favorite_win_rate",
    "odds_rank",
    "odds_delta",
    "ticket_pool_share",
    "draw_bias",
]

CATEGORICAL_FEATURES = [
    "venue",
    "surface",
    "going",
    "weather",
    "sex",
    "jockey",
    "trainer",
    "owner",
    "breeder",
    "sire_id",
    "sire",
    "dam_sire_id",
    "dam_sire",
    "running_style",
]

TARGET_COLUMNS = [
    "is_win",
    "is_place",
    "finish_position",
    "payout_win",
    "payout_place",
    "payout_quinella",
    "payout_wide",
    "payout_exacta",
    "payout_trio",
    "payout_trifecta",
]

UNSAFE_TRAINING_FEATURES = {
    # The current local converter maps this source column to a value that is
    # often larger than win odds, so it is not reliable as a pre-race feature.
    "place_odds",
    # These are race-result values in the local keiba_data export. They can be
    # used only after shifting into historical aggregates.
    "best_time",
    "last600m",
}

TRAINING_NUMERIC_FEATURES = [
    column for column in NUMERIC_FEATURES if column not in UNSAFE_TRAINING_FEATURES
]
