PUBLIC_HOLDOUT_METRICS = {
    "split": {
        "fit_rows": 1_538_125,
        "fit_races": 116_598,
        "calibration_rows": 281_454,
        "calibration_races": 20_577,
        "holdout_rows": 61_400,
        "holdout_races": 5_506,
    },
    "best": {
        "is_win": {
            "holdout_2026": {
                "auc": 0.814713,
                "brier": 0.075271,
                "brier_vs_market": 0.011699,
                "calibration": {"ece": 0.039631},
            }
        },
        "is_top2": {
            "holdout_2026": {
                "auc": 0.79889,
                "brier": 0.132398,
                "brier_vs_market": 0.022697,
                "calibration": {"ece": 0.06933},
            }
        },
        "is_place": {
            "holdout_2026": {
                "auc": 0.776251,
                "brier": 0.176938,
                "brier_vs_market": 0.029224,
                "calibration": {"ece": 0.098975},
            }
        },
    },
    "feature_presence": {
        "runner_number": 1.0,
        "market_odds": 1.0,
        "market_win_probability": 1.0,
        "market_place_probability": 1.0,
        "odds_rank": 1.0,
        "age": 1.0,
        "horse_weight": 0.999,
        "horse_weight_diff": 0.999,
        "distance": 0.956,
        "days_since_last_run": 0.709,
        "jockey_win_rate": 0.933,
        "trainer_win_rate": 0.901,
        "horse_recent_win_rate": 0.709,
        "horse_recent_place_rate": 0.709,
        "horse_distance_place_rate": 0.257,
        "horse_surface_place_rate": 0.452,
        "draw_bias": 0.744,
        "venue": 1.0,
        "surface": 1.0,
        "going": 1.0,
        "weather": 1.0,
        "jockey": 1.0,
        "trainer": 1.0,
    },
    "risk_router": {
        "stable_on_2026": False,
        "low": {"target": "is_place", "bet_types": ["win", "bracket_quinella", "wide"]},
        "middle": {"target": "is_place", "bet_types": ["wide", "quinella", "trio"]},
        "high": {"target": "is_top2", "bet_types": ["exacta", "trio", "trifecta"]},
    },
}

PUBLIC_HOLDOUT_BACKTEST = None
