from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


RESULT_MARKERS = {"着順", "馬番", "馬名"}

OUTPUT_COLUMNS = [
    "race_id",
    "race_date",
    "runner_id",
    "gate",
    "number",
    "name",
    "finish_position",
    "is_win",
    "is_place",
    "sex",
    "age",
    "carried_weight",
    "jockey",
    "trainer",
    "horse_weight",
    "horse_weight_diff",
    "market_odds",
    "odds_rank",
    "best_time",
    "last600m",
    "venue",
    "surface",
    "distance",
    "going",
    "weather",
    "source_url",
]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", value)


class TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict[str, Any]]]] = []
        self.full_text: list[str] = []
        self._table_depth = 0
        self._rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif tag == "tr" and self._table_depth:
            self._row = []
        elif tag in {"th", "td"} and self._table_depth and self._row is not None:
            self._cell = {"text": [], "links": []}
        elif tag == "a" and self._cell is not None:
            href = attrs_dict.get("href")
            if href:
                self._cell["links"].append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._cell["text"] = clean_text(" ".join(self._cell["text"]))
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._table_depth and self._row is not None:
            if self._row:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._rows:
                self.tables.append(self._rows)
                self._rows = []

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if text:
            self.full_text.append(text)
        if self._cell is not None:
            self._cell["text"].append(data)


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


def parse_html(path: Path) -> tuple[TableHTMLParser, str]:
    body = path.read_bytes()
    encoding = detect_encoding(body)
    html = body.decode(encoding, errors="replace")
    parser = TableHTMLParser()
    parser.feed(html)
    return parser, " ".join(parser.full_text)


def cell_text(cell: dict[str, Any]) -> str:
    return str(cell.get("text", ""))


def header_index(headers: list[str], candidates: list[str]) -> int | None:
    normalized = [normalize_header(header) for header in headers]
    for candidate in candidates:
        for index, header in enumerate(normalized):
            if candidate in header:
                return index
    return None


def find_result_table(tables: list[list[list[dict[str, Any]]]]) -> tuple[list[str], list[list[dict[str, Any]]]] | None:
    for table in tables:
        if not table:
            continue

        headers = [cell_text(cell) for cell in table[0]]
        normalized_headers = [normalize_header(header) for header in headers]

        if RESULT_MARKERS.issubset(set(normalized_headers)) or all(
            any(marker in header for header in normalized_headers)
            for marker in RESULT_MARKERS
        ):
            return normalized_headers, table[1:]

    return None


def parse_float(value: str) -> float | None:
    value = clean_text(value).replace(",", "")
    if not value or value in {"---", "--", "-"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def parse_int(value: str) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None else None


def parse_finish(value: str) -> int | None:
    match = re.match(r"\d+", clean_text(value))
    return int(match.group(0)) if match else None


def parse_sex_age(value: str) -> tuple[str | None, int | None]:
    match = re.match(r"([牡牝セせ騸])\s*(\d+)", clean_text(value))
    if not match:
        return None, None
    sex = "せん" if match.group(1) in {"セ", "せ", "騸"} else match.group(1)
    return sex, int(match.group(2))


def parse_weight(value: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d+)\s*(?:\(([+-]?\d+)\))?", clean_text(value))
    if not match:
        return None, None
    diff = int(match.group(2)) if match.group(2) else None
    return int(match.group(1)), diff


def parse_time(value: str) -> float | None:
    value = clean_text(value)
    if not value:
        return None
    if ":" in value:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + float(seconds)
    return parse_float(value)


def extract_race_id(url: str | None, path: Path) -> str:
    if url:
        match = re.search(r"/race/(\d+)/?", url)
        if match:
            return match.group(1)
    match = re.search(r"(\d{10,12})", path.stem)
    return match.group(1) if match else path.stem


def source_url_for(path: Path) -> str | None:
    sidecar = path.with_suffix(".url")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8").strip()
    return None


def extract_metadata(text: str) -> dict[str, Any]:
    date_match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    race_date = None
    if date_match:
        race_date = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    venue = None
    for candidate in ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]:
        if candidate in text:
            venue = candidate
            break

    course_match = re.search(r"(芝|ダート|障害)\s*(\d{3,4})m", text)
    going_match = re.search(r"馬場\s*[:：]?\s*(良|稍重|重|不良)", text)
    weather_match = re.search(r"天候\s*[:：]?\s*(晴|曇|雨|小雨|雪|小雪)", text)
    return {
        "race_date": race_date,
        "venue": venue,
        "surface": course_match.group(1) if course_match else None,
        "distance": int(course_match.group(2)) if course_match else None,
        "going": going_match.group(1) if going_match else None,
        "weather": weather_match.group(1) if weather_match else None,
    }


def link_id(cell: dict[str, Any], pattern: str) -> str | None:
    for href in cell.get("links", []):
        match = re.search(pattern, str(href))
        if match:
            return match.group(1)
    return None


def parse_result_file(path: Path) -> list[dict[str, Any]]:
    parser, text = parse_html(path)
    result = find_result_table(parser.tables)
    if result is None:
        return []

    headers, rows = result
    source_url = source_url_for(path)
    race_id = extract_race_id(source_url, path)
    metadata = extract_metadata(text)

    idx = {
        "finish": header_index(headers, ["着順", "着"]),
        "gate": header_index(headers, ["枠番", "枠"]),
        "number": header_index(headers, ["馬番"]),
        "name": header_index(headers, ["馬名"]),
        "sex_age": header_index(headers, ["性齢"]),
        "carried_weight": header_index(headers, ["斤量"]),
        "jockey": header_index(headers, ["騎手"]),
        "time": header_index(headers, ["タイム"]),
        "last600m": header_index(headers, ["上り"]),
        "odds": header_index(headers, ["単勝"]),
        "odds_rank": header_index(headers, ["人気"]),
        "horse_weight": header_index(headers, ["馬体重"]),
        "trainer": header_index(headers, ["調教師"]),
    }

    if any(idx[k] is None for k in ["finish", "number", "name"]):
        return []

    parsed_rows = []
    for row in rows:
        if len(row) < len(headers):
            continue

        finish_position = parse_finish(cell_text(row[idx["finish"]]))
        number = parse_int(cell_text(row[idx["number"]]))
        if finish_position is None or number is None:
            continue

        name_cell = row[idx["name"]]
        sex, age = parse_sex_age(cell_text(row[idx["sex_age"]])) if idx["sex_age"] is not None else (None, None)
        horse_weight, horse_weight_diff = parse_weight(cell_text(row[idx["horse_weight"]])) if idx["horse_weight"] is not None else (None, None)

        parsed_rows.append({
            "race_id": race_id,
            "race_date": metadata["race_date"],
            "runner_id": link_id(name_cell, r"/horse/(\d+)"),
            "gate": parse_int(cell_text(row[idx["gate"]])) if idx["gate"] is not None else None,
            "number": number,
            "name": cell_text(name_cell),
            "finish_position": finish_position,
            "is_win": int(finish_position == 1),
            "is_place": int(finish_position <= 3),
            "sex": sex,
            "age": age,
            "carried_weight": parse_float(cell_text(row[idx["carried_weight"]])) if idx["carried_weight"] is not None else None,
            "jockey": cell_text(row[idx["jockey"]]) if idx["jockey"] is not None else None,
            "trainer": cell_text(row[idx["trainer"]]) if idx["trainer"] is not None else None,
            "horse_weight": horse_weight,
            "horse_weight_diff": horse_weight_diff,
            "market_odds": parse_float(cell_text(row[idx["odds"]])) if idx["odds"] is not None else None,
            "odds_rank": parse_int(cell_text(row[idx["odds_rank"]])) if idx["odds_rank"] is not None else None,
            "best_time": parse_time(cell_text(row[idx["time"]])) if idx["time"] is not None else None,
            "last600m": parse_time(cell_text(row[idx["last600m"]])) if idx["last600m"] is not None else None,
            "venue": metadata["venue"],
            "surface": metadata["surface"],
            "distance": metadata["distance"],
            "going": metadata["going"],
            "weather": metadata["weather"],
            "source_url": source_url,
        })

    return parsed_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for p in args.html_dir.glob("*.html"):
        rows.extend(parse_result_file(p))

    df = pd.DataFrame(rows)
    df.to_csv(args.output, index=False)
    print(f"rows={len(df)}")


if __name__ == "__main__":
    main()