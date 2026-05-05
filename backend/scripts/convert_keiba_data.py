from __future__ import annotations

import argparse
import csv
from datetime import date
from math import ceil
from pathlib import Path
from typing import Any


EXPECTED_COLUMNS = 52


# 1-based source index map from keiba_data/*.CSV
COL = {
    "yy": 1,
    "mm": 2,
    "dd": 3,
    "venue": 5,
    "number": 7,
    "distance": 12,
    "going": 13,
    "surface": 10,
    "horse_name": 14,
    "sex": 15,
    "age": 16,
    "jockey": 17,
    "carried_weight": 18,
    "field_size": 19,
    "gate": 20,
    "finish_position": 21,
    "odds_rank": 25,
    "best_time": 26,
    "last600m": 33,
    "horse_weight": 34,
    "trainer": 35,
    "trainer_area": 36,
    "race_runner_id": 41,
    "owner": 42,
    "breeder": 43,
    "sire": 44,
    "dam_sire": 46,
    "market_odds": 49,
    "place_odds": 52,
}


def _value(row: list[str], key: str) -> str:
    index = COL[key] - 1
    if 0 <= index < len(row):
        return row[index].strip().strip('"')
    return ""


def _to_float(text: str) -> float | None:
    cleaned = text.replace(",", "").replace(" ", "").strip().strip('"')
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(text: str) -> int | None:
    value = _to_float(text)
    if value is None:
        return None
    return int(value)


def _parse_date(yy: str, mm: str, dd: str) -> str:
    y = _to_int(yy)
    m = _to_int(mm)
    d = _to_int(dd)
    if y is None or m is None or d is None:
        return ""

    year = 2000 + y if 0 <= y <= 69 else 1900 + y
    try:
        return date(year, m, d).isoformat()
    except ValueError:
        return ""


def _race_id_from_runner_id(race_runner_id: str) -> str:
    cleaned = race_runner_id.replace(" ", "").strip().strip('"')
    if len(cleaned) >= 8:
        return cleaned[:8]
    return ""


def _bracket_from_horse_number(horse_number: int | None) -> int | None:
    if horse_number is None or horse_number <= 0:
        return None
    return min(max(ceil(horse_number / 2), 1), 8)


def parse_file(path: Path, encoding: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) != EXPECTED_COLUMNS:
                continue

            race_runner_id = _value(row, "race_runner_id")
            race_id = _race_id_from_runner_id(race_runner_id)
            if not race_id:
                continue

            race_date = _parse_date(_value(row, "yy"), _value(row, "mm"), _value(row, "dd"))
            finish_position = _to_int(_value(row, "finish_position"))

            trainer_name = _value(row, "trainer")
            trainer_area = _value(row, "trainer_area")
            trainer = f"{trainer_name}({trainer_area})" if trainer_area else trainer_name
            race_no = _to_int(_value(row, "number"))
            horse_number = _to_int(_value(row, "gate"))
            bracket = _bracket_from_horse_number(horse_number)

            record: dict[str, Any] = {
                "race_id": race_id,
                "race_date": race_date,
                "race_no": race_no,
                "horse_number": horse_number,
                "runner_number": horse_number,
                "number": horse_number,
                "bracket": bracket,
                "gate": bracket,
                "horse_name": _value(row, "horse_name"),
                "venue": _value(row, "venue"),
                "distance": _to_int(_value(row, "distance")),
                "going": _value(row, "going"),
                "surface": _value(row, "surface"),
                "sex": _value(row, "sex"),
                "age": _to_int(_value(row, "age")),
                "jockey": _value(row, "jockey"),
                "trainer": trainer,
                "owner": _value(row, "owner"),
                "breeder": _value(row, "breeder"),
                "sire": _value(row, "sire"),
                "dam_sire": _value(row, "dam_sire"),
                "carried_weight": _to_float(_value(row, "carried_weight")),
                "horse_weight": _to_int(_value(row, "horse_weight")),
                "field_size": _to_int(_value(row, "field_size")),
                "finish_position": finish_position,
                "is_win": 1 if finish_position == 1 else 0,
                "is_place": 1 if finish_position is not None and finish_position <= 3 else 0,
                "market_odds": _to_float(_value(row, "market_odds")),
                "place_odds": _to_float(_value(row, "place_odds")),
                "odds_rank": _to_int(_value(row, "odds_rank")),
                "best_time": _to_float(_value(row, "best_time")),
                "last600m": _to_float(_value(row, "last600m")),
                "source_file": path.name,
                "source_runner_id": race_runner_id,
            }
            rows.append(record)

    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert keiba_data CSV files to normalized training CSV"
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/keiba_data"))
    parser.add_argument("--output", type=Path, default=Path("data/keiba_history_normalized.csv"))
    parser.add_argument("--encoding", default="cp932")
    parser.add_argument("--glob", default="*.CSV")
    parser.add_argument("--limit-files", type=int, default=0)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_path: Path = args.output

    files = sorted(input_dir.glob(args.glob))
    if args.limit_files > 0:
        files = files[: args.limit_files]

    if not files:
        raise SystemExit(f"no files found: {input_dir} ({args.glob})")

    records: list[dict[str, Any]] = []
    for file_path in files:
        records.extend(parse_file(file_path, args.encoding))

    if not records:
        raise SystemExit("no records parsed")

    records = sorted(
        records,
        key=lambda row: (
            row.get("race_date") or "",
            row.get("race_id") or "",
            row.get("horse_number") if row.get("horse_number") is not None else 999,
        ),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].keys())
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    race_ids = {str(row["race_id"]) for row in records if row.get("race_id")}

    summary = {
        "files": len(files),
        "rows": int(len(records)),
        "races": int(len(race_ids)),
        "output": str(output_path),
    }
    print(summary)


if __name__ == "__main__":
    main()
