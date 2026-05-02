from __future__ import annotations

import argparse
from pathlib import Path


PLACE_CODES = {
    "01": "札幌",
    "02": "函館",
    "03": "福島",
    "04": "新潟",
    "05": "東京",
    "06": "中山",
    "07": "中京",
    "08": "京都",
    "09": "阪神",
    "10": "小倉",
}


def race_ids(start_year: int, end_year: int, max_meeting: int, max_day: int, races_per_day: int) -> list[str]:
    ids: list[str] = []
    for year in range(start_year, end_year + 1):
        for place_code in PLACE_CODES:
            for meeting in range(1, max_meeting + 1):
                for day in range(1, max_day + 1):
                    for race in range(1, races_per_day + 1):
                        ids.append(f"{year}{place_code}{meeting:02d}{day:02d}{race:02d}")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate candidate public netkeiba race result URLs.")
    parser.add_argument("--start-year", required=True, type=int)
    parser.add_argument("--end-year", required=True, type=int)
    parser.add_argument("--max-meeting", default=8, type=int)
    parser.add_argument("--max-day", default=12, type=int)
    parser.add_argument("--races-per-day", default=12, type=int)
    parser.add_argument("--output", default=Path("data/netkeiba_urls.txt"), type=Path)
    args = parser.parse_args()

    if args.start_year > args.end_year:
        raise ValueError("--start-year must be <= --end-year")

    urls = [f"https://db.netkeiba.com/race/{race_id}/" for race_id in race_ids(
        args.start_year,
        args.end_year,
        args.max_meeting,
        args.max_day,
        args.races_per_day,
    )]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(urls) + "\n", encoding="utf-8")
    print({"output": str(args.output), "urls": len(urls)})


if __name__ == "__main__":
    main()
