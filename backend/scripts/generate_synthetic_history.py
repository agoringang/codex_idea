from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


VENUES = ["東京", "中山", "京都", "阪神", "中京", "新潟", "札幌", "函館", "福島", "小倉"]
SURFACES = ["芝", "ダート"]
GOINGS = ["良", "稍重", "重", "不良"]
WEATHERS = ["晴", "曇", "雨"]
RUNNING_STYLES = ["逃げ", "先行", "差し", "追込"]
SIRES = ["DeepLine", "KingHalo", "SundayAce", "StormRoute", "RobertoStar", "NorthernWay"]


def softmax(values: np.ndarray) -> np.ndarray:
    values = values - np.max(values)
    exp = np.exp(values)
    return exp / exp.sum()


def generate(races: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    start = date(2016, 1, 5)

    for race_index in range(races):
        field_size = int(rng.integers(8, 17))
        race_date = start + timedelta(days=int(race_index * 2.2))
        venue = VENUES[race_index % len(VENUES)]
        surface = str(rng.choice(SURFACES, p=[0.56, 0.44]))
        distance = int(rng.choice([1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 3000, 3200]))
        going = str(rng.choice(GOINGS, p=[0.64, 0.20, 0.11, 0.05]))
        weather = str(rng.choice(WEATHERS, p=[0.55, 0.33, 0.12]))
        race_id = f"synthetic-{race_date:%Y%m%d}-{race_index % 12 + 1:02d}"

        latent = rng.normal(0, 1, field_size)
        speed = rng.normal(74, 8, field_size) + latent * 4
        stamina = rng.normal(72, 8, field_size) + latent * 2 + (distance >= 2000) * rng.normal(3, 2, field_size)
        pace = rng.normal(70, 9, field_size)
        condition = rng.normal(72, 10, field_size) + latent * 2
        jockey_rate = np.clip(rng.beta(2.2, 18, field_size), 0.01, 0.32)
        trainer_rate = np.clip(rng.beta(2.0, 20, field_size), 0.01, 0.28)
        bloodline = np.clip(rng.normal(54, 16, field_size) + latent * 7, 10, 99)
        horse_weight_diff = rng.normal(0, 8, field_size)
        draw_bias = rng.normal(0, 0.18, field_size)
        final600 = np.clip(rng.normal(36.0, 1.4, field_size) - latent * 0.4, 31.2, 42.8)

        ability = (
            speed * 0.28
            + stamina * 0.18
            + pace * 0.10
            + condition * 0.15
            + jockey_rate * 55
            + trainer_rate * 42
            + bloodline * 0.08
            - final600 * 0.8
            + draw_bias * 8
            + rng.normal(0, 4.5, field_size)
        )
        probabilities = softmax(ability / 9.0)
        finish_order = list(rng.choice(np.arange(field_size), size=field_size, replace=False, p=probabilities))
        finish_position = {runner_index: rank + 1 for rank, runner_index in enumerate(finish_order)}
        market_noise = np.exp(rng.normal(0, 0.18, field_size))
        market_probability = np.clip(probabilities * market_noise, 0.005, 0.75)
        market_probability = market_probability / market_probability.sum()
        market_odds = np.clip(0.79 / market_probability, 1.2, 300)
        place_odds = np.clip(market_odds / rng.uniform(3.1, 5.3, field_size), 1.1, 18)
        odds_rank = pd.Series(market_odds).rank(method="first").astype(int).tolist()

        for runner_index in range(field_size):
            number = runner_index + 1
            rows.append(
                {
                    "race_id": race_id,
                    "race_date": race_date.isoformat(),
                    "runner_id": f"{race_id}-{number:02d}",
                    "gate": min(8, int((number + 1) / 2)),
                    "number": number,
                    "name": f"シンセティック{race_index:04d}-{number:02d}",
                    "venue": venue,
                    "surface": surface,
                    "going": going,
                    "weather": weather,
                    "distance": distance,
                    "age": int(rng.integers(3, 8)),
                    "sex": str(rng.choice(["牡", "牝", "せん"], p=[0.55, 0.40, 0.05])),
                    "carried_weight": float(rng.choice([52, 53, 54, 55, 56, 57, 58])),
                    "horse_weight": float(np.clip(rng.normal(480, 32), 390, 560)),
                    "horse_weight_diff": float(horse_weight_diff[runner_index]),
                    "days_since_last_run": int(np.clip(rng.normal(42, 23), 7, 180)),
                    "running_style": str(rng.choice(RUNNING_STYLES)),
                    "jockey": f"J{int(rng.integers(1, 80)):02d}",
                    "trainer": f"T{int(rng.integers(1, 180)):03d}",
                    "owner": f"O{int(rng.integers(1, 240)):03d}",
                    "breeder": f"B{int(rng.integers(1, 160)):03d}",
                    "sire": str(rng.choice(SIRES)),
                    "dam_sire": str(rng.choice(SIRES)),
                    "speed": float(np.clip(speed[runner_index], 35, 105)),
                    "stamina": float(np.clip(stamina[runner_index], 35, 105)),
                    "pace": float(np.clip(pace[runner_index], 35, 105)),
                    "condition": float(np.clip(condition[runner_index], 30, 105)),
                    "avg_last3_speed": float(np.clip(speed[runner_index] + rng.normal(0, 3), 35, 108)),
                    "best_time": float(np.clip(distance / np.clip(speed[runner_index], 35, 108) * 5.8, 54, 220)),
                    "last600m": float(final600[runner_index]),
                    "jockey_win_rate": float(jockey_rate[runner_index]),
                    "trainer_win_rate": float(trainer_rate[runner_index]),
                    "horse_recent_win_rate": float(np.clip(probabilities[runner_index] * 1.8, 0, 0.65)),
                    "horse_recent_place_rate": float(np.clip(probabilities[runner_index] * 4.8, 0.02, 0.92)),
                    "training_score": float(np.clip(condition[runner_index] + rng.normal(0, 6), 20, 100)),
                    "bloodline_score": float(bloodline[runner_index]),
                    "market_odds": float(market_odds[runner_index]),
                    "place_odds": float(place_odds[runner_index]),
                    "base_win": float(np.clip(probabilities[runner_index], 0.003, 0.72)),
                    "odds_rank": int(odds_rank[runner_index]),
                    "odds_delta": float(rng.normal(0, 0.12)),
                    "ticket_pool_share": float(np.clip(market_probability[runner_index], 0.001, 0.8)),
                    "draw_bias": float(np.clip(draw_bias[runner_index], -1, 1)),
                    "finish_position": int(finish_position[runner_index]),
                    "is_win": int(finish_position[runner_index] == 1),
                    "is_place": int(finish_position[runner_index] <= 3),
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--races", default=1200, type=int)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--output", default=Path("data/smoke_history.csv"), type=Path)
    args = parser.parse_args()

    frame = generate(args.races, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    print({"output": str(args.output), "rows": len(frame), "races": args.races})


if __name__ == "__main__":
    main()
