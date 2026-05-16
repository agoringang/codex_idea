from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enrich_netkeiba_2026_features import enrich as enrich_2026_features
from import_netkeiba_exports import normalize_records, read_records, write_combined, write_csv


LIST_URL = "https://db.netkeiba.com/race/list/{yyyymmdd}/"
RACE_URL = "https://db.netkeiba.com/race/{race_id}/"
NAR_LIST_SUB_URL = "https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={yyyymmdd}"
JRA_LIST_SUB_URL = "https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={yyyymmdd}"
NAR_SHUTUBA_URL = "https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}"
JRA_SHUTUBA_URL = "https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
NAR_RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"
JRA_RESULT_URL = "https://race.netkeiba.com/race/result.html?race_id={race_id}"
NAR_ODDS_TANFUKU_URL = "https://nar.netkeiba.com/odds/index.html?type=b1&race_id={race_id}"
JRA_ODDS_TANFUKU_URL = "https://race.netkeiba.com/odds/index.html?race_id={race_id}&type=b1"
NAR_OFFICIAL_ODDS_TAN_URL = (
    "https://sp.keiba.go.jp/KeibaWebSP_IPAT/TodayRaceInfo/S_OddsTan_ipat"
    "?k_raceDate={race_date}&k_raceNo={race_no}&k_babaCode={venue_code}"
)
NAR_OFFICIAL_ODDS_FUKU_URL = (
    "https://sp.keiba.go.jp/KeibaWebSP_IPAT/TodayRaceInfo/S_OddsFuku_ipat"
    "?k_raceDate={race_date}&k_raceNo={race_no}&k_babaCode={venue_code}"
)
JRA_ODDS_API_URL = (
    "https://race.netkeiba.com/api/api_get_jra_odds.html"
    "?pid=api_get_jra_odds&input=UTF-8&output=jsonp"
    "&race_id={race_id}&type=1&action=update&sort=odds&compress=0"
)
JRA_OFFICIAL_ODDS_URL = "https://www.jra.go.jp/JRADB/accessO.html"
JRA_OFFICIAL_ENTRY_CNAME = "pw15oli00/6D"
RACE_ID_RE = re.compile(r"/race/(20\d{10})/?|race_id=(20\d{10})")
JRA_OFFICIAL_TANFUKU_CNAME_RE = re.compile(
    r"pw151ouS3(?P<course>\d{2})(?P<year>\d{4})(?P<meeting>\d{2})(?P<day>\d{2})"
    r"(?P<race>\d{2})(?P<date>\d{8})Z/[A-F0-9]{2}"
)
JRA_COURSE_CODES = {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10"}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "UmaLabResearch/0.2"
)
ACCESS_LIMIT_TEXT = (
    "アクセス制限",
    "通信制限",
    "captcha",
    "CAPTCHA",
    "認証",
    "ログインしてください",
)


@dataclass
class FetchResult:
    url: str
    path: str
    status: str
    http_status: int | None = None
    bytes: int = 0
    error: str = ""


class MaxRequestsReached(RuntimeError):
    pass


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start: date, end: date) -> list[date]:
    days = (end - start).days
    if days < 0:
        raise ValueError("--end-date must be on or after --start-date")
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def decode_html(raw: bytes) -> str:
    best_text = ""
    best_score = -10**9
    for encoding in ["euc-jp", "cp932", "utf-8", "utf-8-sig"]:
        text = raw.decode(encoding, errors="replace")
        score = sum(
            text.count(token) * 100
            for token in ("馬名", "騎手", "単勝", "複勝", "出馬表", "着順", "オッズ")
        ) - text.count("\ufffd")
        if score > best_score:
            best_text = text
            best_score = score
    return best_text


def read_html(path: Path) -> str:
    return decode_html(path.read_bytes())


def extract_race_ids(html: str) -> list[str]:
    ids: list[str] = []
    for match in RACE_ID_RE.finditer(html):
        race_id = match.group(1) or match.group(2)
        if race_id:
            ids.append(race_id)
    return sorted(set(ids))


def has_access_limit(html: str) -> bool:
    return any(token in html for token in ACCESS_LIMIT_TEXT)


class RateLimitedFetcher:
    def __init__(
        self,
        *,
        delay: float,
        timeout: float,
        retries: int,
        max_requests: int,
        refresh: bool,
        user_agent: str,
    ) -> None:
        self.delay = max(delay, 0.0)
        self.timeout = timeout
        self.retries = max(retries, 0)
        self.max_requests = max_requests
        self.refresh = refresh
        self.user_agent = user_agent
        self.last_request_at = 0.0
        self.request_count = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        referer: str = "https://www.netkeiba.com/",
    ) -> bytes:
        if self.max_requests and self.request_count >= self.max_requests:
            raise MaxRequestsReached(f"max requests reached: {self.max_requests}")

        self._wait()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": referer,
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(
            url,
            data=data,
            headers=headers,
        )
        self.request_count += 1
        self.last_request_at = time.monotonic()
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def fetch(self, url: str, output_path: Path) -> FetchResult:
        if output_path.exists() and not self.refresh:
            return FetchResult(
                url=url,
                path=str(output_path),
                status="cached",
                bytes=output_path.stat().st_size,
            )

        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                body = self._request(url)
                html = decode_html(body)
                if has_access_limit(html):
                    return FetchResult(
                        url=url,
                        path=str(output_path),
                        status="access_limited",
                        http_status=200,
                        bytes=len(body),
                    )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(body)
                return FetchResult(
                    url=url,
                    path=str(output_path),
                    status="fetched",
                    http_status=200,
                    bytes=len(body),
                )
            except HTTPError as exc:
                if exc.code == 404:
                    return FetchResult(
                        url=url,
                        path=str(output_path),
                        status="not_found",
                        http_status=404,
                    )
                if exc.code in {401, 403, 429}:
                    return FetchResult(
                        url=url,
                        path=str(output_path),
                        status="blocked",
                        http_status=exc.code,
                        error=str(exc),
                    )
                last_error = str(exc)
            except URLError as exc:
                last_error = str(exc.reason)
            except TimeoutError as exc:
                last_error = str(exc)

            if attempt < self.retries:
                time.sleep(self.delay * (attempt + 1))

        return FetchResult(
            url=url,
            path=str(output_path),
            status="error",
            error=last_error,
        )

    def fetch_post(
        self,
        url: str,
        output_path: Path,
        *,
        data: dict[str, str],
        referer: str,
        cache_key: str | None = None,
    ) -> FetchResult:
        if output_path.exists() and not self.refresh:
            return FetchResult(
                url=url,
                path=str(output_path),
                status="cached",
                bytes=output_path.stat().st_size,
            )

        body = urlencode(data).encode("ascii")
        request_url = f"{url}#{cache_key}" if cache_key else url
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                response_body = self._request(url, data=body, referer=referer)
                html = decode_html(response_body)
                if has_access_limit(html):
                    return FetchResult(
                        url=request_url,
                        path=str(output_path),
                        status="access_limited",
                        http_status=200,
                        bytes=len(response_body),
                    )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response_body)
                return FetchResult(
                    url=request_url,
                    path=str(output_path),
                    status="fetched",
                    http_status=200,
                    bytes=len(response_body),
                )
            except HTTPError as exc:
                if exc.code == 404:
                    return FetchResult(
                        url=request_url,
                        path=str(output_path),
                        status="not_found",
                        http_status=404,
                    )
                if exc.code in {401, 403, 429}:
                    return FetchResult(
                        url=request_url,
                        path=str(output_path),
                        status="blocked",
                        http_status=exc.code,
                        error=str(exc),
                    )
                last_error = str(exc)
            except URLError as exc:
                last_error = str(exc.reason)
            except TimeoutError as exc:
                last_error = str(exc)

            if attempt < self.retries:
                time.sleep(self.delay * (attempt + 1))

        return FetchResult(
            url=request_url,
            path=str(output_path),
            status="error",
            error=last_error,
        )


def read_race_ids_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.search(r"(20\d{10})", line)
        if match:
            ids.append(match.group(1))
    return ids


def jst_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def estimated_post_time(
    race_id: str,
    source: str,
    *,
    race_date: date | None = None,
) -> datetime | None:
    if not race_id[-2:].isdigit():
        return None
    race_no = int(race_id[-2:])
    jra_times = {
        1: "09:50",
        2: "10:20",
        3: "10:50",
        4: "11:20",
        5: "12:10",
        6: "12:40",
        7: "13:10",
        8: "13:40",
        9: "14:15",
        10: "14:50",
        11: "15:30",
        12: "16:10",
    }
    nar_times = {
        1: "10:30",
        2: "11:00",
        3: "11:30",
        4: "12:05",
        5: "12:40",
        6: "13:15",
        7: "13:50",
        8: "14:25",
        9: "15:05",
        10: "15:45",
        11: "16:25",
        12: "17:05",
    }
    time_text = (jra_times if source == "jra" else nar_times).get(race_no)
    if not time_text:
        return None
    hour, minute = map(int, time_text.split(":"))
    if race_date is None:
        try:
            race_date = date(
                int(race_id[:4]),
                int(race_id[4:6]),
                int(race_id[6:8]),
            )
        except ValueError:
            return None
    return datetime(
        race_date.year,
        race_date.month,
        race_date.day,
        hour,
        minute,
        tzinfo=timezone(timedelta(hours=9)),
    )


def infer_source_from_race_id(race_id: str) -> str:
    if len(race_id) >= 6 and race_id[4:6] in JRA_COURSE_CODES:
        return "jra"
    return "nar"


def infer_local_date_from_race_id(race_id: str) -> date | None:
    if infer_source_from_race_id(race_id) != "nar" or len(race_id) < 10:
        return None
    try:
        return date(int(race_id[:4]), int(race_id[6:8]), int(race_id[8:10]))
    except ValueError:
        return None


def race_url_for_dynamic_id(
    race_id: str,
    *,
    source: str,
    race_date: date,
    prefer_results: bool = False,
) -> str:
    now = datetime.now(timezone(timedelta(hours=9)))
    estimated = estimated_post_time(race_id, source, race_date=race_date)
    result_overdue = estimated is not None and now >= estimated + timedelta(minutes=25)
    # Do not force today's races onto result pages just because the live
    # polling endpoint is running. Before the result page exists, the shutuba
    # page plus the odds page is the only reliable source for prediction.
    is_past = race_date < jst_today() or result_overdue or (prefer_results and race_date < jst_today())
    if source == "jra":
        template = JRA_RESULT_URL if is_past else JRA_SHUTUBA_URL
    else:
        template = NAR_RESULT_URL if is_past else NAR_SHUTUBA_URL
    return template.format(race_id=race_id)


def odds_url_for_dynamic_id(race_id: str, *, source: str) -> str:
    template = JRA_ODDS_TANFUKU_URL if source == "jra" else NAR_ODDS_TANFUKU_URL
    return template.format(race_id=race_id)


def nar_official_odds_params(race_id: str) -> dict[str, str] | None:
    if infer_source_from_race_id(race_id) != "nar" or len(race_id) < 12:
        return None
    race_date = infer_local_date_from_race_id(race_id)
    if race_date is None:
        return None
    venue_code = race_id[4:6]
    race_no = str(int(race_id[-2:])) if race_id[-2:].isdigit() else ""
    if not venue_code or not race_no:
        return None
    return {
        "venue_code": venue_code,
        "race_no": race_no,
        "race_date": race_date.strftime("%Y%%2f%m%%2f%d"),
    }


def nar_official_odds_url_for_dynamic_id(race_id: str, *, kind: str) -> str | None:
    params = nar_official_odds_params(race_id)
    if not params:
        return None
    template = NAR_OFFICIAL_ODDS_FUKU_URL if kind == "fuku" else NAR_OFFICIAL_ODDS_TAN_URL
    return template.format(**params)


def jra_odds_api_url_for_dynamic_id(race_id: str) -> str:
    return JRA_ODDS_API_URL.format(race_id=race_id)


def jra_official_race_id_from_cname(cname: str) -> str | None:
    match = JRA_OFFICIAL_TANFUKU_CNAME_RE.search(cname)
    if not match:
        return None
    return (
        f"{match.group('year')}{match.group('course')}"
        f"{match.group('meeting')}{match.group('day')}{match.group('race')}"
    )


def extract_jra_official_cnames(html: str) -> list[str]:
    cnames = re.findall(
        r"doAction\(\s*['\"]/JRADB/accessO\.html['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
        html,
    )
    return sorted(set(html_lib.unescape(cname) for cname in cnames))


def official_jra_odds_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "include_official_jra_odds", True))


def scrape_jra_official_odds_pages(
    race_ids: list[str],
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> list[dict[str, Any]]:
    if not race_ids or not official_jra_odds_enabled(args):
        return []

    output_dir = args.raw_dir / "_odds"
    target_race_ids = {
        race_id
        for race_id in race_ids
        if should_fetch_odds_page(race_id, args) and infer_source_from_race_id(race_id) == "jra"
    }
    if not target_race_ids:
        return []

    results: list[dict[str, Any]] = []
    entry_path = output_dir / "jra_official_entry.html"
    entry_result = fetcher.fetch_post(
        JRA_OFFICIAL_ODDS_URL,
        entry_path,
        data={"cname": JRA_OFFICIAL_ENTRY_CNAME},
        referer="https://www.jra.go.jp/",
        cache_key=JRA_OFFICIAL_ENTRY_CNAME,
    )
    entry_row = entry_result.__dict__.copy()
    entry_row["source"] = "jra"
    entry_row["odds_api"] = "jra_official_entry"
    results.append(entry_row)
    if entry_result.status in {"blocked", "access_limited"}:
        raise SystemExit(f"JRA official odds access stopped: {entry_result.status} {entry_result.url}")
    if entry_result.status not in {"fetched", "cached"} or not entry_path.exists():
        return results

    entry_html = read_html(entry_path)
    meeting_cnames = extract_jra_official_cnames(entry_html)
    target_dates = {race_id[:4] + race_id[6:8] + race_id[8:10] for race_id in target_race_ids}
    if target_dates:
        meeting_cnames = [
            cname for cname in meeting_cnames if any(target_date in cname for target_date in target_dates)
        ]

    race_cnames: dict[str, str] = {}
    for index, meeting_cname in enumerate(meeting_cnames, start=1):
        date_match = re.search(r"(20\d{6})", meeting_cname)
        date_label = date_match.group(1) if date_match else f"meeting{index:02d}"
        meeting_path = output_dir / f"jra_official_{date_label}_{index:02d}.html"
        meeting_result = fetcher.fetch_post(
            JRA_OFFICIAL_ODDS_URL,
            meeting_path,
            data={"cname": meeting_cname},
            referer=JRA_OFFICIAL_ODDS_URL,
            cache_key=meeting_cname,
        )
        meeting_row = meeting_result.__dict__.copy()
        meeting_row["source"] = "jra"
        meeting_row["odds_api"] = "jra_official_meeting"
        results.append(meeting_row)
        if meeting_result.status in {"blocked", "access_limited"}:
            raise SystemExit(
                f"JRA official odds meeting access stopped: {meeting_result.status} {meeting_result.url}"
            )
        if meeting_result.status not in {"fetched", "cached"} or not meeting_path.exists():
            continue

        for cname in extract_jra_official_cnames(read_html(meeting_path)):
            race_id = jra_official_race_id_from_cname(cname)
            if race_id and race_id in target_race_ids:
                race_cnames[race_id] = cname

    for race_id, race_cname in sorted(race_cnames.items()):
        race_result = fetcher.fetch_post(
            JRA_OFFICIAL_ODDS_URL,
            output_dir / f"{race_id}_jra_official_b1.html",
            data={"cname": race_cname},
            referer=JRA_OFFICIAL_ODDS_URL,
            cache_key=race_cname,
        )
        race_row = race_result.__dict__.copy()
        race_row["race_id"] = race_id
        race_row["source"] = "jra"
        race_row["odds_api"] = "jra_official_tanfuku"
        results.append(race_row)
        if race_result.status in {"blocked", "access_limited"}:
            raise SystemExit(f"JRA official odds race access stopped: {race_result.status} {race_result.url}")

    return results


def scrape_nar_official_odds_pages(
    race_ids: list[str],
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> list[dict[str, Any]]:
    if not race_ids or not bool(getattr(args, "include_official_nar_odds", True)):
        return []

    output_dir = args.raw_dir / "_odds"
    results: list[dict[str, Any]] = []
    target_race_ids = [
        race_id
        for race_id in race_ids
        if should_fetch_odds_page(race_id, args) and infer_source_from_race_id(race_id) == "nar"
    ]
    for race_id in target_race_ids:
        for kind, api_name, suffix in (
            ("tan", "nar_official_tansho", "tan"),
            ("fuku", "nar_official_fukusho", "fuku"),
        ):
            odds_url = nar_official_odds_url_for_dynamic_id(race_id, kind=kind)
            if not odds_url:
                continue
            result = fetcher.fetch(
                odds_url,
                output_dir / f"{race_id}_nar_official_{suffix}.html",
            )
            row = result.__dict__.copy()
            row["race_id"] = race_id
            row["source"] = "nar"
            row["odds_api"] = api_name
            results.append(row)
            if result.status in {"blocked", "access_limited"}:
                raise SystemExit(f"NAR official odds access stopped: {result.status} {result.url}")

    return results


def scrape_calendar_pages(
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> tuple[list[str], list[dict[str, Any]]]:
    race_ids: list[str] = []
    results: list[dict[str, Any]] = []
    dynamic_page_urls: dict[str, str] = getattr(args, "race_page_urls", {}) or {}
    race_meta: dict[str, dict[str, str]] = getattr(args, "race_meta", {}) or {}
    market = str(getattr(args, "market", "all") or "all").upper()
    include_jra = market in {"ALL", "JRA"}
    include_nar = market in {"ALL", "NAR"}

    for day in date_range(parse_date(args.start_date), parse_date(args.end_date)):
        yyyymmdd = day.strftime("%Y%m%d")
        if market == "ALL":
            output_path = args.raw_dir / "_list" / f"{yyyymmdd}.html"
            result = fetcher.fetch(LIST_URL.format(yyyymmdd=yyyymmdd), output_path)
            row = result.__dict__.copy()
            row["date"] = day.isoformat()
            row["race_ids"] = []

            if result.status in {"fetched", "cached"} and output_path.exists():
                html = read_html(output_path)
                ids = extract_race_ids(html)
                row["race_ids"] = ids
                race_ids.extend(ids)
            elif result.status in {"blocked", "access_limited"}:
                row["warning"] = f"netkeiba db list blocked: {result.status}"

            results.append(row)

        for source, url_template in (("nar", NAR_LIST_SUB_URL), ("jra", JRA_LIST_SUB_URL)):
            if source == "jra" and not include_jra:
                continue
            if source == "nar" and not include_nar:
                continue
            sub_output_path = args.raw_dir / "_list" / f"{yyyymmdd}_{source}_sub.html"
            sub_result = fetcher.fetch(url_template.format(yyyymmdd=yyyymmdd), sub_output_path)
            sub_row = sub_result.__dict__.copy()
            sub_row["date"] = day.isoformat()
            sub_row["race_ids"] = []
            sub_row["source"] = source
            if sub_result.status in {"fetched", "cached"} and sub_output_path.exists():
                html = read_html(sub_output_path)
                ids = extract_race_ids(html)
                sub_row["race_ids"] = ids
                race_ids.extend(ids)
                for race_id in ids:
                    dynamic_page_urls[race_id] = race_url_for_dynamic_id(
                        race_id,
                        source=source,
                        race_date=day,
                        prefer_results=bool(getattr(args, "prefer_results", False)),
                    )
                    race_meta[race_id] = {"date": day.isoformat(), "source": source}
            elif sub_result.status in {"blocked", "access_limited"}:
                sub_row["warning"] = f"netkeiba {source} race list blocked: {sub_result.status}"
            results.append(sub_row)

    args.race_page_urls = dynamic_page_urls
    args.race_meta = race_meta
    return sorted(set(race_ids)), results


def scrape_race_pages(
    race_ids: list[str],
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    race_page_urls: dict[str, str] = getattr(args, "race_page_urls", {}) or {}

    for race_id in race_ids:
        race_url = race_page_urls.get(race_id)
        if not race_url:
            inferred_date = infer_local_date_from_race_id(race_id)
            if inferred_date is not None:
                race_url = race_url_for_dynamic_id(
                    race_id,
                    source=infer_source_from_race_id(race_id),
                    race_date=inferred_date,
                    prefer_results=bool(getattr(args, "prefer_results", False)),
                )
            else:
                race_url = RACE_URL.format(race_id=race_id)
        result = fetcher.fetch(race_url, args.raw_dir / f"{race_id}.html")
        row = result.__dict__.copy()
        row["race_id"] = race_id
        results.append(row)
        if result.status in {"blocked", "access_limited"}:
            raise SystemExit(f"netkeiba access stopped: {result.status} {result.url}")

    return results


def should_fetch_odds_page(race_id: str, args: argparse.Namespace) -> bool:
    if not bool(getattr(args, "include_odds", False)):
        return False
    meta = (getattr(args, "race_meta", {}) or {}).get(race_id, {})
    race_date_text = meta.get("date")
    if not race_date_text:
        return True
    try:
        race_date = parse_date(race_date_text)
    except ValueError:
        return True
    # JRA/NAR next-day race cards can already expose early odds signals on the
    # previous night. Fetch through tomorrow so the preday cron can create
    # predictions before race day, then refresh again on race day for updates.
    return race_date <= jst_today() + timedelta(days=1)


def scrape_odds_pages(
    race_ids: list[str],
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    race_meta: dict[str, dict[str, str]] = getattr(args, "race_meta", {}) or {}
    output_dir = args.raw_dir / "_odds"
    official_jra_targets: list[str] = []
    official_nar_targets: list[str] = []

    for race_id in race_ids:
        if not should_fetch_odds_page(race_id, args):
            continue
        source = race_meta.get(race_id, {}).get("source") or infer_source_from_race_id(race_id)
        if source == "jra":
            official_jra_targets.append(race_id)
        elif source == "nar":
            official_nar_targets.append(race_id)
        odds_url = odds_url_for_dynamic_id(race_id, source=source)
        result = fetcher.fetch(odds_url, output_dir / f"{race_id}_b1.html")
        row = result.__dict__.copy()
        row["race_id"] = race_id
        row["source"] = source
        results.append(row)
        if result.status in {"blocked", "access_limited"}:
            raise SystemExit(f"netkeiba odds access stopped: {result.status} {result.url}")
        if source == "jra":
            api_result = fetcher.fetch(
                jra_odds_api_url_for_dynamic_id(race_id),
                output_dir / f"{race_id}_jra_b1_api.jsonp",
            )
            api_row = api_result.__dict__.copy()
            api_row["race_id"] = race_id
            api_row["source"] = source
            api_row["odds_api"] = "jra_tanfuku"
            results.append(api_row)
            if api_result.status in {"blocked", "access_limited"}:
                raise SystemExit(f"netkeiba odds api access stopped: {api_result.status} {api_result.url}")

    results.extend(scrape_jra_official_odds_pages(official_jra_targets, args, fetcher))
    results.extend(scrape_nar_official_odds_pages(official_nar_targets, args, fetcher))
    return results


def strip_html_fragment(value: str) -> str:
    text = html_lib.unescape(value).replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_odds_number(value: str) -> float | None:
    text = strip_html_fragment(value).translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    if not text or "---" in text or "取消" in text or "除外" in text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    if number <= 0:
        return None
    return number


def parse_odds_runner_status(value: str) -> str:
    text = strip_html_fragment(value)
    compact = text.replace(" ", "").replace("\u3000", "")
    if "競走除外" in compact or "発走除外" in compact or "除外" in compact:
        return "除外"
    if "出走取消" in compact or "取消" in compact:
        return "取消"
    return ""


def extract_odds_table(text: str, block_id: str) -> str:
    block_index = text.find(block_id)
    if block_index < 0:
        return ""
    table_start = text.find("<table", block_index)
    if table_start < 0:
        return ""
    table_end = text.find("</table>", table_start)
    if table_end < 0:
        return ""
    return text[table_start : table_end + len("</table>")]


def parse_odds_block(text: str, block_id: str, value_key: str) -> dict[int, dict[str, Any]]:
    table = extract_odds_table(text, block_id)
    if not table:
        return {}

    parsed: dict[int, dict[str, Any]] = {}
    for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.IGNORECASE | re.DOTALL):
        row_html = row_match.group(1)
        cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 3:
            continue

        cell_texts = [strip_html_fragment(cell_html) for _attrs, cell_html in cells]
        numeric_cells = [
            int(match.group(0))
            for text_value in cell_texts[:3]
            for match in [re.fullmatch(r"\d{1,2}", text_value)]
            if match
        ]
        if not numeric_cells:
            continue
        runner_number = numeric_cells[1] if len(numeric_cells) >= 2 else numeric_cells[0]

        horse_name_match = re.search(
            r"class=[\"'][^\"']*Horse_Name[^\"']*[\"'][^>]*>(.*?)</td>",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        horse_name = strip_html_fragment(horse_name_match.group(1)) if horse_name_match else ""
        odds_match = re.search(
            r"class=[\"'][^\"']*Odds[^\"']*[\"'][^>]*>(.*?)</td>",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        odds_text = odds_match.group(1) if odds_match else cells[-1][1]
        odds_value = parse_odds_number(odds_text)
        runner_status = parse_odds_runner_status(odds_text)
        if odds_value is None and not runner_status:
            continue
        parsed[runner_number] = {
            "runner_number": runner_number,
            "horse_name": horse_name,
        }
        if odds_value is not None:
            parsed[runner_number][value_key] = odds_value
        if runner_status:
            parsed[runner_number]["runner_status"] = runner_status
    return parsed


def parse_live_odds_file(path: Path) -> list[dict[str, Any]]:
    race_id_match = re.search(r"(20\d{10})", path.stem)
    if not race_id_match:
        return []
    race_id = race_id_match.group(1)
    text = read_html(path)
    win_odds = parse_odds_block(text, "odds_tan_block", "market_odds")
    place_odds = parse_odds_block(text, "odds_fuku_block", "place_odds")
    runner_numbers = sorted(set(win_odds) | set(place_odds))
    if not runner_numbers:
        return []

    snapshot_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for runner_number in runner_numbers:
        row = {
            "race_id": race_id,
            "runner_number": runner_number,
            "odds_snapshot_at": snapshot_at,
            "odds_source": "netkeiba_html",
        }
        row.update(place_odds.get(runner_number, {}))
        row.update(win_odds.get(runner_number, {}))
        if row.get("runner_status"):
            row["scratched"] = 1
        rows.append(row)

    valid_win_odds = sorted(
        (
            (float(row["market_odds"]), int(row["runner_number"]))
            for row in rows
            if row.get("market_odds") is not None and float(row["market_odds"]) > 1.0
        )
    )
    rank_by_runner = {runner_number: index + 1 for index, (_odds, runner_number) in enumerate(valid_win_odds)}
    for row in rows:
        rank = rank_by_runner.get(int(row["runner_number"]))
        if rank is not None:
            row["odds_rank"] = rank
    return rows


def cell_has_class(attrs: str, class_name: str) -> bool:
    match = re.search(r"class=[\"']([^\"']*)[\"']", attrs, flags=re.IGNORECASE)
    if not match:
        return False
    classes = {item.strip() for item in match.group(1).split()}
    return class_name in classes


def extract_table_rows(text: str) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", text, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", row_match.group(1), flags=re.IGNORECASE | re.DOTALL)
        if cells:
            rows.append(cells)
    return rows


def parse_place_odds_range(cell_html: str) -> tuple[float | None, float | None]:
    min_match = re.search(
        r"class=[\"'][^\"']*\bmin\b[^\"']*[\"'][^>]*>(.*?)</span>",
        cell_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    max_match = re.search(
        r"class=[\"'][^\"']*\bmax\b[^\"']*[\"'][^>]*>(.*?)</span>",
        cell_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    place_min = parse_odds_number(min_match.group(1)) if min_match else None
    place_max = parse_odds_number(max_match.group(1)) if max_match else None
    if place_min is not None or place_max is not None:
        return place_min, place_max
    values = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", strip_html_fragment(cell_html))]
    if not values:
        return None, None
    return values[0], values[1] if len(values) >= 2 else None


def parse_jra_official_odds_file(path: Path) -> list[dict[str, Any]]:
    race_id_match = re.search(r"(20\d{10})", path.stem)
    if not race_id_match:
        return []
    race_id = race_id_match.group(1)
    text = read_html(path)
    if "単勝・複勝オッズ" not in text and "単勝" not in text:
        return []

    snapshot_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for cells in extract_table_rows(text):
        number_cell = next((cell for cell in cells if cell_has_class(cell[0], "num")), None)
        horse_cell = next((cell for cell in cells if cell_has_class(cell[0], "horse")), None)
        win_cell = next((cell for cell in cells if cell_has_class(cell[0], "odds_tan")), None)
        place_cell = next((cell for cell in cells if cell_has_class(cell[0], "odds_fuku")), None)
        if not number_cell or not horse_cell:
            continue
        number_match = re.fullmatch(r"\d{1,2}", strip_html_fragment(number_cell[1]))
        if not number_match:
            continue
        runner_number = int(number_match.group(0))
        horse_name = strip_html_fragment(horse_cell[1])
        win_html = win_cell[1] if win_cell else ""
        place_html = place_cell[1] if place_cell else ""
        market_odds = parse_odds_number(win_html)
        place_odds, place_odds_max = parse_place_odds_range(place_html)
        runner_status = parse_odds_runner_status(" ".join([win_html, place_html, horse_name]))
        if market_odds is None and place_odds is None and not runner_status:
            continue

        row: dict[str, Any] = {
            "race_id": race_id,
            "runner_number": runner_number,
            "horse_name": horse_name,
            "odds_snapshot_at": snapshot_at,
            "odds_source": "jra_official",
        }
        if market_odds is not None:
            row["market_odds"] = market_odds
        if place_odds is not None:
            row["place_odds"] = place_odds
        if place_odds_max is not None:
            row["place_odds_max"] = place_odds_max
        if runner_status:
            row["runner_status"] = runner_status
            row["scratched"] = 1
        rows.append(row)

    valid_win_odds = sorted(
        (
            (float(row["market_odds"]), int(row["runner_number"]))
            for row in rows
            if row.get("market_odds") is not None and float(row["market_odds"]) > 1.0
        )
    )
    rank_by_runner = {runner_number: index + 1 for index, (_odds, runner_number) in enumerate(valid_win_odds)}
    for row in rows:
        rank = rank_by_runner.get(int(row["runner_number"]))
        if rank is not None:
            row["odds_rank"] = rank
    return rows


def parse_nar_official_table(path: Path, value_key: str) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    text = read_html(path)
    if "この賭け式の発売はありません" in text or "エラー" in text:
        return {}

    parsed: dict[int, dict[str, Any]] = {}
    for cells in extract_table_rows(text):
        if len(cells) < 3:
            continue
        number_text = strip_html_fragment(cells[0][1])
        horse_name = strip_html_fragment(cells[1][1])
        odds_text = strip_html_fragment(cells[2][1])
        if not re.fullmatch(r"\d{1,2}", number_text) or not horse_name:
            continue
        if "馬番" in horse_name or "オッズ" in odds_text:
            continue
        runner_number = int(number_text)
        row: dict[str, Any] = {
            "runner_number": runner_number,
            "horse_name": horse_name,
        }
        if value_key == "place_odds":
            place_low, place_high = parse_place_odds_range(cells[2][1])
            if place_low is not None:
                row["place_odds"] = place_low
            if place_high is not None:
                row["place_odds_max"] = place_high
        else:
            odds_value = parse_odds_number(odds_text)
            if odds_value is not None:
                row[value_key] = odds_value
        runner_status = parse_odds_runner_status(" ".join([horse_name, odds_text]))
        if runner_status:
            row["runner_status"] = runner_status
            row["scratched"] = 1
        if any(key in row for key in (value_key, "runner_status")):
            parsed[runner_number] = row
    return parsed


def parse_nar_official_odds_files(win_path: Path, place_path: Path | None = None) -> list[dict[str, Any]]:
    race_id_match = re.search(r"(20\d{10})", win_path.stem)
    if not race_id_match:
        return []
    race_id = race_id_match.group(1)
    win_odds = parse_nar_official_table(win_path, "market_odds")
    place_odds = parse_nar_official_table(place_path, "place_odds") if place_path is not None else {}
    runner_numbers = sorted(set(win_odds) | set(place_odds))
    if not runner_numbers:
        return []

    snapshot_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for runner_number in runner_numbers:
        row: dict[str, Any] = {
            "race_id": race_id,
            "runner_number": runner_number,
            "odds_snapshot_at": snapshot_at,
            "odds_source": "nar_official",
        }
        row.update(place_odds.get(runner_number, {}))
        row.update(win_odds.get(runner_number, {}))
        if row.get("runner_status"):
            row["scratched"] = 1
        rows.append(row)

    valid_win_odds = sorted(
        (
            (float(row["market_odds"]), int(row["runner_number"]))
            for row in rows
            if row.get("market_odds") is not None and float(row["market_odds"]) > 1.0
        )
    )
    rank_by_runner = {runner_number: index + 1 for index, (_odds, runner_number) in enumerate(valid_win_odds)}
    for row in rows:
        rank = rank_by_runner.get(int(row["runner_number"]))
        if rank is not None:
            row["odds_rank"] = rank
    return rows


def parse_jsonp_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        stripped = stripped[1:-1].strip()
    callback_match = re.match(r"^[A-Za-z_$][\w$]*\((.*)\)$", stripped, flags=re.DOTALL)
    if callback_match:
        stripped = callback_match.group(1).strip()
    payload = json.loads(stripped)
    return payload if isinstance(payload, dict) else {}


def parse_jra_odds_api_file(path: Path) -> list[dict[str, Any]]:
    race_id_match = re.search(r"(20\d{10})", path.stem)
    html_path = path.with_name(f"{race_id_match.group(1)}_b1.html") if race_id_match else None
    return parse_jra_odds_api_file_with_mapping(path, html_path)


def parse_jra_odds_row_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    text = read_html(path)
    table = extract_odds_table(text, "odds_tan_block")
    if not table:
        return {}

    mapped: dict[str, dict[str, Any]] = {}
    for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.IGNORECASE | re.DOTALL):
        row_html = row_match.group(1)
        key_match = re.search(r"id=[\"']odds-1_(\d{2})[\"']", row_html)
        if not key_match:
            continue

        cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        cell_texts = [strip_html_fragment(cell_html) for _attrs, cell_html in cells]
        numeric_cells = [
            int(match.group(0))
            for text_value in cell_texts[:3]
            for match in [re.fullmatch(r"\d{1,2}", text_value)]
            if match
        ]
        if not numeric_cells:
            continue

        horse_name_match = re.search(
            r"class=[\"'][^\"']*Horse_Name[^\"']*[\"'][^>]*>(.*?)</td>",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        horse_name = strip_html_fragment(horse_name_match.group(1)) if horse_name_match else ""
        mapped[key_match.group(1)] = {
            "runner_number": numeric_cells[1] if len(numeric_cells) >= 2 else numeric_cells[0],
            "horse_name": horse_name,
        }
    return mapped


def parse_jra_odds_api_file_with_mapping(path: Path, html_path: Path | None = None) -> list[dict[str, Any]]:
    race_id_match = re.search(r"(20\d{10})", path.stem)
    if not race_id_match:
        return []
    race_id = race_id_match.group(1)
    try:
        payload = parse_jsonp_payload(read_html(path))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    odds = data.get("odds") if isinstance(data.get("odds"), dict) else {}
    win_rows = odds.get("1") if isinstance(odds.get("1"), dict) else {}
    if not win_rows:
        return []
    place_rows = odds.get("2") if isinstance(odds.get("2"), dict) else {}
    row_map = parse_jra_odds_row_map(html_path)
    if not row_map:
        return []

    snapshot_at = datetime.now(timezone.utc).isoformat()
    official_datetime = data.get("official_datetime")
    rows: list[dict[str, Any]] = []
    for runner_key, values in win_rows.items():
        mapped = row_map.get(str(runner_key).zfill(2))
        if not mapped:
            continue
        runner_number = int(mapped["runner_number"])
        horse_name = str(mapped.get("horse_name") or "")
        if not isinstance(values, list) or not values:
            continue
        odds_value = parse_odds_number(str(values[0]))
        runner_status = parse_odds_runner_status(str(values[0]))
        if odds_value is None and not runner_status:
            continue
        row: dict[str, Any] = {
            "race_id": race_id,
            "runner_number": runner_number,
            "odds_snapshot_at": official_datetime or snapshot_at,
            "odds_source": "netkeiba_jra_api",
        }
        if horse_name:
            row["horse_name"] = horse_name
        if odds_value is not None:
            row["market_odds"] = odds_value
        place_values = place_rows.get(runner_key) if isinstance(place_rows, dict) else None
        if isinstance(place_values, list) and place_values:
            place_low = parse_odds_number(str(place_values[0]))
            if place_low is not None:
                row["place_odds"] = place_low
        if len(values) >= 3:
            try:
                row["odds_rank"] = int(float(values[2]))
            except (TypeError, ValueError):
                pass
        if runner_status:
            row["runner_status"] = runner_status
            row["scratched"] = 1
        rows.append(row)
    return rows


def load_live_odds_rows(raw_dir: Path) -> list[dict[str, Any]]:
    odds_dir = raw_dir / "_odds"
    if not odds_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(odds_dir.glob("*_b1.html")):
        rows.extend(parse_live_odds_file(path))
    for path in sorted(odds_dir.glob("*_jra_b1_api.jsonp")):
        rows.extend(parse_jra_odds_api_file(path))
    for path in sorted(odds_dir.glob("*_jra_official_b1.html")):
        rows.extend(parse_jra_official_odds_file(path))
    for path in sorted(odds_dir.glob("*_nar_official_tan.html")):
        place_path = path.with_name(path.name.replace("_tan.html", "_fuku.html"))
        rows.extend(parse_nar_official_odds_files(path, place_path))
    return rows


def overlay_live_odds(frame: pd.DataFrame, raw_dir: Path) -> pd.DataFrame:
    odds_rows = load_live_odds_rows(raw_dir)
    if frame.empty or not odds_rows:
        return frame

    odds_frame = pd.DataFrame(odds_rows)
    if odds_frame.empty:
        return frame
    odds_frame["race_id"] = odds_frame["race_id"].astype(str)
    odds_frame["runner_number"] = pd.to_numeric(odds_frame["runner_number"], errors="coerce").astype("Int64")
    odds_frame = odds_frame.dropna(subset=["runner_number"])
    odds_frame = odds_frame.drop_duplicates(["race_id", "runner_number"], keep="last")

    live_columns = [
        column
        for column in ["market_odds", "place_odds", "odds_rank", "odds_snapshot_at", "runner_status", "scratched"]
        if column in odds_frame
    ]
    if not live_columns:
        return frame

    work = frame.copy()
    work["race_id"] = work["race_id"].astype(str)
    work["runner_number"] = pd.to_numeric(work["runner_number"], errors="coerce").astype("Int64")
    live_identity_columns = ["horse_name"] if "horse_name" in odds_frame else []
    live = odds_frame[["race_id", "runner_number", *live_identity_columns, *live_columns]].rename(
        columns={column: f"{column}_live" for column in live_columns}
    )
    if "horse_name" in live:
        live = live.rename(columns={"horse_name": "horse_name_live"})
    work = work.merge(live, how="left", on=["race_id", "runner_number"])
    if "horse_name_live" in work and "horse_name" in work:
        base_names = work["horse_name"].fillna("").astype(str).str.replace(r"\s+", "", regex=True)
        live_names = work["horse_name_live"].fillna("").astype(str).str.replace(r"\s+", "", regex=True)
        live_name_matches = (live_names == "") | (base_names == "") | (live_names == base_names)
    else:
        live_name_matches = pd.Series(True, index=work.index)
    for column in live_columns:
        live_column = f"{column}_live"
        if live_column in work:
            use_live = work[live_column].notna() & live_name_matches
            work[column] = work[live_column].where(use_live, work[column])
            work = work.drop(columns=[live_column])
    if "horse_name_live" in work:
        work = work.drop(columns=["horse_name_live"])
    return work


def import_downloaded_html(args: argparse.Namespace) -> dict[str, Any]:
    import_args = argparse.Namespace(
        input_dir=args.raw_dir,
        output=args.output,
        base_csv=args.base_csv,
        combined_output=args.combined_output,
        encoding=args.encoding,
        glob=["*.html"],
        limit_files=0,
        default_date="",
        default_race_no=None,
        default_venue="",
        default_surface="",
        default_distance=None,
        default_going="",
        default_weather="",
    )
    records, diagnostics = read_records(import_args)
    frame = normalize_records(records)
    frame = overlay_live_odds(frame, args.raw_dir)
    if frame.empty:
        return {
            "rows": 0,
            "races": 0,
            "output": str(args.output),
            "diagnostics": diagnostics,
        }

    write_csv(frame, args.output)
    date_values = pd.to_datetime(frame["race_date"], errors="coerce")
    summary: dict[str, Any] = {
        "rows": int(len(frame)),
        "races": int(frame["race_id"].nunique()),
        "min_date": date_values.min().date().isoformat() if date_values.notna().any() else None,
        "max_date": date_values.max().date().isoformat() if date_values.notna().any() else None,
        "rows_missing_result": int(frame["finish_position"].isna().sum()),
        "rows_missing_market_odds": int(frame["market_odds"].isna().sum()),
        "output": str(args.output),
        "diagnostics": diagnostics,
    }
    if args.base_csv and args.combined_output:
        summary["combined"] = write_combined(args.base_csv, frame, args.combined_output)
    if not args.skip_enrich and args.base_csv:
        summary["enriched"] = enrich_2026_features(
            base_csv=args.base_csv,
            netkeiba_csv=args.output,
            output_2026=args.enriched_output,
            output_combined=args.enriched_combined_output,
        )
    summary["runner_integrity"] = verify_scraped_runner_integrity(args.start_date, args.end_date)
    return summary


def verify_scraped_runner_integrity(start_date: str, end_date: str) -> dict[str, Any]:
    from app.data_sources import get_races
    from app.runner_integrity import validate_race_runner_integrity

    races = get_races(start_date=start_date, end_date=end_date)
    reports: list[dict[str, Any]] = []
    error_count = 0
    warning_count = 0
    for race in races:
        report = validate_race_runner_integrity(race)
        errors = report.get("errors") if isinstance(report.get("errors"), list) else []
        warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
        error_count += len(errors)
        warning_count += len(warnings)
        if errors or warnings:
            reports.append(
                {
                    "race_id": race.id,
                    "date": race.date,
                    "venue": race.venue,
                    "race_no": race.raceNo,
                    "errors": errors,
                    "warnings": warnings,
                }
            )
    return {
        "status": "ok" if error_count == 0 else "failed",
        "races": len(races),
        "error_count": error_count,
        "warning_count": warning_count,
        "reports": reports[:50],
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Conservatively scrape public netkeiba DB race pages for 2026, cache raw HTML, "
            "and normalize it into UmaLab CSV."
        )
    )
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--race-id", action="append", default=[])
    parser.add_argument("--race-ids-file", type=Path, default=None)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/netkeiba_2026"))
    parser.add_argument("--output", type=Path, default=Path("data/netkeiba_2026_normalized.csv"))
    parser.add_argument("--base-csv", type=Path, default=Path("data/keiba_history_normalized.csv"))
    parser.add_argument(
        "--combined-output",
        type=Path,
        default=Path("data/keiba_history_with_2026.csv"),
    )
    parser.add_argument("--enriched-output", type=Path, default=Path("data/netkeiba_2026_enriched.csv"))
    parser.add_argument(
        "--enriched-combined-output",
        type=Path,
        default=Path("data/keiba_history_with_2026_enriched.csv"),
    )
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-calendar", action="store_true")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--include-odds", action="store_true")
    parser.add_argument(
        "--no-official-jra-odds",
        dest="include_official_jra_odds",
        action="store_false",
        help="Disable JRA official odds fallback/verification.",
    )
    parser.add_argument(
        "--no-official-nar-odds",
        dest="include_official_nar_odds",
        action="store_false",
        help="Disable NAR official odds fallback/verification.",
    )
    parser.set_defaults(include_official_jra_odds=True, include_official_nar_odds=True)
    parser.add_argument(
        "--market",
        choices=["all", "JRA", "NAR"],
        default="all",
        help="Limit calendar/race scraping to JRA or NAR. Useful for fast central odds refreshes.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    fetcher = RateLimitedFetcher(
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        max_requests=args.max_requests,
        refresh=args.refresh,
        user_agent=args.user_agent,
    )

    explicit_ids = [race_id for item in args.race_id for race_id in re.findall(r"20\d{10}", item)]
    explicit_ids.extend(read_race_ids_file(args.race_ids_file))

    calendar_ids: list[str] = []
    calendar_results: list[dict[str, Any]] = []
    try:
        if not args.no_calendar:
            calendar_ids, calendar_results = scrape_calendar_pages(args, fetcher)
        race_ids = sorted(set([*explicit_ids, *calendar_ids]))
        race_results = [] if args.list_only else scrape_race_pages(race_ids, args, fetcher)
        odds_results = [] if args.list_only else scrape_odds_pages(race_ids, args, fetcher)
    except MaxRequestsReached as exc:
        race_ids = sorted(set([*explicit_ids, *calendar_ids]))
        race_results = []
        odds_results = []
        stop_reason = str(exc)
    else:
        stop_reason = ""

    import_summary = None
    if not args.skip_import and not args.list_only:
        import_summary = import_downloaded_html(args)

    summary = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "raw_dir": str(args.raw_dir),
        "request_count": fetcher.request_count,
        "stop_reason": stop_reason or None,
        "race_ids": len(race_ids),
        "race_id_sample": race_ids[:10],
        "calendar_pages": len(calendar_results),
        "calendar_results": calendar_results,
        "race_pages": len(race_results),
        "race_results": race_results,
        "odds_pages": len(odds_results),
        "odds_results": odds_results,
        "import": import_summary,
    }
    write_manifest(args.raw_dir / "scrape_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
