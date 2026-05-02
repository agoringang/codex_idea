from __future__ import annotations

import argparse
import csv
import hashlib
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request, robotparser


ALLOWED_HOSTS = {"db.netkeiba.com"}
BLOCK_STATUSES = {403, 429}


def normalize_url(line: str) -> str | None:
    value = line.strip()
    if not value or value.startswith("#"):
        return None
    if value.isdigit():
        return f"https://db.netkeiba.com/race/{value}/"
    return value


def read_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        url = normalize_url(line)
        if url:
            urls.append(url)
    return urls


def cache_name(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def allowed_host(url: str) -> bool:
    return parse.urlparse(url).netloc in ALLOWED_HOSTS


def robots_allowed(url: str, user_agent: str, cache: dict[str, robotparser.RobotFileParser], lock: threading.Lock) -> tuple[bool, str]:
    parsed = parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    with lock:
        if origin not in cache:
            robots = robotparser.RobotFileParser()
            robots.set_url(f"{origin}/robots.txt")
            try:
                robots.read()
            except Exception as exc:
                return False, f"robots_unavailable:{type(exc).__name__}"
            cache[origin] = robots

        return cache[origin].can_fetch(user_agent, url), "robots_ok"


class RateLimiter:
    def __init__(self, delay_seconds: float, jitter_seconds: float):
        self.delay_seconds = delay_seconds
        self.jitter_seconds = jitter_seconds
        self.lock = threading.Lock()
        self.next_time = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now < self.next_time:
                time.sleep(self.next_time - now)

            interval = self.delay_seconds + random.uniform(0, self.jitter_seconds)
            self.next_time = time.monotonic() + interval


def fetch_url(url: str, user_agent: str, timeout: int) -> tuple[int, bytes, str]:
    req = request.Request(url, headers={"User-Agent": user_agent})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return int(response.status), response.read(), ""
    except error.HTTPError as exc:
        return int(exc.code), exc.read(), str(exc)
    except error.URLError as exc:
        return 0, b"", str(exc)


def write_manifest_row(path: Path, row: dict[str, str | int], lock: threading.Lock) -> None:
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "fetched_at",
                    "url",
                    "status",
                    "cache_path",
                    "sidecar_path",
                    "message",
                ],
            )
            if not exists:
                writer.writeheader()
            writer.writerow(row)


def process_url(
    index: int,
    total: int,
    url: str,
    args: argparse.Namespace,
    robots_cache: dict[str, robotparser.RobotFileParser],
    robots_lock: threading.Lock,
    manifest_lock: threading.Lock,
    rate_limiter: RateLimiter,
    stop_event: threading.Event,
) -> dict[str, str | int]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    digest = cache_name(url)
    html_path = args.output_dir / f"{digest}.html"
    sidecar_path = args.output_dir / f"{digest}.url"

    if stop_event.is_set():
        return {"index": index, "total": total, "url": url, "status": "skipped_stopped"}

    if not allowed_host(url):
        row = {
            "fetched_at": fetched_at,
            "url": url,
            "status": "skipped_host",
            "cache_path": "",
            "sidecar_path": "",
            "message": "only db.netkeiba.com is allowed",
        }
        write_manifest_row(args.manifest, row, manifest_lock)
        return {"index": index, "total": total, "url": url, "status": "skipped_host"}

    if html_path.exists() and not args.refresh:
        row = {
            "fetched_at": fetched_at,
            "url": url,
            "status": "cached",
            "cache_path": str(html_path),
            "sidecar_path": str(sidecar_path),
            "message": "",
        }
        write_manifest_row(args.manifest, row, manifest_lock)
        return {"index": index, "total": total, "url": url, "status": "cached"}

    can_fetch, robots_message = robots_allowed(url, args.user_agent, robots_cache, robots_lock)
    if not can_fetch:
        row = {
            "fetched_at": fetched_at,
            "url": url,
            "status": "skipped_robots",
            "cache_path": "",
            "sidecar_path": "",
            "message": robots_message,
        }
        write_manifest_row(args.manifest, row, manifest_lock)
        return {"index": index, "total": total, "url": url, "status": "skipped_robots"}

    rate_limiter.wait()

    status, body, message = fetch_url(url, args.user_agent, args.timeout_seconds)

    if status == 200 and body:
        html_path.write_bytes(body)
        sidecar_path.write_text(url + "\n", encoding="utf-8")
        cache_path = str(html_path)
        sidecar = str(sidecar_path)
    else:
        cache_path = ""
        sidecar = ""

    row = {
        "fetched_at": fetched_at,
        "url": url,
        "status": status,
        "cache_path": cache_path,
        "sidecar_path": sidecar,
        "message": message,
    }
    write_manifest_row(args.manifest, row, manifest_lock)

    if status in BLOCK_STATUSES:
        stop_event.set()

    return {"index": index, "total": total, "url": url, "status": status}


def main() -> None:
    parser = argparse.ArgumentParser(description="Polite parallel fetcher for public netkeiba pages.")
    parser.add_argument("--url-file", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("raw/netkeiba/html"), type=Path)
    parser.add_argument("--manifest", default=Path("raw/netkeiba/manifest.csv"), type=Path)
    parser.add_argument("--delay-seconds", default=1.0, type=float)
    parser.add_argument("--jitter-seconds", default=0.3, type=float)
    parser.add_argument("--timeout-seconds", default=20, type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--user-agent",
        default="RaceQuantResearchBot/0.1 personal-use low-rate cache-respecting",
    )
    args = parser.parse_args()

    urls = read_urls(args.url_file)
    if args.max_pages:
        urls = urls[: args.max_pages]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    robots_cache: dict[str, robotparser.RobotFileParser] = {}
    robots_lock = threading.Lock()
    manifest_lock = threading.Lock()
    stop_event = threading.Event()
    rate_limiter = RateLimiter(args.delay_seconds, args.jitter_seconds)

    total = len(urls)
    workers = max(1, min(args.workers, 8))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                process_url,
                index,
                total,
                url,
                args,
                robots_cache,
                robots_lock,
                manifest_lock,
                rate_limiter,
                stop_event,
            )
            for index, url in enumerate(urls, start=1)
        ]

        for future in as_completed(futures):
            result = future.result()
            print(result)

            if result["status"] in BLOCK_STATUSES:
                print({"stopped": True, "reason": "blocked_or_rate_limited"})
                break


if __name__ == "__main__":
    main()