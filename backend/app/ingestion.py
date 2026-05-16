from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .data_sources import _collapse_duplicate_races, build_race_dicts_from_rows
from .history import get_all_history, record_prediction
from .model import predict_race
from .race_schedule import upsert_schedule_from_race_dicts
from .race_storage import fetch_race_cards, race_storage_available, record_ingest_run, upsert_race_cards
from .runner_state import canonical_runner_status, runner_is_inactive_dict
from .schemas import RaceRequest, RunnerInput


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_PATH = BACKEND_ROOT / "scripts" / "scrape_netkeiba_2026.py"
JST = timezone(timedelta(hours=9))


def _load_scraper_module() -> Any:
    module_name = "umalab_netkeiba_scraper"
    spec = importlib.util.spec_from_file_location(module_name, SCRAPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scraper module: {SCRAPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _date_range_for_days(days: int, days_ahead: int = 0) -> tuple[str, str]:
    today = datetime.now(JST).date()
    start = today - timedelta(days=max(days - 1, 0))
    end = today + timedelta(days=max(days_ahead, 0))
    return start.isoformat(), end.isoformat()


def _safe_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _estimated_place_odds(win_odds: float) -> float:
    # Do not manufacture huge place odds from a longshot win price. When live
    # place odds are missing, keep the estimate conservative so EV cannot be
    # inflated by synthetic data.
    return max(1.1, min(8.0, 1.05 + max(win_odds - 1.0, 0.0) * 0.09))


def _trusted_place_odds(win_odds: float, value: Any) -> float | None:
    place_odds = _safe_float(value, 0.0)
    if place_odds <= 1 or place_odds > max(win_odds, 1.1):
        return None

    # Older netkeiba imports filled missing place odds with win_odds / 4. Those
    # synthetic values look plausible for longshots but must not drive staking.
    legacy_estimate = round(max(1.1, min(win_odds, win_odds / 4.0)), 2)
    conservative_estimate = round(_estimated_place_odds(win_odds), 2)
    if abs(round(place_odds, 2) - legacy_estimate) < 0.015:
        return None
    if abs(round(place_odds, 2) - conservative_estimate) < 0.015:
        return None
    return place_odds


def _race_request_from_dict(race: dict[str, Any]) -> RaceRequest:
    raw_runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    runners = [runner for runner in raw_runners if isinstance(runner, dict) and not runner_is_inactive_dict(runner)]
    odds_rank = {
        id(item): index + 1
        for index, item in enumerate(
            sorted(runners, key=lambda item: _safe_float(item.get("odds") if isinstance(item, dict) else None, 999.0))
        )
        if isinstance(item, dict)
    }
    course = str(race.get("course") or "")
    distance_match = re.search(r"(\d+(?:\.\d+)?)m", course)
    distance = int(float(distance_match.group(1))) if distance_match else None
    surface = "ダ" if "ダ" in course else "芝" if "芝" in course else None
    going = next((label for label in ("不良", "稍重", "重", "良") if label in course), None)

    runner_inputs: list[RunnerInput] = []
    for index, runner in enumerate(runners, start=1):
        if not isinstance(runner, dict):
            continue
        number = _safe_int(runner.get("number"), index)
        odds = max(_safe_float(runner.get("odds"), 1.1), 1.1)
        rating = max(1.0, min(100.0, _safe_float(runner.get("rating"), 60.0)))
        trusted_place_odds = _trusted_place_odds(odds, runner.get("placeOdds") or runner.get("place_odds"))
        runner_inputs.append(
            RunnerInput(
                id=f"{race.get('id')}-{number}",
                gate=max(1, min(8, _safe_int(runner.get("gate"), (number + 1) // 2))),
                number=number,
                name=str(runner.get("name") or f"{number}番"),
                market_odds=odds,
                place_odds=trusted_place_odds or 1.1,
                speed=rating,
                stamina=rating,
                pace=rating,
                condition=rating,
                base_win=max(0.001, min(0.8, 1 / odds)),
                carried_weight=runner.get("carriedWeight"),
                horse_weight=runner.get("horseWeight"),
                horse_weight_diff=runner.get("horseWeightDiff"),
                age=runner.get("age"),
                sex=runner.get("sex"),
                venue=race.get("venue"),
                surface=surface,
                going=going,
                jockey=runner.get("jockey"),
                trainer=runner.get("trainer"),
                running_style=runner.get("runningStyle"),
                sire=runner.get("sire"),
                dam_sire=runner.get("damSire"),
                days_since_last_run=runner.get("daysSinceLastRun"),
                avg_last3_speed=runner.get("avgLast3Speed"),
                best_time=runner.get("bestTime"),
                last600m=runner.get("last600m"),
                jockey_win_rate=runner.get("jockeyWinRate"),
                trainer_win_rate=runner.get("trainerWinRate"),
                horse_recent_win_rate=runner.get("horseRecentWinRate"),
                horse_recent_place_rate=runner.get("horseRecentPlaceRate"),
                horse_distance_place_rate=runner.get("horseDistancePlaceRate"),
                horse_surface_place_rate=runner.get("horseSurfacePlaceRate"),
                horse_recent_win_rate_5=runner.get("horseRecentWinRate5"),
                horse_recent_place_rate_5=runner.get("horseRecentPlaceRate5"),
                horse_avg_finish_last3=runner.get("horseAvgFinishLast3"),
                horse_avg_finish_last5=runner.get("horseAvgFinishLast5"),
                horse_win_rate_lifetime=runner.get("horseWinRateLifetime"),
                horse_place_rate_lifetime=runner.get("horsePlaceRateLifetime"),
                horse_avg_odds_rank_last3=runner.get("horseAvgOddsRankLast3"),
                horse_avg_odds_last3=runner.get("horseAvgOddsLast3"),
                horse_weight_change_from_last=runner.get("horseWeightChangeFromLast"),
                horse_weight_change_rate=runner.get("horseWeightChangeRate"),
                distance_change=runner.get("distanceChange"),
                distance_abs_change=runner.get("distanceAbsChange"),
                surface_switch=runner.get("surfaceSwitch"),
                jockey_switch=runner.get("jockeySwitch"),
                carried_weight_change=runner.get("carriedWeightChange"),
                jockey_recent_win_rate_50=runner.get("jockeyRecentWinRate50"),
                jockey_recent_place_rate_50=runner.get("jockeyRecentPlaceRate50"),
                trainer_recent_win_rate_50=runner.get("trainerRecentWinRate50"),
                trainer_recent_place_rate_50=runner.get("trainerRecentPlaceRate50"),
                horse_jockey_win_rate=runner.get("horseJockeyWinRate"),
                horse_jockey_place_rate=runner.get("horseJockeyPlaceRate"),
                jockey_trainer_win_rate=runner.get("jockeyTrainerWinRate"),
                jockey_trainer_place_rate=runner.get("jockeyTrainerPlaceRate"),
                sire_win_rate=runner.get("sireWinRate"),
                sire_place_rate=runner.get("sirePlaceRate"),
                dam_sire_win_rate=runner.get("damSireWinRate"),
                dam_sire_place_rate=runner.get("damSirePlaceRate"),
                sire_surface_place_rate=runner.get("sireSurfacePlaceRate"),
                dam_sire_surface_place_rate=runner.get("damSireSurfacePlaceRate"),
                sire_distance_place_rate=runner.get("sireDistancePlaceRate"),
                dam_sire_distance_place_rate=runner.get("damSireDistancePlaceRate"),
                training_score=runner.get("trainingScore"),
                bloodline_score=runner.get("bloodlineScore"),
                paddock_score=runner.get("paddockScore"),
                lap_3f=runner.get("lap3f"),
                lap_4f=runner.get("lap4f"),
                odds_rank=odds_rank.get(id(runner)),
                odds_delta=runner.get("oddsDelta"),
                log_market_odds=runner.get("logMarketOdds"),
                odds_to_favorite=runner.get("oddsToFavorite"),
                favorite_market_odds=runner.get("favoriteMarketOdds"),
                market_top3_probability=runner.get("marketTop3Probability"),
                market_entropy=runner.get("marketEntropy"),
                market_rank_pct=runner.get("marketRankPct"),
                carried_weight_vs_field=runner.get("carriedWeightVsField"),
                horse_weight_vs_field=runner.get("horseWeightVsField"),
                age_vs_field=runner.get("ageVsField"),
                rest_vs_field=runner.get("restVsField"),
                avg_speed_vs_field=runner.get("avgSpeedVsField"),
                recent_place_vs_field=runner.get("recentPlaceVsField"),
                jockey_win_vs_field=runner.get("jockeyWinVsField"),
                trainer_win_vs_field=runner.get("trainerWinVsField"),
                draw_bias_vs_field=runner.get("drawBiasVsField"),
                ticket_pool_share=runner.get("ticketPoolShare"),
                draw_bias=runner.get("drawBias"),
                scratched=False,
                runner_status=canonical_runner_status(runner.get("runnerStatus") or runner.get("runner_status")),
            )
        )

    return RaceRequest(
        race_id=str(race.get("id") or ""),
        race_date=str(race.get("date") or date.today().isoformat()),
        venue=race.get("venue"),
        title=race.get("title"),
        race_no=race.get("raceNo"),
        course=race.get("course"),
        market=race.get("market") if race.get("market") in {"JRA", "NAR"} else None,
        model_version="racequant-active",
        model_mode="ensemble",
        risk_level=52,
        bankroll=100_000,
        min_edge=0.0,
        min_probability=0.0,
        max_candidate_odds=999,
        max_edge=None,
        max_exposure=0.1,
        recommendation_limit=7,
        enabled_bet_types=[
            "win",
            "bracket_quinella",
            "quinella",
            "wide",
            "exacta",
            "trio",
            "trifecta",
        ],
        runners=runner_inputs,
    )


def _race_has_usable_market_odds(race: dict[str, Any]) -> bool:
    runners = [
        runner
        for runner in (race.get("runners") if isinstance(race.get("runners"), list) else [])
        if isinstance(runner, dict) and not runner_is_inactive_dict(runner)
    ]
    if len(runners) < 2:
        return False
    usable = 0
    for runner in runners:
        if not isinstance(runner, dict):
            continue
        if _safe_float(runner.get("odds"), 0.0) > 1.01:
            usable += 1
    required = max(2, int(len(runners) * 0.7))
    return usable >= required


def _record_prediction_for_race(race: dict[str, Any], *, generated_after_result: bool = False) -> bool:
    runners = race.get("runners") if isinstance(race.get("runners"), list) else []
    if len(runners) < 2:
        return False
    if not _race_has_usable_market_odds(race):
        return False
    try:
        request = _race_request_from_dict(race)
        prediction = predict_race(request)
        record_prediction(
            request.race_id,
            request.race_date or date.today().isoformat(),
            prediction=prediction.model_dump(mode="json"),
            metadata={
                "race_date": request.race_date,
                "venue": request.venue,
                "title": request.title,
                "race_no": request.race_no,
                "course": request.course,
                "market": request.market,
                "risk_level": request.risk_level,
                "bankroll": request.bankroll,
                "model_mode": request.model_mode,
                "model_version": request.model_version,
                "auto_generated": True,
                "official_prediction": not generated_after_result,
                "generated_after_result": generated_after_result,
                "prediction_kind": "post_result_simulation" if generated_after_result else "pre_race_auto",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        return False
    return True


def _auto_predict_open_races(races: list[dict[str, Any]]) -> int:
    count = 0
    for race in races:
        if str(race.get("status") or "") == "finished":
            continue
        if _record_prediction_for_race(race):
            count += 1
    return count


def _existing_prediction_ids(start_date: str, end_date: str) -> set[str]:
    existing: set[str] = set()
    try:
        history = get_all_history(start_date, end_date)
    except Exception:
        return existing
    for entries in history.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            prediction = entry.get("prediction")
            race_id = str(entry.get("race_id") or "")
            if race_id and isinstance(prediction, dict) and prediction:
                existing.add(race_id)
    return existing


def _auto_predict_missing_finished_races(races: list[dict[str, Any]], start_date: str, end_date: str) -> int:
    existing = _existing_prediction_ids(start_date, end_date)
    count = 0
    for race in races:
        race_id = str(race.get("id") or "")
        if not race_id or race_id in existing:
            continue
        if str(race.get("status") or "") != "finished":
            continue
        if _record_prediction_for_race(race, generated_after_result=True):
            existing.add(race_id)
            count += 1
    return count


def _compact_name(value: Any) -> str:
    return re.sub(r"[\s\u3000・･\-\(\)（）]+", "", str(value or "")).lower()


def _odds_source_name(row: dict[str, Any]) -> str:
    source = str(row.get("odds_source") or "").strip()
    if source == "jra_official":
        return "jra_official"
    if source == "nar_official":
        return "nar_official"
    if source == "netkeiba_jra_api":
        return "netkeiba_jra_api"
    if source == "netkeiba_html":
        return "netkeiba_html"
    return source or "unknown"


def _odds_public_source_label(sources: list[str]) -> str:
    source_set = set(sources)
    has_official = "jra_official" in source_set
    has_nar_official = "nar_official" in source_set
    has_netkeiba = any(source.startswith("netkeiba") for source in source_set)
    if has_nar_official and has_netkeiba:
        return "NAR公式+netkeiba"
    if has_nar_official:
        return "NAR公式"
    if has_official and has_netkeiba:
        return "JRA公式+netkeiba"
    if has_official:
        return "JRA公式"
    if has_netkeiba:
        return "netkeiba"
    return "取得元不明"


def _matching_odds_rows(rows: list[dict[str, Any]], runner: dict[str, Any]) -> list[dict[str, Any]]:
    runner_name = _compact_name(runner.get("name"))
    matched: list[dict[str, Any]] = []
    for row in rows:
        row_name = _compact_name(row.get("horse_name"))
        if runner_name and row_name and runner_name != row_name:
            continue
        matched.append(row)
    return matched


def _choose_odds_row(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, list[str]]:
    if not rows:
        return None, "missing", []
    sources = sorted({_odds_source_name(row) for row in rows})
    official_rows = [row for row in rows if _odds_source_name(row) in {"jra_official", "nar_official"}]
    netkeiba_rows = [row for row in rows if _odds_source_name(row).startswith("netkeiba")]
    official = official_rows[-1] if official_rows else None
    latest = official or rows[-1]

    values = [
        _safe_float(row.get("market_odds"), 0.0)
        for row in rows
        if _safe_float(row.get("market_odds"), 0.0) > 1.0
    ]
    if official and netkeiba_rows and len(values) >= 2:
        min_value = min(values)
        max_value = max(values)
        tolerance = max(0.1, min_value * 0.02)
        if max_value - min_value <= tolerance:
            return official, "confirmed", sources
        return official, "source_mismatch_official_used", sources
    if official:
        return official, "official_single_source", sources
    return latest, "single_source", sources


def _with_odds_verification_tag(tags: list[Any], status: str, sources: list[str]) -> list[str]:
    cleaned = [
        str(tag)
        for tag in tags
        if not re.fullmatch(r"(オッズ二重確認|JRA公式オッズ|NAR公式オッズ|netkeibaオッズ|オッズ差異確認)", str(tag))
    ]
    if status == "confirmed":
        return [*cleaned, "オッズ二重確認"]
    if status == "source_mismatch_official_used":
        return [*cleaned, "オッズ差異確認"]
    if "jra_official" in sources:
        return [*cleaned, "JRA公式オッズ"]
    if "nar_official" in sources:
        return [*cleaned, "NAR公式オッズ"]
    if any(source.startswith("netkeiba") for source in sources):
        return [*cleaned, "netkeibaオッズ"]
    return cleaned


def _apply_live_odds_to_races(races: list[dict[str, Any]], odds_rows: list[dict[str, Any]]) -> int:
    if not races or not odds_rows:
        return 0

    odds_by_runner: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in odds_rows:
        if not isinstance(row, dict):
            continue
        race_id = str(row.get("race_id") or "")
        runner_number = _safe_int(row.get("runner_number"), 0)
        if not race_id or runner_number <= 0:
            continue
        odds_by_runner[(race_id, runner_number)].append(row)

    updated = 0
    for race in races:
        race_id = str(race.get("id") or "")
        runners = race.get("runners") if isinstance(race.get("runners"), list) else []
        race_updated = False
        for runner in runners:
            if not isinstance(runner, dict):
                continue
            number = _safe_int(runner.get("number"), 0)
            candidates = _matching_odds_rows(odds_by_runner.get((race_id, number), []), runner)
            odds_row, verification_status, odds_sources = _choose_odds_row(candidates)
            if not odds_row:
                continue

            win_odds = _safe_float(odds_row.get("market_odds"), 0.0)
            place_odds = _safe_float(odds_row.get("place_odds"), 0.0)
            if win_odds > 1.0:
                runner["odds"] = win_odds
                race_updated = True
            if place_odds > 1.0 and (win_odds <= 1.0 or place_odds <= win_odds):
                runner["placeOdds"] = place_odds
                race_updated = True
            odds_rank = _safe_int(odds_row.get("odds_rank"), 0)
            if odds_rank > 0:
                tags = runner.get("tags") if isinstance(runner.get("tags"), list) else []
                tags = [tag for tag in tags if not re.fullmatch(r"\d+人気", str(tag))]
                runner["tags"] = _with_odds_verification_tag(
                    [*tags, f"{odds_rank}人気"],
                    verification_status,
                    odds_sources,
                )
            else:
                tags = runner.get("tags") if isinstance(runner.get("tags"), list) else []
                runner["tags"] = _with_odds_verification_tag(tags, verification_status, odds_sources)
            if odds_row.get("odds_snapshot_at"):
                runner["oddsSnapshotAt"] = str(odds_row.get("odds_snapshot_at"))
            if odds_sources:
                runner["oddsSources"] = odds_sources
                runner["oddsSource"] = _odds_public_source_label(odds_sources)
                runner["oddsVerificationStatus"] = verification_status

        if race_updated:
            race["sourceCheckedAt"] = datetime.now(timezone.utc).isoformat()
            race["verificationStatus"] = "verified"
            updated += 1
    return updated


def _attach_live_feature_deltas(races: list[dict[str, Any]], start_date: str, end_date: str) -> None:
    try:
        previous_races = fetch_race_cards(start_date, end_date)
    except Exception:
        return
    previous_by_id = {str(race.get("id") or ""): race for race in previous_races if isinstance(race, dict)}
    for race in races:
        race_id = str(race.get("id") or "")
        previous = previous_by_id.get(race_id)
        if not previous:
            continue
        previous_runners = previous.get("runners") if isinstance(previous.get("runners"), list) else []
        previous_odds = {
            _safe_int(runner.get("number"), 0): _safe_float(runner.get("odds"), 0.0)
            for runner in previous_runners
            if isinstance(runner, dict)
        }
        runners = race.get("runners") if isinstance(race.get("runners"), list) else []
        for runner in runners:
            if not isinstance(runner, dict):
                continue
            number = _safe_int(runner.get("number"), 0)
            current = _safe_float(runner.get("odds"), 0.0)
            prior = previous_odds.get(number, 0.0)
            if current > 1 and prior > 1:
                runner["oddsDelta"] = round((current - prior) / prior, 4)


def ingest_netkeiba_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    race_id: str | None = None,
    days: int = 2,
    days_ahead: int = 0,
    max_requests: int | None = None,
    delay: float | None = None,
    refresh: bool = False,
    prefer_results: bool = False,
    backfill_finished_predictions: bool = False,
    market: str = "all",
    odds_only: bool = False,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    if not start_date or not end_date:
        start_date, end_date = _date_range_for_days(days, days_ahead)

    market_scope = market if market in {"JRA", "NAR"} else "all"
    explicit_race_ids = re.findall(r"20\d{10}", race_id or "")
    raw_suffix = f"_{explicit_race_ids[0]}" if explicit_race_ids else ""
    raw_dir = (
        Path(os.getenv("NETKEIBA_RAW_DIR", "/tmp/umalab_netkeiba_raw"))
        / f"{market_scope}_{start_date}_{end_date}{raw_suffix}"
    )
    configured_output = os.getenv("NETKEIBA_INGEST_OUTPUT")
    output = (
        Path(configured_output)
        if configured_output
        else Path("/tmp") / f"umalab_netkeiba_{market_scope}_{start_date}_{end_date}{raw_suffix}.csv"
    )
    raw_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    scraper = _load_scraper_module()
    race_meta: dict[str, dict[str, str]] = {}
    race_page_urls: dict[str, str] = {}
    odds_only_seed_races: list[dict[str, Any]] = []
    if explicit_race_ids:
        scraper_source = scraper.infer_source_from_race_id(explicit_race_ids[0])
        race_date_text = start_date
        if not race_date_text:
            inferred_date = scraper.infer_local_date_from_race_id(explicit_race_ids[0])
            race_date_text = (
                inferred_date.isoformat()
                if inferred_date is not None
                else datetime.now(JST).date().isoformat()
            )
        try:
            race_date = datetime.strptime(race_date_text, "%Y-%m-%d").date()
        except ValueError:
            race_date = datetime.now(JST).date()
        race_meta[explicit_race_ids[0]] = {"date": race_date.isoformat(), "source": scraper_source}
        race_page_urls[explicit_race_ids[0]] = scraper.race_url_for_dynamic_id(
            explicit_race_ids[0],
            source=scraper_source,
            race_date=race_date,
            prefer_results=prefer_results,
        )
    elif odds_only:
        try:
            odds_only_seed_races = fetch_race_cards(start_date, end_date)
        except Exception:
            odds_only_seed_races = []
        if market_scope in {"JRA", "NAR"}:
            odds_only_seed_races = [
                race
                for race in odds_only_seed_races
                if str(race.get("market") or "").upper() == market_scope
            ]
        odds_only_seed_races = [
            race
            for race in odds_only_seed_races
            if isinstance(race, dict)
            and str(race.get("id") or "")
            and str(race.get("date") or "")
            and str(race.get("status") or "") != "finished"
        ]
        for race in odds_only_seed_races:
            stored_race_id = str(race.get("id") or "")
            source = str(race.get("market") or market_scope or "").lower()
            if source not in {"jra", "nar"}:
                source = scraper.infer_source_from_race_id(stored_race_id)
            race_meta[stored_race_id] = {
                "date": str(race.get("date") or start_date),
                "source": source,
            }

    args = argparse.Namespace(
        start_date=start_date,
        end_date=end_date,
        race_id=explicit_race_ids,
        race_ids_file=None,
        raw_dir=raw_dir,
        output=output,
        base_csv=None,
        combined_output=None,
        encoding="utf-8-sig",
        delay=delay if delay is not None else float(os.getenv("NETKEIBA_INGEST_DELAY", "1.5")),
        timeout=float(os.getenv("NETKEIBA_INGEST_TIMEOUT", "20")),
        retries=int(os.getenv("NETKEIBA_INGEST_RETRIES", "1")),
        max_requests=max_requests if max_requests is not None else int(os.getenv("NETKEIBA_INGEST_MAX_REQUESTS", "120")),
        refresh=refresh,
        prefer_results=prefer_results,
        no_calendar=bool(explicit_race_ids),
        list_only=False,
        skip_import=False,
        skip_enrich=True,
        include_odds=True,
        include_official_jra_odds=True,
        include_official_nar_odds=True,
        market=market_scope,
        enriched_output=None,
        enriched_combined_output=None,
        user_agent=os.getenv(
            "NETKEIBA_USER_AGENT",
            getattr(scraper, "DEFAULT_USER_AGENT", "UmaLabResearch/0.2"),
        ),
        race_meta=race_meta,
        race_page_urls=race_page_urls,
    )

    fetcher = scraper.RateLimitedFetcher(
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        max_requests=args.max_requests,
        refresh=args.refresh,
        user_agent=args.user_agent,
    )

    calendar_ids: list[str] = []
    race_results: list[dict[str, Any]] = []
    stop_reason = ""
    try:
        if odds_only_seed_races:
            calendar_ids = sorted({str(race.get("id") or "") for race in odds_only_seed_races})
            _calendar_results = []
        else:
            calendar_ids, _calendar_results = (
                ([], [])
                if explicit_race_ids
                else scraper.scrape_calendar_pages(args, fetcher)
            )
        race_ids = sorted(set([*explicit_race_ids, *calendar_ids]))
        race_results = [] if odds_only_seed_races else scraper.scrape_race_pages(race_ids, args, fetcher)
        odds_results = scraper.scrape_odds_pages(race_ids, args, fetcher)
    except scraper.MaxRequestsReached as exc:
        race_ids = sorted(set(calendar_ids))
        stop_reason = str(exc)
        odds_results = []
    except SystemExit as exc:
        race_ids = sorted(set(calendar_ids))
        stop_reason = str(exc)
        odds_results = []

    import_summary = scraper.import_downloaded_html(args)
    live_odds_rows = scraper.load_live_odds_rows(raw_dir)
    rows = _read_rows(output)
    rows = [
        row
        for row in rows
        if start_date <= str(row.get("race_date") or "") <= end_date
    ]
    race_dicts, _snapshots = build_race_dicts_from_rows(
        rows,
        source_name="netkeiba live scrape",
        source_checked_at=datetime.now(timezone.utc).isoformat(),
    )

    odds_updates = _apply_live_odds_to_races(race_dicts, live_odds_rows)
    existing_races: list[dict[str, Any]] = odds_only_seed_races
    if not existing_races:
        try:
            existing_races = fetch_race_cards(start_date, end_date)
        except Exception:
            existing_races = []
    if market_scope in {"JRA", "NAR"}:
        existing_races = [
            race
            for race in existing_races
            if str(race.get("market") or "").upper() == market_scope
        ]
    if explicit_race_ids:
        explicit_id_set = set(explicit_race_ids)
        existing_races = [
            race for race in existing_races if str(race.get("id") or "") in explicit_id_set
        ]

    if live_odds_rows and existing_races:
        existing_updates = _apply_live_odds_to_races(existing_races, live_odds_rows)
        if existing_updates:
            race_ids_from_rows = {str(race.get("id") or "") for race in race_dicts}
            race_dicts.extend(
                race for race in existing_races if str(race.get("id") or "") not in race_ids_from_rows
            )
            odds_updates += existing_updates

    if existing_races and race_dicts:
        race_dicts = _collapse_duplicate_races([*existing_races, *race_dicts])

    _attach_live_feature_deltas(race_dicts, start_date, end_date)
    races_stored = upsert_race_cards(race_dicts)
    schedules_stored = upsert_schedule_from_race_dicts(race_dicts)
    open_predictions = _auto_predict_open_races(race_dicts) if races_stored > 0 else 0
    backfilled_predictions = (
        _auto_predict_missing_finished_races(race_dicts, start_date, end_date)
        if prefer_results and backfill_finished_predictions and races_stored > 0
        else 0
    )
    auto_predictions = open_predictions + backfilled_predictions

    status = "ok"
    if stop_reason:
        status = "partial"
    if not race_dicts:
        status = "skipped"
    if race_dicts and races_stored == 0 and not race_storage_available():
        status = "error"
        stop_reason = "Supabase is not configured, so scraped races were not persisted"

    summary = {
        "status": status,
        "source": "netkeiba",
        "market": args.market,
        "odds_only": bool(odds_only_seed_races),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "request_count": fetcher.request_count,
        "race_ids": len(race_ids),
        "race_pages": len(race_results),
        "odds_pages": len(odds_results),
        "odds_rows": len(live_odds_rows),
        "odds_updates": odds_updates,
        "rows_found": int(import_summary.get("rows") or len(rows)),
        "races_found": len(race_dicts),
        "races_stored": races_stored,
        "schedules_stored": schedules_stored,
        "auto_predictions": auto_predictions,
        "backfilled_predictions": backfilled_predictions,
        "raw_dir": str(raw_dir),
        "output": str(output),
        "message": stop_reason
        or (
            f"{len(race_dicts)} races imported, "
            f"{open_predictions} open-race predictions saved, "
            f"{schedules_stored} schedule rows updated, "
            f"{backfilled_predictions} finished-race simulations backfilled"
        ),
    }
    record_ingest_run(summary)
    return summary


def import_netkeiba_race_cards(
    race_cards: list[dict[str, Any]],
    *,
    source: str = "netkeiba_local_import",
    auto_predict: bool = True,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    races = [race for race in race_cards if isinstance(race, dict)]
    dates = sorted({str(race.get("date") or "") for race in races if race.get("date")})
    start_date = dates[0] if dates else ""
    end_date = dates[-1] if dates else ""

    races_stored = upsert_race_cards(races)
    schedules_stored = upsert_schedule_from_race_dicts(races)
    auto_predictions = _auto_predict_open_races(races) if auto_predict and races_stored > 0 else 0

    status = "ok"
    message = f"{len(races)} races imported, {auto_predictions} open-race predictions saved, {schedules_stored} schedule rows updated"
    if not races:
        status = "skipped"
        message = "no race cards supplied"
    if races and races_stored == 0 and not race_storage_available():
        status = "error"
        message = "Supabase is not configured, so supplied races were not persisted"

    summary = {
        "status": status,
        "source": source,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "request_count": 0,
        "race_ids": len(races),
        "race_pages": len(races),
        "rows_found": sum(len(race.get("runners") or []) for race in races),
        "races_found": len(races),
        "races_stored": races_stored,
        "schedules_stored": schedules_stored,
        "auto_predictions": auto_predictions,
        "backfilled_predictions": 0,
        "raw_dir": "",
        "output": "",
        "message": message,
    }
    record_ingest_run(summary)
    return summary


def parse_date_window(start_date: str | None, end_date: str | None, days: int) -> tuple[str, str]:
    if start_date and end_date:
        return start_date, end_date
    return _date_range_for_days(days)
