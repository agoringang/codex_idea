import math
from collections.abc import Callable, Iterable, Sequence
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

RunnerCombo = tuple[RunnerPrediction, ...]

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


def risk_profile(risk_level: float) -> dict[str, float | str]:
    normalized = clamp(risk_level, 0, 100) / 100
    if normalized < 0.34:
        local = normalized / 0.34
        return {
            "band": "low",
            "multiplier": 0.05 + local * 0.07,
            "max_stake": 0.003 + local * 0.003,
            "portfolio_exposure": 0.006 + local * 0.004,
            "target": normalized,
        }
    if normalized < 0.67:
        local = (normalized - 0.34) / 0.33
        return {
            "band": "middle",
            "multiplier": 0.14 + local * 0.12,
            "max_stake": 0.008 + local * 0.008,
            "portfolio_exposure": 0.014 + local * 0.012,
            "target": normalized,
        }
    return {
        "band": "high",
        "multiplier": 0.30 + (normalized - 0.67) / 0.33 * 0.20,
        "max_stake": 0.020 + (normalized - 0.67) / 0.33 * 0.026,
        "portfolio_exposure": 0.035 + (normalized - 0.67) / 0.33 * 0.025,
        "target": normalized,
    }


def kelly_fraction(probability: float, odds: float) -> float:
    net_odds = odds - 1
    if net_odds <= 0:
        return 0

    return clamp((probability * net_odds - (1 - probability)) / net_odds, 0, 1)


def stake_size(bankroll: float, risk_level: float, max_exposure: float, kelly: float) -> float:
    risk = risk_profile(risk_level)
    stake_ratio = min(
        kelly * float(risk["multiplier"]),
        float(risk["max_stake"]),
        max_exposure,
    )
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


def leg(label: str, runners: Iterable[RunnerPrediction]) -> dict[str, object]:
    return {"label": label, "numbers": [runner.number for runner in runners]}


def unique_combos(combos: Iterable[RunnerCombo], *, unordered: bool = False) -> list[RunnerCombo]:
    unique: list[RunnerCombo] = []
    seen: set[tuple[str, ...]] = set()
    for combo in combos:
        key = tuple(runner.id for runner in combo)
        if unordered:
            key = tuple(sorted(key))
        if key in seen:
            continue
        seen.add(key)
        unique.append(combo)
    return unique


def pair_axis_flow(axis: RunnerPrediction, opponents: Sequence[RunnerPrediction]) -> list[RunnerCombo]:
    return [(axis, opponent) for opponent in opponents if opponent.id != axis.id]


def exacta_axis_flow(
    axis: RunnerPrediction, opponents: Sequence[RunnerPrediction], axis_position: int
) -> list[RunnerCombo]:
    if axis_position == 0:
        return [(axis, opponent) for opponent in opponents if opponent.id != axis.id]
    return [(opponent, axis) for opponent in opponents if opponent.id != axis.id]


def trio_one_axis_flow(
    axis: RunnerPrediction, opponents: Sequence[RunnerPrediction]
) -> list[RunnerCombo]:
    return [(axis, *pair) for pair in combinations(opponents, 2)]


def trio_two_axis_flow(
    first_axis: RunnerPrediction, second_axis: RunnerPrediction, opponents: Sequence[RunnerPrediction]
) -> list[RunnerCombo]:
    return [(first_axis, second_axis, opponent) for opponent in opponents]


def trifecta_fixed_axis_flow(
    axis: RunnerPrediction, opponents: Sequence[RunnerPrediction], axis_position: int
) -> list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]]:
    combos: list[tuple[RunnerPrediction, RunnerPrediction, RunnerPrediction]] = []
    for first, second in permutations(opponents, 2):
        if axis_position == 0:
            combos.append((axis, first, second))
        elif axis_position == 1:
            combos.append((first, axis, second))
        else:
            combos.append((first, second, axis))
    return combos


def exacta_probability(combo: RunnerCombo) -> float:
    second_probability = combo[1].second_probability or combo[1].win_probability
    return clamp(combo[0].win_probability * second_probability * 1.65, 0.002, 0.24)


def quinella_probability(combo: RunnerCombo) -> float:
    return clamp(2.18 * combo[0].win_probability * combo[1].win_probability, 0.004, 0.36)


def wide_probability(combo: RunnerCombo) -> float:
    return clamp(combo[0].place_probability * combo[1].place_probability * 0.92, 0.02, 0.62)


def trio_probability(combo: RunnerCombo) -> float:
    place_product = combo[0].place_probability * combo[1].place_probability * combo[2].place_probability
    return clamp(
        place_product * 0.72,
        0.001,
        0.22,
    )


def bet_type_matches_risk(bet_type: BetType, risk_level: float) -> bool:
    band = str(risk_profile(risk_level)["band"])
    if band == "low":
        return bet_type in {"place", "wide"}
    if band == "middle":
        return bet_type in {"place", "wide", "win", "bracket_quinella", "quinella", "exacta", "trio"}
    return bet_type in {"win", "place", "wide", "quinella", "exacta", "trio", "trifecta"}


def round_to_ticket_unit(value: float) -> float:
    return max(100, round(value / 100) * 100)


def scale_recommendation_stake(item: BetRecommendation, available_budget: float) -> BetRecommendation | None:
    if available_budget < 100:
        return None
    unit_stake = round_to_ticket_unit(available_budget / item.tickets)
    stake = unit_stake * item.tickets
    if stake > available_budget and unit_stake > 100:
        unit_stake = max(100, unit_stake - 100)
        stake = unit_stake * item.tickets
    if stake > available_budget:
        return None
    return item.model_copy(update={"unit_stake": unit_stake, "stake": stake})


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
    legs: list[dict[str, object]] | None = None,
    edge_floor: float | None = None,
) -> None:
    if bet_type not in request.enabled_bet_types:
        return
    if not bet_type_matches_risk(bet_type, request.risk_level):
        return

    edge = probability * odds - 1
    if probability < request.min_probability:
        return
    if odds > request.max_candidate_odds:
        return
    if request.max_edge is not None and edge > request.max_edge:
        return

    kelly = kelly_fraction(probability, odds)
    stake_budget = stake_size(request.bankroll, request.risk_level, request.max_exposure, kelly)
    unit_stake = round_to_ticket_unit(stake_budget / tickets)
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
            legs=legs or [],
            probability=probability,
            odds=odds,
            edge=edge,
            kelly_fraction=kelly,
            stake=stake,
        )
    )


def add_combo_strategy(
    recommendations: list[BetRecommendation],
    *,
    request: RaceRequest,
    bet_type: BetType,
    strategy: str,
    selection_text: str,
    combos: Iterable[RunnerCombo],
    probability_fn: Callable[[RunnerCombo], float],
    bonus: float,
    max_probability: float,
    unordered: bool,
    max_odds: float = 220,
    legs: list[dict[str, object]] | None = None,
) -> None:
    if bet_type not in request.enabled_bet_types:
        return
    if not bet_type_matches_risk(bet_type, request.risk_level):
        return

    combo_list = unique_combos(combos, unordered=unordered)
    if not combo_list:
        return

    weighted_odds = 0.0
    raw_probability = 0.0
    examples: list[str] = []
    for combo in combo_list:
        combo_probability = probability_fn(combo)
        combo_odds = synthetic_odds(bet_type, combo_probability, combo, bonus)
        raw_probability += combo_probability
        weighted_odds += combo_probability * combo_odds
        if len(examples) < 4:
            examples.append(selection(combo))

    probability = clamp(raw_probability, 0.001, max_probability)
    average_ticket_odds = weighted_odds / max(raw_probability, 0.0001)
    effective_odds = clamp(average_ticket_odds / len(combo_list), 1.01, max_odds)

    add_candidate(
        recommendations,
        request=request,
        bet_type=bet_type,
        selection_text=selection_text,
        note_text=f"{strategy} / {len(combo_list)}点 / 例 {'、'.join(examples)}",
        probability=probability,
        odds=effective_odds,
        strategy=strategy,
        tickets=len(combo_list),
        covered_selections=[selection(combo) for combo in combo_list],
        legs=legs,
    )


def trifecta_order_probability(order: Sequence[RunnerPrediction]) -> float:
    second_probability = order[1].second_probability or order[1].win_probability
    third_probability = order[2].third_probability or order[2].place_probability
    return clamp(
        order[0].win_probability * second_probability * third_probability * 2.4,
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
    legs: list[dict[str, object]] | None = None,
) -> None:
    if "trifecta" not in request.enabled_bet_types:
        return
    if not bet_type_matches_risk("trifecta", request.risk_level):
        return

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
        legs=legs,
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
    band = str(risk_profile(risk_level)["band"])
    bet_risk = BET_TYPE_RISK[recommendation.bet_type]
    risk_fit = 1 - abs(bet_risk - normalized)
    hit_rate_weight = (1 - normalized) * recommendation.probability * 3.6
    return_weight = normalized * min(recommendation.odds / 80, 1.5) * 1.3
    if recommendation.strategy == "single":
        strategy_bonus = 0
    elif recommendation.bet_type == "trifecta":
        strategy_bonus = 2.4
    elif recommendation.bet_type in {"exacta", "trio"}:
        strategy_bonus = 1.3
    elif recommendation.bet_type in {"quinella", "wide"}:
        strategy_bonus = 0.8
    else:
        strategy_bonus = 0
    if band == "low" and recommendation.bet_type in {"place", "wide"}:
        strategy_bonus += 1.2
    if band == "high" and recommendation.bet_type == "trifecta":
        strategy_bonus += 1.1

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
    band = str(risk_profile(risk_level)["band"])
    if band == "low":
        return 2
    if band == "middle":
        return 2 if bet_type in {"win", "place"} else 3
    return 4 if bet_type in {"exacta", "trio", "trifecta"} else 2


def diversify_recommendations(
    recommendations: list[BetRecommendation], request: RaceRequest, limit: int = 12
) -> list[BetRecommendation]:
    risk_level = request.risk_level
    profile = risk_profile(risk_level)
    band = str(profile["band"])
    portfolio_budget = round_to_ticket_unit(
        request.bankroll * min(request.max_exposure, float(profile["portfolio_exposure"]))
    )
    target_limit = min(limit, 3 if band == "low" else 5 if band == "middle" else 7)
    selected: list[BetRecommendation] = []
    selected_keys: set[tuple[str, str, str]] = set()
    counts: dict[str, int] = {}
    spent = 0.0

    def projected_roi(items: Sequence[BetRecommendation]) -> float:
        stake = sum(item.stake for item in items)
        if stake <= 0:
            return 0
        expected_return = sum(item.stake * item.odds * item.probability for item in items)
        return expected_return / stake

    def add_item(item: BetRecommendation) -> bool:
        nonlocal spent
        key = (item.bet_type, item.selection, item.note)
        if key in selected_keys:
            return False
        bucket = f"{item.bet_type}:{item.strategy}" if item.strategy != "single" else item.bet_type
        if counts.get(bucket, 0) >= bet_type_cap(item.bet_type, risk_level):
            return False
        remaining_budget = portfolio_budget - spent
        candidate = item
        if candidate.stake > remaining_budget:
            scaled = scale_recommendation_stake(candidate, remaining_budget)
            if scaled is None:
                return False
            candidate = scaled
        next_items = [*selected, candidate]
        if candidate.edge <= 0 and projected_roi(next_items) < request.min_portfolio_roi:
            return False
        selected.append(candidate)
        selected_keys.add(key)
        counts[bucket] = counts.get(bucket, 0) + 1
        spent += candidate.stake
        return True

    if band == "low":
        anchor_types: tuple[BetType, ...] = ("place", "wide")
    elif band == "middle":
        anchor_types = ("place", "win", "wide")
    else:
        anchor_types = ("win", "trifecta", "trio", "wide")

    for bet_type in anchor_types:
        anchor = next((item for item in recommendations if item.bet_type == bet_type), None)
        if anchor:
            add_item(anchor)
        if len(selected) == target_limit:
            return selected

    for item in recommendations:
        if add_item(item) and len(selected) == target_limit:
            return selected

    for item in recommendations:
        if add_item(item) and len(selected) == target_limit:
            break

    return selected


def predict_race(request: RaceRequest) -> RacePrediction:
    trained_probabilities = predict_probabilities(request.runners)
    if trained_probabilities is None:
        raw_scores = [raw_probability_score(runner, request.model_mode) for runner in request.runners]
        trained_place_probabilities: list[float] | None = None
        trained_top2_probabilities: list[float] | None = None
        trained_second_probabilities: list[float] | None = None
        trained_third_probabilities: list[float] | None = None
        trained_out_probabilities: list[float] | None = None
    else:
        raw_scores = trained_probabilities.win
        trained_place_probabilities = trained_probabilities.place
        trained_top2_probabilities = trained_probabilities.top2
        trained_second_probabilities = trained_probabilities.second
        trained_third_probabilities = trained_probabilities.third
        trained_out_probabilities = trained_probabilities.out

    raw_scores = [max(float(score), 1e-6) if math.isfinite(float(score)) else 1e-6 for score in raw_scores]
    total = sum(raw_scores)
    if not math.isfinite(total) or total <= 0:
        # Guard against pathological all-zero scores in heuristic mode.
        raw_scores = [max(float(runner.base_win), 1e-6) for runner in request.runners]
        total = sum(raw_scores)

    runner_predictions: list[RunnerPrediction] = []
    normalized_risk = clamp(request.risk_level, 0, 100) / 100

    for index, (runner, raw_score) in enumerate(zip(request.runners, raw_scores, strict=True)):
        win_probability = raw_score / total
        top2_probability: float | None = None
        second_probability: float | None = None
        third_probability: float | None = None
        out_probability: float | None = None
        if trained_place_probabilities is None:
            place_probability = clamp(win_probability * 2.35 + runner.condition / 520, 0.16, 0.82)
        else:
            place_probability = clamp(trained_place_probabilities[index], 0.08, 0.86)
        if trained_top2_probabilities is not None:
            top2_probability = clamp(trained_top2_probabilities[index], win_probability, place_probability)
        if trained_second_probabilities is not None:
            second_probability = clamp(trained_second_probabilities[index], 0, 1)
        elif top2_probability is not None:
            second_probability = clamp(top2_probability - win_probability, 0, 1)
        if trained_third_probabilities is not None:
            third_probability = clamp(trained_third_probabilities[index], 0, 1)
        elif top2_probability is not None:
            third_probability = clamp(place_probability - top2_probability, 0, 1)
        if trained_out_probabilities is not None:
            out_probability = clamp(trained_out_probabilities[index], 0, 1)
        else:
            out_probability = clamp(1 - place_probability, 0, 1)
        fair_odds = 1 / win_probability
        edge = win_probability * runner.market_odds - 1
        if normalized_risk < 0.34:
            score = place_probability * 72 + win_probability * 14 + edge * 7
        elif normalized_risk < 0.67:
            top2_score = top2_probability if top2_probability is not None else place_probability
            score = top2_score * 48 + place_probability * 24 + win_probability * 18 + edge * 10
        else:
            top2_score = top2_probability if top2_probability is not None else win_probability * 1.8
            score = win_probability * 64 + top2_score * 16 + place_probability * 10 + edge * 18
        score += runner.condition / 10 + runner.speed / 16

        runner_predictions.append(
            RunnerPrediction(
                id=runner.id,
                gate=runner.gate,
                number=runner.number,
                name=runner.name,
                win_probability=win_probability,
                top2_probability=top2_probability,
                place_probability=place_probability,
                second_probability=second_probability,
                third_probability=third_probability,
                out_probability=out_probability,
                fair_odds=fair_odds,
                market_odds=runner.market_odds,
                edge=edge,
                score=score,
            )
        )

    runner_predictions.sort(key=lambda item: item.score, reverse=True)
    recommendations: list[BetRecommendation] = []
    top_candidates = runner_predictions[:6]
    enabled_bet_types = set(request.enabled_bet_types)

    for runner in runner_predictions:
        add_candidate(
            recommendations,
            request=request,
            bet_type="win",
            selection_text=f"{runner.number}",
            note_text=runner.name,
            probability=runner.win_probability,
            odds=runner.market_odds,
            legs=[leg("馬番", [runner])],
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
            legs=[leg("馬番", [runner])],
        )
        add_candidate(
            recommendations,
            request=request,
            bet_type="support",
            selection_text=f"{runner.number}",
            note_text=f"{runner.name} 単勝+複勝",
            probability=runner.place_probability,
            odds=(runner.market_odds + place_odds) / 2,
            legs=[leg("馬番", [runner])],
        )

    if enabled_bet_types & {"quinella", "wide", "bracket_quinella"}:
        for pair in combinations(top_candidates, 2):
            quinella_pair_probability = quinella_probability(pair)
            wide_pair_probability = wide_probability(pair)
            bracket_probability = clamp(quinella_pair_probability * 1.08, 0.004, 0.42)

            add_candidate(
                recommendations,
                request=request,
                bet_type="quinella",
                selection_text=selection(pair),
                note_text=note(pair),
                probability=quinella_pair_probability,
                odds=synthetic_odds("quinella", quinella_pair_probability, pair, 0.11),
                legs=[leg("組み合わせ", pair)],
            )
            add_candidate(
                recommendations,
                request=request,
                bet_type="wide",
                selection_text=selection(pair),
                note_text=note(pair),
                probability=wide_pair_probability,
                odds=synthetic_odds("wide", wide_pair_probability, pair, 0.05),
                legs=[leg("組み合わせ", pair)],
            )
            add_candidate(
                recommendations,
                request=request,
                bet_type="bracket_quinella",
                selection_text="-".join(str(runner.gate) for runner in pair),
                note_text=f"枠 {'-'.join(str(runner.gate) for runner in pair)} / {note(pair)}",
                probability=bracket_probability,
                odds=synthetic_odds("bracket_quinella", bracket_probability, pair, 0.04),
                legs=[{"label": "枠", "numbers": [runner.gate for runner in pair]}],
            )

    if len(top_candidates) >= 2:
        axis = top_candidates[0]
        pair_opponents = top_candidates[1:6]
        add_combo_strategy(
            recommendations,
            request=request,
            bet_type="quinella",
            strategy="馬連1頭軸流し",
            selection_text=f"軸 {axis.number} / 相手 {selection(pair_opponents)}",
            combos=pair_axis_flow(axis, pair_opponents),
            probability_fn=quinella_probability,
            bonus=0.11,
            max_probability=0.66,
            unordered=True,
            legs=[leg("軸", [axis]), leg("相手", pair_opponents)],
        )
        add_combo_strategy(
            recommendations,
            request=request,
            bet_type="wide",
            strategy="ワイド1頭軸流し",
            selection_text=f"軸 {axis.number} / 相手 {selection(pair_opponents)}",
            combos=pair_axis_flow(axis, pair_opponents),
            probability_fn=wide_probability,
            bonus=0.05,
            max_probability=0.82,
            unordered=True,
            max_odds=80,
            legs=[leg("軸", [axis]), leg("相手", pair_opponents)],
        )

    if "exacta" in enabled_bet_types:
        for pair in permutations(top_candidates, 2):
            probability = exacta_probability(pair)
            add_candidate(
                recommendations,
                request=request,
                bet_type="exacta",
                selection_text=selection(pair),
                note_text=note(pair),
                probability=probability,
                odds=synthetic_odds("exacta", probability, pair, 0.16),
                legs=[leg("1着", [pair[0]]), leg("2着", [pair[1]])],
            )

    if len(top_candidates) >= 2:
        axis = top_candidates[0]
        exacta_opponents = top_candidates[1:5]
        add_combo_strategy(
            recommendations,
            request=request,
            bet_type="exacta",
            strategy="馬単1着軸流し",
            selection_text=f"1着 {axis.number} / 2着 {selection(exacta_opponents)}",
            combos=exacta_axis_flow(axis, exacta_opponents, 0),
            probability_fn=exacta_probability,
            bonus=0.16,
            max_probability=0.58,
            unordered=False,
            legs=[leg("1着", [axis]), leg("2着", exacta_opponents)],
        )
        add_combo_strategy(
            recommendations,
            request=request,
            bet_type="exacta",
            strategy="馬単2着軸流し",
            selection_text=f"1着 {selection(exacta_opponents)} / 2着 {axis.number}",
            combos=exacta_axis_flow(axis, exacta_opponents, 1),
            probability_fn=exacta_probability,
            bonus=0.18,
            max_probability=0.50,
            unordered=False,
            legs=[leg("1着", exacta_opponents), leg("2着", [axis])],
        )

    if "trio" in enabled_bet_types:
        for trio in combinations(top_candidates, 3):
            probability = trio_probability(trio)
            add_candidate(
                recommendations,
                request=request,
                bet_type="trio",
                selection_text=selection(trio),
                note_text=note(trio),
                probability=probability,
                odds=synthetic_odds("trio", probability, trio, 0.20),
                legs=[leg("組み合わせ", trio)],
            )

    if len(top_candidates) >= 3:
        axis = top_candidates[0]
        trio_opponents = top_candidates[1:6]
        add_combo_strategy(
            recommendations,
            request=request,
            bet_type="trio",
            strategy="3連複1頭軸流し",
            selection_text=f"軸 {axis.number} / 相手 {selection(trio_opponents)}",
            combos=trio_one_axis_flow(axis, trio_opponents),
            probability_fn=trio_probability,
            bonus=0.20,
            max_probability=0.56,
            unordered=True,
            max_odds=160,
            legs=[leg("軸", [axis]), leg("相手", trio_opponents)],
        )
        add_combo_strategy(
            recommendations,
            request=request,
            bet_type="trio",
            strategy="3連複2頭軸流し",
            selection_text=f"軸 {selection(top_candidates[:2])} / 相手 {selection(top_candidates[2:6])}",
            combos=trio_two_axis_flow(top_candidates[0], top_candidates[1], top_candidates[2:6]),
            probability_fn=trio_probability,
            bonus=0.18,
            max_probability=0.42,
            unordered=True,
            max_odds=160,
            legs=[
                leg("軸1", [top_candidates[0]]),
                leg("軸2", [top_candidates[1]]),
                leg("相手", top_candidates[2:6]),
            ],
        )

    if "trifecta" in enabled_bet_types:
        for trio in permutations(top_candidates[:5], 3):
            probability = trifecta_order_probability(trio)
            add_candidate(
                recommendations,
                request=request,
                bet_type="trifecta",
                selection_text=selection(trio),
                note_text=note(trio),
                probability=probability,
                odds=synthetic_odds("trifecta", probability, trio, 0.24),
                legs=[leg("1着", [trio[0]]), leg("2着", [trio[1]]), leg("3着", [trio[2]])],
            )

    if len(top_candidates) >= 3:
        axis = top_candidates[0]
        trifecta_opponents = top_candidates[1:6]
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単1着軸流し",
            selection_text=f"1着 {axis.number} / 2-3着 {selection(trifecta_opponents)}",
            combos=trifecta_fixed_axis_flow(axis, trifecta_opponents, 0),
            bonus=0.22,
            legs=[leg("1着", [axis]), leg("2着", trifecta_opponents), leg("3着", trifecta_opponents)],
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単2着軸流し",
            selection_text=f"1着 {selection(trifecta_opponents)} / 2着 {axis.number} / 3着 相手",
            combos=trifecta_fixed_axis_flow(axis, trifecta_opponents, 1),
            bonus=0.18,
            legs=[leg("1着", trifecta_opponents), leg("2着", [axis]), leg("3着", trifecta_opponents)],
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単3着軸流し",
            selection_text=f"1-2着 {selection(trifecta_opponents)} / 3着 {axis.number}",
            combos=trifecta_fixed_axis_flow(axis, trifecta_opponents, 2),
            bonus=0.16,
            legs=[leg("1着", trifecta_opponents), leg("2着", trifecta_opponents), leg("3着", [axis])],
        )

    if len(top_candidates) >= 5:
        top = top_candidates
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単フォーメーション",
            selection_text=(
                f"1着 {selection(top[:2])} / 2着 {selection(top[:4])} / 3着 {selection(top[:6])}"
            ),
            combos=formation_combos(top[:2], top[:4], top[:6]),
            bonus=0.19,
            legs=[leg("1着", top[:2]), leg("2着", top[:4]), leg("3着", top[:6])],
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単1頭軸マルチ",
            selection_text=f"軸 {top[0].number} / 相手 {selection(top[1:5])}",
            combos=one_axis_multi_combos(top[0], top[1:5]),
            bonus=0.16,
            legs=[leg("軸", [top[0]]), leg("相手", top[1:5])],
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単2頭軸マルチ",
            selection_text=f"軸 {selection(top[:2])} / 相手 {selection(top[2:6])}",
            combos=two_axis_multi_combos(top[0], top[1], top[2:6]),
            bonus=0.18,
            legs=[leg("軸1", [top[0]]), leg("軸2", [top[1]]), leg("相手", top[2:6])],
        )
        add_trifecta_strategy(
            recommendations,
            request=request,
            strategy="3連単4頭ボックス",
            selection_text=f"BOX {selection(top[:4])}",
            combos=permutations(top[:4], 3),
            bonus=0.14,
            legs=[leg("BOX", top[:4])],
        )

    recommendations.sort(key=lambda item: risk_adjusted_score(item, request.risk_level), reverse=True)
    recommendations = diversify_recommendations(recommendations, request)

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
