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
                "auc": 0.856558,
                "brier": 0.063621,
                "brier_vs_market": 0.000048,
                "calibration": {"ece": 0.004308},
            }
        },
        "is_top2": {
            "holdout_2026": {
                "auc": 0.841770,
                "brier": 0.107954,
                "brier_vs_market": -0.001746,
                "calibration": {"ece": 0.010581},
            }
        },
        "is_place": {
            "holdout_2026": {
                "auc": 0.825213,
                "brier": 0.142486,
                "brier_vs_market": -0.005229,
                "calibration": {"ece": 0.017688},
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
        "stable_on_2026": True,
        "low": {"target": "is_place", "bet_types": ["place", "wide"]},
        "middle": {"target": "is_top2", "bet_types": ["wide", "quinella", "trio"]},
        "high": {"target": "is_win", "bet_types": ["exacta", "trio", "trifecta"]},
    },
}

PUBLIC_HOLDOUT_BACKTEST = {
    "races": 5_506,
    "bets": 3_423,
    "total_stake": 7_174_600.0,
    "total_payout": 9_685_282.0,
    "roi": 1.3499,
    "hit_rate": 0.2591,
    "max_drawdown": 68_876.0,
    "note": (
        "2026 holdout win/place simulation. Exotic payout columns are not used "
        "for public ROI yet."
    ),
}
