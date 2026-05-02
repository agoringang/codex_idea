from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self.hrefs.append(href)


def detect_encoding(body: bytes) -> str:
    head = body[:4096]
    match = re.search(rb"charset=['\"]?([A-Za-z0-9_\-]+)", head, flags=re.IGNORECASE)
    if match:
        return match.group(1).decode("ascii", errors="ignore")
    for encoding in ["utf-8", "euc-jp", "cp932"]:
        try:
            body.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def source_url_for(path: Path) -> str:
    sidecar = path.with_suffix(".url")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8").strip()
    return "https://db.netkeiba.com/"


def race_urls_from_file(path: Path) -> set[str]:
    body = path.read_bytes()
    html = body.decode(detect_encoding(body), errors="replace")
    parser = LinkParser()
    parser.feed(html)
    base = source_url_for(path)
    urls: set[str] = set()
    for href in parser.hrefs:
        absolute = urljoin(base, href)
        match = re.search(r"https://db\.netkeiba\.com/race/(\d{10,12})/?", absolute)
        if match:
            urls.add(f"https://db.netkeiba.com/race/{match.group(1)}/")
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract concrete race result URLs from cached netkeiba daily list pages.")
    parser.add_argument("--html-dir", default=Path("raw/netkeiba/list_html"), type=Path)
    parser.add_argument("--output", default=Path("data/netkeiba_race_urls.txt"), type=Path)
    args = parser.parse_args()

    urls: set[str] = set()
    for path in sorted(args.html_dir.glob("*.html")):
        urls.update(race_urls_from_file(path))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(sorted(urls)) + ("\n" if urls else ""), encoding="utf-8")
    print({"output": str(args.output), "urls": len(urls)})


if __name__ == "__main__":
    main()
