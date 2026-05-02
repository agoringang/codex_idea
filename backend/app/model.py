from collections.abc import Iterable, Sequence
from itertools import combinations, permutations

from .features import clamp, raw_probability_score
from .schemas import BetRecommendation, BetType, RacePrediction, RaceRequest, RunnerPrediction
from .trained_model import predict_probabilities


PAYOUT_RATES: dict[BetType, float] = {
    "win": 0.80,
    "place": 0.80,
    "support": 0.80,
    "bracket_quinella": 0.775,
    "quinella": 0.775,
    "wide": 0.775,
    "exacta": 0.750,
    "trio": 0.750,
    "trifecta": 0.725,
    "win5": 0.700,
}

BET_TYPE_RISK: dict[BetType, float] = {
    "place": 0.12,
    "wide": 0.22,
    "bracket_quinella": 0.28,
    "support": 0.34,
    "win": 0.44,
    "quinella": 0.54,
    "exacta": 0.68,
    "trio": 0.76,
    "trifecta": 0.92,
    "win5": 1.00,
}

BET_TYPE_UTILITY: dict[BetType, float] = {
    "win": 0.02,
    "place": 0.22,
    "support": -2.20,
    "bracket_quinella": 0.12,
    "quinella": 0.10,
    "wide": 0.24,
    "exacta": 0.16,
    "trio": 0.18,
    "trifecta": 0.22,
    "win5": -0.15,
}


def risk_profile(risk_level: float) -> dict[str, float]:
    normalized = clamp(risk_level, 0, 100) / 100
    return {
        "multiplier": 0.12 + normalized * 0.42,
        "max_stake": 0.008 + normalized * 0.032,
        "target": normalized,
    }


def kelly_fraction(probability: float, odds: float) -> float:
    net_odds = odds - 1
    if net_odds <= 0:
        return 0

    return clamp((probability * net_odds - (1 - probability)) / net_odds, 0, 1)


def stake_size(bankroll: float, risk_level: float, max_exposure: float, kelly: float) -> float:
    risk = risk_profile(risk_level)
    stake_ratio = min(kelly * risk["multiplier"], risk["max_stake"], max_exposure)
    return round(bankroll * stake_ratio / 100) * 100


def value_bias(runners: Iterable[RunnerPrediction], bonus: float = 0) -> float:
    runners = list(runners)
    if not runners:
        return 1

    base = sum(runner.market_odds / runner.fair_odds for runner in runners) / len(runners)
    longshot = max(0, sum(runner.market_odds for runner in runners) / len(runners) - 8) / 24
    return clamp(base + longshot + bonus, 0.68, 1.85)


def synthetic_odds(
    bet_type: BetType, probability: float, runners: Iterable[RunnerPrediction], bonus: float = 0
) -> float:
    fair_odds = 1 / max(probability, 0.0001)
    return clamp(fair_odds * PAYOUT_RATES[bet_type] * value_bias(runners, bonus), 1.1, 999.9)


def selection(runners: Iterable[RunnerPrediction]) -> str:
    return "-".join(str(runner.number) for runner in runners)


def note(runners: Iterable[RunnerPrediction]) -> str:
    return " / ".join(f"{runner.number} {runner.name}" for runner in runners)


def bet_type_matches_risk(bet_type: BetType, risk_level: float) -> bool:
    normalized = clamp(risk_level, 0, 100) / 100
    bet_risk = BET_TYPE_RISK[bet_type]

    if normalized < 0.34:
        return bet_risk <= 0.55
    if normalized < 0.67:
        return bet_risk <= 0.78
    return bet_risk >= 0.44 or bet_type in {"wide", "quinella"}


def add_candidate(
    recommendations: list[BetRecommendation],
    *,
    request: RaceRequest,
    bet_type: BetType,
    selection_text: str,
    note_text: str,
    probability: float,
    odds: float,
    strategy: str = "single",
    tickets: int = 1,
    covered_selections: list[str] | None = None,
    edge_floor: float | None = None,
) -> None:
    if bet_type not in request.enabled_bet_types:
        return
    if not bet_type_matches_risk(bet_type, request.risk_level):
        return

    edge = probability * odds - 1
    kelly = kelly_fraction(probability, odds)
    stake_budget = stake_size(request.bankroll, request.risk_level, request.max_exposure, kelly)
    unit_stake = max(100, round(stake_budget / tickets / 100) * 100)
    stake = unit_stake * tickets

    minimum_edge = request.min_edge if edge_floor is None else edge_floor
    if edge < minimum_edge or stake < 100:
        return

    recommendations.append(
        BetRecommendation(
            selection=selection_text,
            note=note_text,
            bet_type=bet_type,
            strategy=strategy,
            tickets=tickets,
            unit_stake=unit_stake,
            covered_selections=covered_selections or [selection_text],
            probability=probability,
            odds=odds,
            edge=edge,
            kelly_fraction=kelly,
            stake=stake,
        )
    )


def trifecta_order_probability(order: Sequence[RunnerPrediction]) -> float:
    return clamp(
        order[0].win_probability * order[1].win_probability * order[2].win_probability * 1.9,
        0.0005,
        0.12,
    )


def add_trifecta_strategy(
    recommendations: list[BetRecommendation],
    *,
    request: RaceRequest,
    strategy: str,
    selection_text: str,
    combos: Iterable[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]],
    bonus: float,
) -> None:
    unique_combos: list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]] = []
    seen: set[tuple[str, str, str]] = set()
    for combo in combos:
        key = tuple(runner.id for runner in combo)
        if key in seen:
            continue
        seen.add(key)
        unique_combos.append(combo)
    combos = unique_combos
    if not combos:
        return

    weighted_odds = 0.0
    raw_probability = 0.0
    notes: list[str] = []
    for combo in combos:
        combo_probability = trifecta_order_probability(combo)
        combo_odds = synthetic_odds("trifecta", combo_probability, combo, bonus)
        raw_probability += combo_probability
        weighted_odds += combo_probability * combo_odds
        if len(notes) < 4:
            notes.append(selection(combo))

    probability = clamp(raw_probability, 0.001, 0.62)
    average_ticket_odds = weighted_odds / max(raw_probability, 0.0001)
    effective_odds = clamp(average_ticket_odds / len(combos), 1.01, 180)

    add_candidate(
        recommendations,
        request=request,
        bet_type="trifecta",
        selection_text=selection_text,
        note_text=f"{strategy} / {len(combos)}点 / 例 {'、'.join(notes)}",
        probability=probability,
        odds=effective_odds,
        strategy=strategy,
        tickets=len(combos),
        covered_selections=[selection(combo) for combo in combos],
        edge_floor=-0.95,
    )


def formation_combos(
    firsts: Sequence[RunnerPrediction], seconds: Sequence[RunnerPrediction], thirds: Sequence[RunnerPrediction]
) -> list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]]:
    return [(a, b, c) for a in firsts for b in seconds for c in thirds if len({a.id, b.id, c.id}) == 3]


def one_axis_multi_combos(
    axis: RunnerPrediction, opponents: Sequence[RunnerPrediction]
) -> list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]]:
    combos: list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]] = []
    for pair in combinations(opponents, 2):
        combos.extend(permutations((axis, *pair), 3))
    return combos


def two_axis_multi_combos(
    first_axis: RunnerPrediction, second_axis: RunnerPrediction, opponents: Sequence[RunnerPrediction]
) -> list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]]:
    combos: list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]] = []
    for opponent in opponents:
        combos.extend(permutations((first_axis, second_axis, opponent), 3))
    return combos


def risk_adjusted_score(recommendation: BetRecommendation, risk_level: float) -> float:
    normalized = clamp(risk_level, 0, 100) / 100
    bet_risk = BET_TYPE_RISK[recommendation.bet_type]
    risk_fit = 1 - abs(bet_risk - normalized)
    hit_rate_weight = (1 - normalized) * recommendation.probability * 3.6
    return_weight = normalized * min(recommendation.odds / 80, 1.5) * 1.3
    strategy_bonus = 2.4 if recommendation.bet_type == "trifecta" and recommendation.strategy != "single" else 0

    return (
        recommendation.edge * 0.9
        + hit_rate_weight
        + return_weight
        + risk_fit * 2.1
        + recommendation.kelly_fraction * 0.4
        + BET_TYPE_UTILITY[recommendation.bet_type]
        + strategy_bonus
    )


def bet_type_cap(bet_type: BetType, risk_level: float) -> int:
    normalized = clamp(risk_level, 0, 100) / 100
    if bet_type == "support":
        return 2
    if normalized < 0.34:
        return 4 if bet_type in {"place", "wide"} else 2
    if normalized < 0.67:
        return 3
    return 4 if bet_type in {"exacta", "trio", "trifecta"} else 2


def diversify_recommendations(
    recommendations: list[BetRecommendation], risk_level: float, limit: int = 12
) -> list[BetRecommendation]:
    selected: list[BetRecommendation] = []
    selected_keys: set[tuple[str, str, str]] = set()
    counts: dict[str, int] = {}

    for item in recommendations:
        bucket = f"{item.bet_type}:{item.strategy}" if item.bet_type == "trifecta" and item.strategy != "single" else item.bet_type
        if counts.get(bucket, 0) >= bet_type_cap(item.bet_type, risk_level):
            continue
        selected.append(item)
        selected_keys.add((item.bet_type, item.selection, item.note))
        counts[bucket] = counts.get(bucket, 0) + 1
        if len(selected) == limit:
            return selected

    for item in recommendations:
        key = (item.bet_type, item.selection, item.note)
        if key in selected_keys:
            continue
        selected.append(item)
        if len(selected) == limit:
            break

    return selected


def predict_race(request: RaceRequest) -> RacePrediction:
    trained_probabilities = predict_probabilities(request.runners)
    if trained_probabilities is None:
        raw_scores = [raw_probability_score(runner, request.model_mode) for runner in request.runners]
        trained_place_probabilities: list[float] | None = None
    else:
        raw_scores, trained_place_probabilities = trained_probabilities

    total = sum(raw_scores)

    runner_predictions: list[RunnerPrediction] = []

    for index, (runner, raw_score) in enumerate(zip(request.runners, raw_scores, strict=True)):
        win_probability = raw_score / total
        if trained_place_probabilities is None:
            place_probability = clamp(win_probability * 2.35 + runner.condition / 520, 0.16, 0.82)
        else:
            place_probability = clamp(trained_place_probabilities[index], 0.08, 0.86)
        fair_odds = 1 / win_probability
        edge = win_probability * runner.market_odds - 1
        score = win_probability * 56 + edge * 24 + runner.condition / 8 + runner.speed / 12

        runner_predictions.append(
            RunnerPrediction(
                id=runner.id,
                gate=runner.gate,
                number=runner.number,
                name=runner.name,
                win_probability=win_probability,
                place_probability=place_probability,
                fair_odds=fair_odds,
                market_odds=runner.market_odds,
                edge=edge,
                score=score,
            )
        )

    runner_predictions.sort(key=lambda item: item.score, reverse=True)
    recommendations: list[BetRecommendation] = []

    for runner in runner_predictions:
        add_candidate(
            recommendations,
            request=request,
            bet_type="win",
            selection_text=f"{runner.number}",
            note_text=runner.name,
            probability=runner.win_probability,
            odds=runner.market_odds,
        )
        place_odds = next(item.place_odds for item in request.runners if item.id == runner.id)
        add_candidate(
            recommendations,
            request=request,
            bet_type="place",
            selection_text=f"{runner.number}",
            note_text=runner.name,
            probability=runner.place_probability,
            odds=place_odds,
        )
        add_candidate(
            recommendations,
            request=request,
            bet_type="support",
            selection_text=f"{runner.number}",
            note_text=f"{runner.name} 単勝+複勝",
            probability=runner.place_probability,
            odds=(runner.market_odds + place_odds) / 2,
        )

    for pair in combinations(runner_predictions, 2):
        quinella_probability = clamp(2.18 * pair[0].win_probability * pair[1].win_probability, 0.004, 0.36)
        wide_probability = clamp(pair[0].place_probability * pair[1].place_probability * 0.92, 0.02, 0.62)
        bracket_probability = clamp(quinella_probability * 1.08, 0.004, 0.42)

        add_candidate(
            recommendations,
            request=request,
            bet_type="quinella",
            selection_text=selection(pair),
            note_text=note(pair),
            probability=quinella_probability,
            odds=synthetic_odds("quinella", quinella_probability, pair, 0.11),
        )
        add_candidate(
            recommendations,
            request=request,
            bet_type="wide",
            selection_text=selection(pair),
            note_text=note(pair),
            probability=wide_probability,
            odds=synthetic_odds("wide", wide_probability, pair, 0.05),
        )
        add_candidate(
            recommendations,
            request=request,
            bet_type="bracket_quinella",
            selection_text="-".join(str(runner.gate) for runner in pair),
            note_text=f"枠 {'-'.join(str(runner.gate) for runner in pair)} / {note(pair)}",
            probability=bracket_probability,
            odds=synthetic_odds("bracket_quinella", bracket_probability, pair, 0.04),
        )

    for pair in permutations(runner_predictions[:8], 2):
        probability = clamp(pair[0].win_probability * pair[1].win_probability * 1.34, 0.002, 0.24)
        add_candidate(
            recommendations,
            request=request,
            bet_type="exacta",
            selection_text=selection(pair),
            note_text=note(pair),
            probability=probability,
            odds=synthetic_odds("exacta", probability, pair, 0.16),
        )

    for trio in combinations(runner_predictions[:8], 3):
        probability = clamp(
            trio[0].win_probability * trio[1].win_probability * trio[2].win_probability * 7.4,
            0.001,
            0.22,
        )
        add_candidate(
            recommendations,
            request=request,
            bet_type="trio",
            selection_text=selection(trio),
            note_text=note(trio),
            probability=probability,
            odds=synthetic_odds("trio", probability, trio, 0.20),
        )

    for trio in permutations(runner_predictions[:7], 3):
        probability = trifecta_order_probability(trio)
        add_candidate(
            recommendations,
            request=request,
            bet_type="trifecta",
            selection_text=selection(trio),
            note_text=note(trio),
            probability=probability,
            odds=synthetic_odds("trifecta", probability, trio, 0.24),
        )

    if len(runner_predictions) >= 5:
        top = runner_predictions[:6]
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単フォーメーション",
            selection_text=(
                f"1着 {selection(top[:2])} / 2着 {selection(top[:4])} / 3着 {selection(top[:6])}"
            ),
            combos=formation_combos(top[:2], top[:4], top[:6]),
            bonus=0.19,
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単1頭軸マルチ",
            selection_text=f"軸 {top[0].number} / 相手 {selection(top[1:5])}",
            combos=one_axis_multi_combos(top[0], top[1:5]),
            bonus=0.16,
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単2頭軸マルチ",
            selection_text=f"軸 {selection(top[:2])} / 相手 {selection(top[2:6])}",
            combos=two_axis_multi_combos(top[0], top[1], top[2:6]),
            bonus=0.18,
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単4頭ボックス",
            selection_text=f"BOX {selection(top[:4])}",
            combos=permutations(top[:4], 3),
            bonus=0.14,
        )

    recommendations.sort(key=lambda item: risk_adjusted_score(item, request.risk_level), reverse=True)
    recommendations = diversify_recommendations(recommendations, request.risk_level)

    total_stake = sum(item.stake for item in recommendations)
    expected_return = sum(item.stake * item.odds * item.probability for item in recommendations)
    expected_roi = (expected_return / total_stake) if total_stake else 0

    return RacePrediction(
        race_id=request.race_id,
        model_mode=request.model_mode,
        runners=runner_predictions,
        recommendations=recommendations,
        total_stake=total_stake,
        expected_return=expected_return,
        expected_roi=expected_roi,
        warning="No model can guarantee profit or a 100% win rate. Use live odds, backtests, and stake caps.",
    )
