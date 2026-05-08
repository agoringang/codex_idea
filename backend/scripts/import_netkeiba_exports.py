from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


JRA_AND_LOCAL_VENUES = [
    "札幌",
    "函館",
    "福島",
    "新潟",
    "東京",
    "中山",
    "中京",
    "京都",
    "阪神",
    "小倉",
    "門別",
    "盛岡",
    "水沢",
    "浦和",
    "船橋",
    "大井",
    "川崎",
    "金沢",
    "笠松",
    "名古屋",
    "園田",
    "姫路",
    "高知",
    "佐賀",
    "帯広",
]
VENUE_BY_RACE_ID_CODE = {
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
    "30": "門別",
    "35": "盛岡",
    "36": "水沢",
    "42": "浦和",
    "43": "船橋",
    "44": "大井",
    "45": "川崎",
    "46": "金沢",
    "47": "笠松",
    "48": "名古屋",
    "50": "園田",
    "51": "姫路",
    "54": "高知",
    "55": "佐賀",
    "65": "帯広",
}

ALIASES: dict[str, tuple[str, ...]] = {
    "race_id": ("race_id", "レースID", "レースid", "raceid"),
    "race_date": ("race_date", "日付", "年月日", "開催日", "date"),
    "race_no": ("race_no", "R", "レース", "レース番号", "race"),
    "finish_position": ("finish_position", "着順", "着", "順位"),
    "runner_status": ("runner_status", "出走状態", "競走状態", "状態", "備考", "取消除外"),
    "runner_number": ("runner_number", "horse_number", "number", "馬番", "馬"),
    "bracket": ("bracket", "枠", "枠番"),
    "horse_name": ("horse_name", "馬名", "name", "競走馬"),
    "sex_age": ("性齢", "性令", "sex_age"),
    "sex": ("sex", "性"),
    "age": ("age", "齢", "年齢"),
    "carried_weight": ("carried_weight", "斤量", "負担重量"),
    "jockey": ("jockey", "騎手"),
    "trainer": ("trainer", "調教師", "厩舎", "所属"),
    "horse_weight": ("horse_weight", "馬体重", "馬体重(増減)", "馬体重（増減）"),
    "horse_weight_diff": ("horse_weight_diff", "増減", "馬体重増減"),
    "body_weight_announced_at": ("body_weight_announced_at", "馬体重発表", "馬体重発表時刻"),
    "market_odds": ("market_odds", "単勝", "オッズ", "単勝オッズ"),
    "place_odds": ("place_odds", "複勝", "複勝オッズ"),
    "odds_rank": ("odds_rank", "人気", "単勝人気"),
    "distance": ("distance", "距離"),
    "surface": ("surface", "馬場", "コース", "種別"),
    "going": ("going", "馬場状態", "馬場状態(芝)", "馬場状態(ダ)"),
    "weather": ("weather", "天候"),
    "start_time": ("start_time", "post_time", "race_time", "発走", "発走時刻", "発走予定"),
    "running_style": ("running_style", "脚質"),
    "sire": ("sire", "父", "父名"),
    "sire_id": ("sire_id", "父ID", "種牡馬ID"),
    "dam_sire": ("dam_sire", "母父", "母の父"),
    "dam_sire_id": ("dam_sire_id", "母父ID", "母の父ID"),
    "training_score": ("training_score", "調教", "調教評価", "追い切り"),
    "bloodline_score": ("bloodline_score", "血統", "血統評価"),
    "paddock_score": ("paddock_score", "パドック", "気配"),
    "odds_delta": ("odds_delta", "オッズ変動", "変動", "前回比"),
    "odds_delta_5m": ("odds_delta_5m", "5分オッズ変動", "直前5分変動"),
    "odds_delta_15m": ("odds_delta_15m", "15分オッズ変動", "直前15分変動"),
    "odds_volatility": ("odds_volatility", "オッズ変動率", "オッズボラ"),
    "odds_snapshot_at": ("odds_snapshot_at", "オッズ取得時刻", "オッズ更新時刻"),
    "ticket_pool_share": ("ticket_pool_share", "票数シェア", "支持率"),
    "last600m": ("last600m", "上り", "上がり", "後3F", "3F"),
    "lap_3f": ("lap_3f", "ラップ3F", "前半3F", "3F"),
    "lap_4f": ("lap_4f", "ラップ4F", "前半4F", "4F"),
}

PAYOUT_BET_TYPES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("trifecta", "payout_trifecta", ("三連単", "3連単")),
    ("trio", "payout_trio", ("三連複", "3連複")),
    ("exacta", "payout_exacta", ("馬単",)),
    ("wide", "payout_wide", ("ワイド",)),
    ("quinella", "payout_quinella", ("馬連",)),
    ("bracket_quinella", "payout_bracket_quinella", ("枠連",)),
    ("place", "payout_place", ("複勝",)),
    ("win", "payout_win", ("単勝",)),
)

PAYOUT_COLUMNS_BY_TYPE = {
    bet_type: column for bet_type, column, _aliases in PAYOUT_BET_TYPES
}

PAYOUT_ROW_CLASS_TYPES = {
    "Tansho": "win",
    "Fukusho": "place",
    "Wakuren": "bracket_quinella",
    "Umaren": "quinella",
    "Wide": "wide",
    "Umatan": "exacta",
    "Fuku3": "trio",
    "Tan3": "trifecta",
}

OUTPUT_COLUMNS = [
    "race_id",
    "race_date",
    "race_no",
    "horse_number",
    "runner_number",
    "number",
    "bracket",
    "gate",
    "horse_name",
    "venue",
    "distance",
    "going",
    "surface",
    "weather",
    "start_time",
    "post_time",
    "body_weight_announced_at",
    "odds_snapshot_at",
    "sex",
    "age",
    "jockey",
    "trainer",
    "running_style",
    "sire",
    "sire_id",
    "dam_sire",
    "dam_sire_id",
    "carried_weight",
    "horse_weight",
    "horse_weight_diff",
    "field_size",
    "finish_position",
    "runner_status",
    "scratched",
    "is_win",
    "is_place",
    "market_odds",
    "place_odds",
    "odds_rank",
    "odds_delta",
    "odds_delta_5m",
    "odds_delta_15m",
    "odds_volatility",
    "ticket_pool_share",
    "training_score",
    "bloodline_score",
    "paddock_score",
    "last600m",
    "lap_3f",
    "lap_4f",
    "payout_win",
    "payout_place",
    "payout_bracket_quinella",
    "payout_quinella",
    "payout_wide",
    "payout_exacta",
    "payout_trio",
    "payout_trifecta",
    "payouts_json",
    "source_file",
    "source_table",
    "source_runner_id",
]


@dataclass
class SourceTable:
    frame: pd.DataFrame
    index: int
    text: str


class SimpleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif tag == "tr" and self._table_depth:
            self._row = []
        elif tag in {"th", "td"} and self._table_depth and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._rows:
                self.tables.append(self._rows)
                self._rows = []


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = html.unescape(str(value)).replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalized_name(value: Any) -> str:
    text = clean_text(value)
    return (
        text.replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("　", "")
        .replace("（", "(")
        .replace("）", ")")
    )


def dedupe_columns(columns: Iterable[Any]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        name = normalized_name(column) or "column"
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}_{count + 1}")
    return result


def flatten_column_name(column: Any) -> str:
    if isinstance(column, tuple):
        parts = [
            clean_text(part)
            for part in column
            if clean_text(part) and not clean_text(part).startswith("Unnamed:")
        ]
        return normalized_name(parts[-1] if parts else "")
    return normalized_name(column)


def known_column_score(columns: Iterable[Any]) -> int:
    names = {normalized_name(column) for column in columns}
    score = 0
    for aliases in ALIASES.values():
        if any(normalized_name(alias) in names for alias in aliases):
            score += 1
    return score


def table_frame(rows: list[list[str]]) -> pd.DataFrame | None:
    if len(rows) < 2:
        return None

    header_index = max(range(min(4, len(rows))), key=lambda index: known_column_score(rows[index]))
    headers = dedupe_columns(rows[header_index])
    body = [row for row in rows[header_index + 1 :] if any(clean_text(cell) for cell in row)]
    if not body:
        return None

    width = len(headers)
    padded = [(row + [""] * width)[:width] for row in body]
    return pd.DataFrame(padded, columns=headers)


def read_csv_frame(path: Path, encoding: str) -> pd.DataFrame:
    encodings = [encoding, "utf-8-sig", "utf-8", "cp932", "euc-jp"]
    last_error: Exception | None = None
    for candidate in dict.fromkeys(encodings):
        try:
            return pd.read_csv(path, dtype=str, encoding=candidate, low_memory=False)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError(f"could not read CSV: {path}")


def read_text_file(path: Path, encoding: str) -> str:
    raw = path.read_bytes()
    best_text = ""
    best_score = -10**9
    for candidate in dict.fromkeys([encoding, "utf-8-sig", "utf-8", "euc-jp", "cp932"]):
        text = raw.decode(candidate, errors="replace")
        score = sum(
            text.count(token) * 100
            for token in ("馬名", "騎手", "レース", "出馬表", "着順", "オッズ")
        ) - text.count("\ufffd")
        if score > best_score:
            best_text = text
            best_score = score
    return best_text


def text_from_html_fragment(fragment: str) -> str:
    text = html.unescape(fragment)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def first_regex_group(patterns: Iterable[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return text_from_html_fragment(match.group(1))
    return ""


def jra_shutuba_frame_from_html(text: str) -> pd.DataFrame | None:
    if "Shutuba_Table" not in text or "HorseList" not in text:
        return None

    rows: list[dict[str, str]] = []
    for match in re.finditer(
        r"<tr\b[^>]*class=[\"'][^\"']*HorseList[^\"']*[\"'][^>]*id=[\"']tr_(\d+)[\"'][^>]*>(.*?)</tr>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        row_html = match.group(2)
        cells = list(re.finditer(r"<td\b([^>]*)>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL))
        cell_texts = [text_from_html_fragment(cell.group(2)) for cell in cells]
        runner_number = cell_texts[1] if len(cell_texts) > 1 and re.fullmatch(r"\d{1,2}", cell_texts[1]) else match.group(1)

        horse_name = first_regex_group(
            [
                r"class=[\"'][^\"']*HorseName[^\"']*[\"'][^>]*>\s*<a\b[^>]*title=[\"']([^\"']+)[\"']",
                r"class=[\"'][^\"']*HorseName[^\"']*[\"'][^>]*>(.*?)</span>",
            ],
            row_html,
        )
        if not horse_name:
            continue

        bracket = cell_texts[0] if len(cell_texts) > 0 else ""
        sex_age = cell_texts[4] if len(cell_texts) > 4 else ""
        carried_weight = cell_texts[5] if len(cell_texts) > 5 else ""
        jockey = first_regex_group([r"<td\b[^>]*class=[\"'][^\"']*Jockey[^\"']*[\"'][^>]*>(.*?)</td>"], row_html)
        trainer = first_regex_group([r"<td\b[^>]*class=[\"'][^\"']*Trainer[^\"']*[\"'][^>]*>(.*?)</td>"], row_html)
        horse_weight = first_regex_group([r"<td\b[^>]*class=[\"'][^\"']*Weight[^\"']*[\"'][^>]*>(.*?)</td>"], row_html)
        odds = first_regex_group([r"id=[\"']odds-[^\"']+_[^\"']+[\"'][^>]*>(.*?)</span>"], row_html)
        odds_rank = first_regex_group([r"id=[\"']ninki-[^\"']+_[^\"']+[\"'][^>]*>(.*?)</span>"], row_html)

        rows.append(
            {
                "枠": bracket,
                "馬番": runner_number,
                "馬名": horse_name,
                "性齢": sex_age,
                "斤量": carried_weight,
                "騎手": jockey,
                "厩舎": trainer,
                "馬体重(増減)": horse_weight,
                "単勝": odds,
                "人気": odds_rank,
            }
        )

    if not rows:
        return None
    return pd.DataFrame(rows)


def read_source_tables(path: Path, encoding: str) -> list[SourceTable]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        frame = read_csv_frame(path, encoding)
        frame.columns = dedupe_columns(frame.columns)
        return [SourceTable(frame=frame, index=0, text="")]
    if suffix == ".tsv":
        frame = pd.read_csv(path, dtype=str, encoding=encoding, sep="\t", low_memory=False)
        frame.columns = dedupe_columns(frame.columns)
        return [SourceTable(frame=frame, index=0, text="")]
    if suffix in {".html", ".htm"}:
        text = read_text_file(path, encoding)
        custom_jra_frame = jra_shutuba_frame_from_html(text)
        if custom_jra_frame is not None:
            return [SourceTable(frame=custom_jra_frame.astype(str), index=0, text=text)]

        tables: list[SourceTable] = []
        try:
            parsed_frames = pd.read_html(text)
        except (ImportError, ValueError):
            parsed_frames = []
        for index, frame in enumerate(parsed_frames):
            frame = frame.copy()
            frame.columns = dedupe_columns(flatten_column_name(column) for column in frame.columns)
            tables.append(SourceTable(frame=frame.astype(str), index=index, text=text))
        if tables:
            return tables

        parser = SimpleTableParser()
        parser.feed(text)
        for index, rows in enumerate(parser.tables):
            frame = table_frame(rows)
            if frame is not None:
                tables.append(SourceTable(frame=frame, index=index, text=text))
        return tables
    raise ValueError(f"unsupported file type: {path.suffix}")


def find_column(frame: pd.DataFrame, key: str) -> str | None:
    names = {normalized_name(column): column for column in frame.columns}
    for alias in ALIASES[key]:
        found = names.get(normalized_name(alias))
        if found is not None:
            return str(found)
    return None


def first_value(row: pd.Series, frame: pd.DataFrame, key: str) -> str:
    column = find_column(frame, key)
    if column is None:
        return ""
    return clean_text(row.get(column))


def to_float(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text in {"-", "--", "取消", "除外", "中止"}:
        return None
    text = text.translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    text = re.sub(r"[^\d.+-]", "", text)
    if not text or text in {".", "+", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    numeric = to_float(value)
    if numeric is None:
        return None
    return int(numeric)


def normalize_digits(value: Any) -> str:
    return clean_text(value).translate(
        str.maketrans("０１２３４５６７８９－ー―", "0123456789---")
    )


def parse_finish_position(value: Any) -> int | None:
    text = clean_text(value)
    if text in {"", "-", "--", "取消", "除外", "中止", "失格"}:
        return None
    normalized = normalize_digits(text)
    match = re.search(r"\d+", normalized)
    return int(match.group(0)) if match else None


def parse_runner_status(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        compact = text.replace(" ", "").replace("\u3000", "")
        if "競走除外" in compact or "発走除外" in compact or "除外" in compact:
            return "除外"
        if "出走取消" in compact or "取消" in compact:
            return "取消"
    return ""


def parse_sex_age(value: Any) -> tuple[str, int | None]:
    text = clean_text(value)
    if not text:
        return "", None
    normalized = normalize_digits(text)
    match = re.search(r"([牡牝セ騸])\s*(\d+)", normalized)
    if not match:
        return text[:1], to_int(text)
    return match.group(1), int(match.group(2))


def parse_horse_weight(value: Any) -> tuple[int | None, int | None]:
    text = clean_text(value).translate(
        str.maketrans("０１２３４５６７８９＋－", "0123456789+-")
    )
    if not text:
        return None, None
    weight = to_int(text.split("(")[0].split("（")[0])
    diff_match = re.search(r"[(（]\s*([+-]?\d+)\s*[)）]", text)
    diff = int(diff_match.group(1)) if diff_match else None
    if weight is not None and not 250 <= weight <= 700:
        weight = None
    if diff is not None and abs(diff) > 80:
        diff = None
    if weight is None:
        diff = None
    return weight, diff


def parse_date_text(value: Any) -> str:
    text = normalize_digits(value)
    if not text:
        return ""
    for pattern in [
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
        r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",
    ]:
        match = re.search(pattern, text)
        if not match:
            continue
        year, month, day = map(int, match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    return ""


def infer_date(path: Path, text: str, default_date: str) -> str:
    return (
        parse_date_text(path.name)
        or parse_date_text(text[:20000])
        or parse_date_text(default_date)
    )


def infer_race_id(
    path: Path,
    text: str,
    table_index: int,
    race_date: str,
    race_no: int | None,
) -> str:
    path_match = re.search(r"(20\d{10})", path.stem)
    if path_match:
        return path_match.group(1)
    text_match = re.search(r"race_id[=/](20\d{10})", text)
    if text_match:
        return text_match.group(1)
    compact_date = race_date.replace("-", "") if race_date else "unknown"
    race_part = f"{race_no:02d}" if race_no else f"t{table_index:02d}"
    return f"{compact_date}-{path.stem}-{race_part}"


def infer_race_no(path: Path, text: str, default_race_no: int | None) -> int | None:
    for source in [path.stem, text[:10000]]:
        match = re.search(r"(?<!\d)(\d{1,2})\s*R", source, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return default_race_no


def infer_venue(path: Path, text: str, default_venue: str) -> str:
    race_id_match = re.search(r"(20\d{10})", f"{path.stem} {text[:2000]}")
    if race_id_match:
        venue = VENUE_BY_RACE_ID_CODE.get(race_id_match.group(1)[4:6])
        if venue:
            return venue

    haystack = f"{path.name} {text[:20000]}"
    for venue in JRA_AND_LOCAL_VENUES:
        if re.search(rf"{re.escape(venue)}\s*\d{{1,2}}R", haystack):
            return venue
    for venue in JRA_AND_LOCAL_VENUES:
        if venue in haystack:
            return venue
    return default_venue


def infer_course(
    text: str,
    default_surface: str,
    default_distance: int | None,
) -> tuple[str, int | None]:
    target = text[:20000].replace("ダート", "ダ")
    match = re.search(r"(芝|ダ|障)\s*[右左直外内]*\s*(\d{3,4})m", target)
    if not match:
        return default_surface, default_distance
    surface = {"芝": "芝", "ダ": "ダート", "障": "障害"}[match.group(1)]
    return surface, int(match.group(2))


def infer_weather(text: str, default_weather: str) -> str:
    match = re.search(r"天候\s*[:：]\s*([^\s/<]+)", text[:20000])
    return match.group(1) if match else default_weather


def infer_going(text: str, default_going: str) -> str:
    match = re.search(
        r"(?:芝|ダート|ダ|障害|障)\s*[:：]\s*(良|稍重|重|不良)",
        text[:20000],
    )
    return match.group(1) if match else default_going


def infer_start_time(text: str, default_start_time: str = "") -> str:
    target = normalize_digits(text[:30000])
    patterns = [
        r"(\d{1,2}:\d{2})\s*発走",
        r"発走\s*[:：]?\s*(\d{1,2}:\d{2})",
        r"発走予定\s*[:：]?\s*(\d{1,2}:\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, target)
        if match:
            return match.group(1)
    return default_start_time


def infer_lap_metric(text: str, label: str) -> float | None:
    target = normalize_digits(text[:50000])
    if label == "lap_3f":
        patterns = [r"(?:前半3F|3F)\s*[:：]?\s*(\d{2}\.\d)", r"上(?:り|がり)\s*[:：]?\s*(\d{2}\.\d)"]
    else:
        patterns = [r"(?:前半4F|4F)\s*[:：]?\s*(\d{2}\.\d)"]
    for pattern in patterns:
        match = re.search(pattern, target)
        if match:
            return to_float(match.group(1))
    return None


def bracket_from_runner_number(number: int | None) -> int | None:
    if number is None or number <= 0:
        return None
    return min(max((number + 1) // 2, 1), 8)


def table_looks_like_race(frame: pd.DataFrame) -> bool:
    required_score = sum(
        1
        for key in ["runner_number", "horse_name"]
        if find_column(frame, key) is not None
    )
    useful_score = sum(
        1
        for key in ["finish_position", "market_odds", "jockey", "carried_weight", "sex_age"]
        if find_column(frame, key) is not None
    )
    return required_score == 2 and useful_score >= 1


def payout_type_from_cells(cells: list[str]) -> str | None:
    joined = " ".join(cells)
    normalized = normalize_digits(joined).replace("３連", "3連")
    if normalized in PAYOUT_COLUMNS_BY_TYPE:
        return normalized
    for bet_type, _column, aliases in PAYOUT_BET_TYPES:
        if any(alias in normalized for alias in aliases):
            return bet_type
    return None


def payout_yen_from_cells(cells: list[str]) -> int | None:
    for cell in cells:
        if "円" in cell or "," in cell:
            value = to_int(cell)
            if value is not None and value >= 10:
                return value
    for cell in cells:
        value = to_int(cell)
        if value is not None and value >= 100:
            return value
    return None


def split_cell_lines(value: Any) -> list[str]:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return [clean_text(line) for line in text.splitlines() if clean_text(line)]


def html_selection_lines(cell_html: str) -> list[str]:
    groups = re.findall(r"<ul\b[^>]*>(.*?)</ul>", cell_html, flags=re.IGNORECASE | re.DOTALL)
    if groups:
        selections: list[str] = []
        for group in groups:
            spans = [
                clean_text(re.sub(r"<[^>]+>", " ", html.unescape(match)))
                for match in re.findall(r"<span\b[^>]*>(.*?)</span>", group, flags=re.IGNORECASE | re.DOTALL)
            ]
            numbers = [item for item in spans if item]
            if numbers:
                selections.append(" - ".join(numbers))
        return selections

    spans = [
        clean_text(re.sub(r"<[^>]+>", " ", html.unescape(match)))
        for match in re.findall(r"<span\b[^>]*>(.*?)</span>", cell_html, flags=re.IGNORECASE | re.DOTALL)
    ]
    return [item for item in spans if item]


def html_cells_from_row(row_html: str) -> list[str]:
    cells: list[str] = []
    for match in re.finditer(r"<(?:th|td)\b([^>]*)>(.*?)</(?:th|td)>", row_html, flags=re.IGNORECASE | re.DOTALL):
        attrs = match.group(1)
        body = match.group(2)
        if re.search(r'class=["\'][^"\']*Result[^"\']*["\']', attrs, flags=re.IGNORECASE):
            lines = html_selection_lines(body)
        else:
            lines = split_cell_lines(body)
        cells.append("\n".join(lines) if lines else clean_text(body))
    return cells


def payout_rows_from_html(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for table_match in re.finditer(
        r"<table\b[^>]*class=[\"'][^\"']*(?:pay_table_01|Payout_Detail_Table)[^\"']*[\"'][^>]*>(.*?)</table>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        table_html = table_match.group(1)
        for row_match in re.finditer(r"<tr\b([^>]*)>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL):
            attrs = row_match.group(1)
            row_class_match = re.search(r'class=["\']([^"\']+)["\']', attrs, flags=re.IGNORECASE)
            row_class = row_class_match.group(1).split()[0] if row_class_match else ""
            cells = html_cells_from_row(row_match.group(2))
            if cells and row_class in PAYOUT_ROW_CLASS_TYPES:
                cells[0] = PAYOUT_ROW_CLASS_TYPES[row_class]
            if cells:
                rows.append(cells)
    return rows


def payout_item(bet_type: str, selection: str, payout_yen: int, popularity: int | None = None) -> dict[str, Any]:
    return {
        "bet_type": bet_type,
        "selection": selection,
        "payout_yen": payout_yen,
        "popularity": popularity,
    }


def selection_numbers_from_cells(cells: list[str]) -> list[int]:
    for cell in cells:
        normalized = normalize_digits(cell)
        if any(token in normalized for token in ["円", "人気", "払戻", "票数"]):
            continue
        if payout_type_from_cells([normalized]):
            continue
        numbers = [int(match) for match in re.findall(r"\d+", normalized)]
        if numbers:
            return numbers
    return []


def apply_payout_row(payouts: dict[str, Any], cells: list[str]) -> None:
    if len(cells) < 3:
        return
    bet_type = payout_type_from_cells([cells[0]])
    if not bet_type:
        return

    selections = split_cell_lines(cells[1]) or [cells[1]]
    payout_values = split_cell_lines(cells[2]) or [cells[2]]
    popularity_values = split_cell_lines(cells[3]) if len(cells) > 3 else []

    for index, selection in enumerate(selections):
        payout_yen = payout_yen_from_cells([payout_values[min(index, len(payout_values) - 1)]])
        if payout_yen is None:
            continue
        popularity = (
            to_int(popularity_values[min(index, len(popularity_values) - 1)])
            if popularity_values
            else None
        )
        numbers = selection_numbers_from_cells([selection])
        payouts["items"].append(payout_item(bet_type, selection, payout_yen, popularity))
        if bet_type == "win" and numbers:
            payouts["win_by_runner"][numbers[0]] = payout_yen
        elif bet_type == "place" and numbers:
            payouts["place_by_runner"][numbers[0]] = payout_yen
        else:
            column = PAYOUT_COLUMNS_BY_TYPE[bet_type]
            payouts["race"].setdefault(column, payout_yen)


def extract_payouts(source_tables: list[SourceTable]) -> dict[str, Any]:
    payouts: dict[str, Any] = {
        "win_by_runner": {},
        "place_by_runner": {},
        "race": {},
        "items": [],
    }

    seen_texts: set[int] = set()
    html_extracted = False
    for source in source_tables:
        if not source.text:
            continue
        text_id = id(source.text)
        if text_id in seen_texts:
            continue
        seen_texts.add(text_id)
        for cells in payout_rows_from_html(source.text):
            apply_payout_row(payouts, cells)
            html_extracted = True

    if html_extracted:
        return payouts

    for source in source_tables:
        if table_looks_like_race(source.frame):
            continue

        current_bet_type: str | None = None
        for _, row in source.frame.iterrows():
            cells = [clean_text(value) for value in row.tolist() if clean_text(value)]
            if not cells:
                continue

            detected_bet_type = payout_type_from_cells(cells)
            if detected_bet_type:
                current_bet_type = detected_bet_type
            bet_type = detected_bet_type or current_bet_type
            if not bet_type:
                continue

            payout_yen = payout_yen_from_cells(cells)
            if payout_yen is None:
                continue

            numbers = selection_numbers_from_cells(cells)
            if bet_type == "win" and numbers:
                payouts["win_by_runner"][numbers[0]] = payout_yen
                payouts["items"].append(payout_item(bet_type, str(numbers[0]), payout_yen))
            elif bet_type == "place" and numbers:
                payouts["place_by_runner"][numbers[0]] = payout_yen
                payouts["items"].append(payout_item(bet_type, str(numbers[0]), payout_yen))
            else:
                column = PAYOUT_COLUMNS_BY_TYPE[bet_type]
                payouts["race"].setdefault(column, payout_yen)
                if numbers:
                    payouts["items"].append(payout_item(bet_type, " - ".join(map(str, numbers)), payout_yen))

    return payouts


def apply_payouts(records: list[dict[str, Any]], payouts: dict[str, Any]) -> None:
    win_by_runner: dict[int, int] = payouts.get("win_by_runner", {})
    place_by_runner: dict[int, int] = payouts.get("place_by_runner", {})
    race_payouts: dict[str, int] = payouts.get("race", {})
    payout_items = payouts.get("items") if isinstance(payouts.get("items"), list) else []
    payouts_json = json.dumps(payout_items, ensure_ascii=False) if payout_items else ""

    for record in records:
        runner_number = record.get("runner_number")
        if runner_number in win_by_runner:
            record["payout_win"] = win_by_runner[runner_number]
        if runner_number in place_by_runner:
            record["payout_place"] = place_by_runner[runner_number]
        for column, value in race_payouts.items():
            record[column] = value
        if payouts_json:
            record["payouts_json"] = payouts_json


def normalize_table(
    source: SourceTable,
    path: Path,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    frame = source.frame
    if not table_looks_like_race(frame):
        return []

    race_date = infer_date(path, source.text, args.default_date)
    race_no = infer_race_no(path, source.text, args.default_race_no)
    race_id = ""
    frame_race_id_column = find_column(frame, "race_id")
    if frame_race_id_column and frame[frame_race_id_column].notna().any():
        race_id = clean_text(frame[frame_race_id_column].dropna().iloc[0])
    if not race_id:
        race_id = infer_race_id(path, source.text, source.index, race_date, race_no)

    venue = infer_venue(path, source.text, args.default_venue)
    surface, distance = infer_course(source.text, args.default_surface, args.default_distance)
    weather = infer_weather(source.text, args.default_weather)
    going = infer_going(source.text, args.default_going)
    start_time = infer_start_time(source.text)
    lap_3f = infer_lap_metric(source.text, "lap_3f")
    lap_4f = infer_lap_metric(source.text, "lap_4f")

    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        runner_number = to_int(first_value(row, frame, "runner_number"))
        horse_name = first_value(row, frame, "horse_name")
        if runner_number is None or not horse_name:
            continue

        sex = first_value(row, frame, "sex")
        age = to_int(first_value(row, frame, "age"))
        sex_age = first_value(row, frame, "sex_age")
        if sex_age and (not sex or age is None):
            parsed_sex, parsed_age = parse_sex_age(sex_age)
            sex = sex or parsed_sex
            age = age if age is not None else parsed_age

        raw_finish_position = first_value(row, frame, "finish_position")
        raw_market_odds = first_value(row, frame, "market_odds")
        raw_place_odds = first_value(row, frame, "place_odds")
        runner_status = parse_runner_status(
            first_value(row, frame, "runner_status"),
            raw_finish_position,
            raw_market_odds,
            raw_place_odds,
        )
        scratched = bool(runner_status)
        finish_position = None if scratched else parse_finish_position(raw_finish_position)
        market_odds = None if scratched else to_float(raw_market_odds)
        place_odds = None if scratched else to_float(raw_place_odds)
        if market_odds is not None and market_odds <= 1.0:
            market_odds = None
        if place_odds is not None and place_odds <= 1.0:
            place_odds = None
        raw_horse_weight = first_value(row, frame, "horse_weight")
        horse_weight, horse_weight_diff = parse_horse_weight(raw_horse_weight)
        explicit_diff = to_int(first_value(row, frame, "horse_weight_diff"))
        if explicit_diff is not None and abs(explicit_diff) <= 80:
            horse_weight_diff = explicit_diff
        if horse_weight is None:
            horse_weight_diff = None
        odds_rank = to_int(first_value(row, frame, "odds_rank"))

        predicted_odds_column = next(
            (
                str(column)
                for column in frame.columns
                if normalized_name(column) == normalized_name("予想オッズ")
            ),
            None,
        )
        if not scratched and finish_position is None and predicted_odds_column and market_odds is None:
            shifted_odds = to_float(raw_horse_weight)
            shifted_rank = to_int(row.get(predicted_odds_column))
            if shifted_odds is not None and shifted_odds > 1:
                market_odds = shifted_odds
                odds_rank = shifted_rank if shifted_rank is not None else odds_rank
                horse_weight = None
                horse_weight_diff = None

        record = {
            "race_id": race_id,
            "race_date": race_date,
            "race_no": race_no,
            "horse_number": runner_number,
            "runner_number": runner_number,
            "number": runner_number,
            "bracket": to_int(first_value(row, frame, "bracket"))
            or bracket_from_runner_number(runner_number),
            "gate": to_int(first_value(row, frame, "bracket"))
            or bracket_from_runner_number(runner_number),
            "horse_name": horse_name,
            "venue": venue,
            "distance": to_int(first_value(row, frame, "distance")) or distance,
            "going": first_value(row, frame, "going") or going,
            "surface": first_value(row, frame, "surface") or surface,
            "weather": first_value(row, frame, "weather") or weather,
            "start_time": first_value(row, frame, "start_time") or start_time,
            "post_time": first_value(row, frame, "start_time") or start_time,
            "body_weight_announced_at": first_value(row, frame, "body_weight_announced_at"),
            "odds_snapshot_at": first_value(row, frame, "odds_snapshot_at"),
            "sex": sex,
            "age": age,
            "jockey": first_value(row, frame, "jockey"),
            "trainer": first_value(row, frame, "trainer"),
            "running_style": first_value(row, frame, "running_style"),
            "sire": first_value(row, frame, "sire"),
            "sire_id": first_value(row, frame, "sire_id"),
            "dam_sire": first_value(row, frame, "dam_sire"),
            "dam_sire_id": first_value(row, frame, "dam_sire_id"),
            "carried_weight": to_float(first_value(row, frame, "carried_weight")),
            "horse_weight": horse_weight,
            "horse_weight_diff": horse_weight_diff,
            "field_size": None,
            "finish_position": finish_position,
            "runner_status": runner_status,
            "scratched": 1 if scratched else 0,
            "is_win": 1 if finish_position == 1 else 0 if finish_position is not None else None,
            "is_place": (
                1
                if finish_position is not None and finish_position <= 3
                else 0 if finish_position is not None else None
            ),
            "market_odds": market_odds,
            "place_odds": place_odds,
            "odds_rank": odds_rank,
            "odds_delta": to_float(first_value(row, frame, "odds_delta")),
            "odds_delta_5m": to_float(first_value(row, frame, "odds_delta_5m")),
            "odds_delta_15m": to_float(first_value(row, frame, "odds_delta_15m")),
            "odds_volatility": to_float(first_value(row, frame, "odds_volatility")),
            "ticket_pool_share": to_float(first_value(row, frame, "ticket_pool_share")),
            "training_score": to_float(first_value(row, frame, "training_score")),
            "bloodline_score": to_float(first_value(row, frame, "bloodline_score")),
            "paddock_score": to_float(first_value(row, frame, "paddock_score")),
            "last600m": to_float(first_value(row, frame, "last600m")) or lap_3f,
            "lap_3f": to_float(first_value(row, frame, "lap_3f")) or lap_3f,
            "lap_4f": to_float(first_value(row, frame, "lap_4f")) or lap_4f,
            "source_file": path.name,
            "source_table": source.index,
            "source_runner_id": f"{race_id}-{runner_number:02d}",
        }
        records.append(record)

    field_size = sum(1 for record in records if not record.get("scratched")) or len(records)
    for record in records:
        record["field_size"] = field_size
    return records


def read_records(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files: list[Path] = []
    for pattern in args.glob:
        files.extend(sorted(args.input_dir.glob(pattern)))
    files = sorted(dict.fromkeys(files))

    if args.limit_files:
        files = files[: args.limit_files]

    records: list[dict[str, Any]] = []
    file_summaries: list[dict[str, Any]] = []
    for path in files:
        source_tables = read_source_tables(path, args.encoding)
        payouts = extract_payouts(source_tables)
        before = len(records)
        for source in source_tables:
            table_records = normalize_table(source, path, args)
            apply_payouts(table_records, payouts)
            records.extend(table_records)
        parsed_rows = len(records) - before
        file_summaries.append(
            {
                "file": str(path),
                "tables": len(source_tables),
                "rows": parsed_rows,
                "payout_columns": sorted(payouts.get("race", {}).keys()),
            }
        )

    diagnostics = {
        "input_dir": str(args.input_dir),
        "files": len(files),
        "file_summaries": file_summaries,
    }
    return records, diagnostics


def normalize_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frame = frame.sort_values(["race_date", "race_id", "runner_number"], na_position="last")
    frame = frame.drop_duplicates(["race_id", "runner_number"], keep="last")
    for column in OUTPUT_COLUMNS:
        if column not in frame:
            frame[column] = None
    return frame[OUTPUT_COLUMNS]


def write_csv(frame: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)


def canonicalize_merge_runner_number(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    runner_number = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    if "runner_number" in frame:
        runner_number = pd.to_numeric(frame["runner_number"], errors="coerce")
    if "horse_number" in frame:
        runner_number = runner_number.fillna(pd.to_numeric(frame["horse_number"], errors="coerce"))
    if {"race_id", "number", "gate"}.issubset(frame.columns):
        number = pd.to_numeric(frame["number"], errors="coerce")
        gate = pd.to_numeric(frame["gate"], errors="coerce")
        number_unique = number.groupby(frame["race_id"].astype(str)).transform("nunique")
        gate_unique = gate.groupby(frame["race_id"].astype(str)).transform("nunique")
        use_gate_as_runner = (number_unique <= 2) & (gate_unique > number_unique)
        runner_number = runner_number.fillna(gate.where(use_gate_as_runner))
    if "number" in frame:
        runner_number = runner_number.fillna(pd.to_numeric(frame["number"], errors="coerce"))
    frame["runner_number"] = pd.to_numeric(runner_number, errors="coerce")
    if "horse_number" not in frame:
        frame["horse_number"] = frame["runner_number"]
    else:
        frame["horse_number"] = pd.to_numeric(frame["horse_number"], errors="coerce").fillna(
            frame["runner_number"]
        )
    return frame


def write_combined(base_csv: Path, imported: pd.DataFrame, combined_output: Path) -> dict[str, Any]:
    base = pd.read_csv(
        base_csv,
        low_memory=False,
        dtype={"race_id": "string", "race_date": "string"},
    )
    base = canonicalize_merge_runner_number(base)
    imported = canonicalize_merge_runner_number(imported)
    combined = pd.concat([base, imported], ignore_index=True, sort=False)
    if {"race_id", "runner_number"}.issubset(combined.columns):
        combined["runner_number"] = pd.to_numeric(combined["runner_number"], errors="coerce")
        combined = combined.drop_duplicates(["race_id", "runner_number"], keep="last")
    combined = combined.sort_values(["race_date", "race_id", "runner_number"], na_position="last")
    combined_output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(combined_output, index=False)
    return {
        "base_rows": int(len(base)),
        "combined_rows": int(len(combined)),
        "combined_races": int(combined["race_id"].nunique()) if "race_id" in combined else 0,
        "combined_output": str(combined_output),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import manually saved netkeiba race-card/result CSV or HTML files into UmaLab's "
            "normalized runner-level CSV schema."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw/netkeiba_2026"))
    parser.add_argument("--output", type=Path, default=Path("data/netkeiba_2026_normalized.csv"))
    parser.add_argument("--base-csv", type=Path, default=None)
    parser.add_argument("--combined-output", type=Path, default=None)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument(
        "--glob",
        action="append",
        default=["*.csv", "*.tsv", "*.html", "*.htm"],
        help="Input glob relative to --input-dir. Can be repeated.",
    )
    parser.add_argument("--limit-files", type=int, default=0)
    parser.add_argument("--default-date", default="")
    parser.add_argument("--default-race-no", type=int, default=None)
    parser.add_argument("--default-venue", default="")
    parser.add_argument("--default-surface", default="")
    parser.add_argument("--default-distance", type=int, default=None)
    parser.add_argument("--default-going", default="")
    parser.add_argument("--default-weather", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    records, diagnostics = read_records(args)
    frame = normalize_records(records)
    if frame.empty:
        raise SystemExit(
            "no race rows parsed. Save netkeiba race result/card tables as CSV or HTML under "
            f"{args.input_dir} and include at least 馬番 and 馬名 columns."
        )

    write_csv(frame, args.output)
    date_values = pd.to_datetime(frame["race_date"], errors="coerce")
    summary: dict[str, Any] = {
        **diagnostics,
        "rows": int(len(frame)),
        "races": int(frame["race_id"].nunique()),
        "min_date": date_values.min().date().isoformat() if date_values.notna().any() else None,
        "max_date": date_values.max().date().isoformat() if date_values.notna().any() else None,
        "rows_missing_result": int(frame["finish_position"].isna().sum()),
        "rows_missing_market_odds": int(frame["market_odds"].isna().sum()),
        "output": str(args.output),
    }

    if args.base_csv and args.combined_output:
        summary["combined"] = write_combined(args.base_csv, frame, args.combined_output)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
