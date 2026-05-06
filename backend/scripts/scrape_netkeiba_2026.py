from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_netkeiba_exports import normalize_records, read_records, write_combined, write_csv


LIST_URL = "https://db.netkeiba.com/race/list/{yyyymmdd}/"
RACE_URL = "https://db.netkeiba.com/race/{race_id}/"
NAR_LIST_SUB_URL = "https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={yyyymmdd}"
JRA_LIST_SUB_URL = "https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={yyyymmdd}"
NAR_SHUTUBA_URL = "https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}"
JRA_SHUTUBA_URL = "https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
NAR_RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"
JRA_RESULT_URL = "https://race.netkeiba.com/race/result.html?race_id={race_id}"
RACE_ID_RE = re.compile(r"/race/(20\d{10})/?|race_id=(20\d{10})")
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
    for encoding in ["euc-jp", "cp932", "utf-8", "utf-8-sig"]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


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

    def _request(self, url: str) -> bytes:
        if self.max_requests and self.request_count >= self.max_requests:
            raise MaxRequestsReached(f"max requests reached: {self.max_requests}")

        self._wait()
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
            },
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


def race_url_for_dynamic_id(race_id: str, *, source: str, race_date: date) -> str:
    is_past = race_date < jst_today()
    if source == "jra":
        template = JRA_RESULT_URL if is_past else JRA_SHUTUBA_URL
    else:
        template = NAR_RESULT_URL if is_past else NAR_SHUTUBA_URL
    return template.format(race_id=race_id)


def scrape_calendar_pages(
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> tuple[list[str], list[dict[str, Any]]]:
    race_ids: list[str] = []
    results: list[dict[str, Any]] = []
    dynamic_page_urls: dict[str, str] = getattr(args, "race_page_urls", {}) or {}

    for day in date_range(parse_date(args.start_date), parse_date(args.end_date)):
        yyyymmdd = day.strftime("%Y%m%d")
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
                    )
            elif sub_result.status in {"blocked", "access_limited"}:
                sub_row["warning"] = f"netkeiba {source} race list blocked: {sub_result.status}"
            results.append(sub_row)

    args.race_page_urls = dynamic_page_urls
    return sorted(set(race_ids)), results


def scrape_race_pages(
    race_ids: list[str],
    args: argparse.Namespace,
    fetcher: RateLimitedFetcher,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    race_page_urls: dict[str, str] = getattr(args, "race_page_urls", {}) or {}

    for race_id in race_ids:
        race_url = race_page_urls.get(race_id, RACE_URL.format(race_id=race_id))
        result = fetcher.fetch(race_url, args.raw_dir / f"{race_id}.html")
        row = result.__dict__.copy()
        row["race_id"] = race_id
        results.append(row)
        if result.status in {"blocked", "access_limited"}:
            raise SystemExit(f"netkeiba access stopped: {result.status} {result.url}")

    return results


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
    return summary


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
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-calendar", action="store_true")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument(
        "--user-agent",
        default=(
            "UmaLabResearch/0.1 "
            "(public pages only; rate-limited; contact: local-user)"
        ),
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
    except MaxRequestsReached as exc:
        race_ids = sorted(set([*explicit_ids, *calendar_ids]))
        race_results = []
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
        "import": import_summary,
    }
    write_manifest(args.raw_dir / "scrape_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
