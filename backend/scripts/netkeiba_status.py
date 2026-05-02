from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open(encoding="utf-8"))


def manifest_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    counts: Counter[str] = Counter()
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            counts[str(row.get("status", ""))] += 1
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show netkeiba collection progress.")
    parser.add_argument("--status", default=Path("runtime/netkeiba_collect_status.json"), type=Path)
    parser.add_argument("--pid-file", default=Path("runtime/netkeiba_collect.pid"), type=Path)
    parser.add_argument("--list-url-file", default=Path("data/netkeiba_list_urls.txt"), type=Path)
    parser.add_argument("--race-url-file", default=Path("data/netkeiba_race_urls.txt"), type=Path)
    args = parser.parse_args()

    status = json.loads(args.status.read_text(encoding="utf-8")) if args.status.exists() else {}
    pid = args.pid_file.read_text(encoding="utf-8").strip() if args.pid_file.exists() else None
    payload = {
        "pid": pid,
        "status": status,
        "list_urls": count_lines(args.list_url_file),
        "race_urls": count_lines(args.race_url_file),
        "list_manifest": manifest_counts(Path("raw/netkeiba/list_manifest.csv")),
        "race_manifest": manifest_counts(Path("raw/netkeiba/race_manifest.csv")),
        "list_html_files": len(list(Path("raw/netkeiba/list_html").glob("*.html"))),
        "race_html_files": len(list(Path("raw/netkeiba/html").glob("*.html"))),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
