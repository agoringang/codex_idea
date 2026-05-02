from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path


def parse_date(value: str) -> date:
    year, month, day = value.split("-", 2)
    return date(int(year), int(month), int(day))


def dates(start_year: int, end_year: int, end_date: date | None = None) -> list[date]:
    current = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    if end_date and end_date < end:
        end = end_date
    values: list[date] = []
    while current <= end:
        values.append(current)
        current += timedelta(days=1)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily netkeiba race list URLs.")
    parser.add_argument("--start-year", required=True, type=int)
    parser.add_argument("--end-year", required=True, type=int)
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD cutoff inside --end-year.")
    parser.add_argument("--output", default=Path("data/netkeiba_list_urls.txt"), type=Path)
    args = parser.parse_args()

    if args.start_year > args.end_year:
        raise ValueError("--start-year must be <= --end-year")

    cutoff = parse_date(args.end_date) if args.end_date else None
    urls = [f"https://db.netkeiba.com/race/list/{day:%Y%m%d}/" for day in dates(args.start_year, args.end_year, cutoff)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(urls) + "\n", encoding="utf-8")
    print({"output": str(args.output), "urls": len(urls)})


if __name__ == "__main__":
    main()
