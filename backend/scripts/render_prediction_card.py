from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def yen(value: Any) -> str:
    try:
        return f"JPY {float(value):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def metric(metrics: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = metrics
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def build_svg(metrics: dict[str, Any], backtest: dict[str, Any], title: str) -> str:
    rows = metric(metrics, "rows", default=0)
    races = metric(metrics, "races", default=0)
    trained_at = str(metric(metrics, "trained_at", default="not trained"))[:10]
    win_auc = metric(metrics, "targets", "is_win", "test", "auc")
    place_auc = metric(metrics, "targets", "is_place", "test", "auc")
    roi = backtest.get("roi")
    hit_rate = backtest.get("hit_rate")
    max_drawdown = backtest.get("max_drawdown")
    bets = backtest.get("bets", 0)

    safe_title = html.escape(title)
    safe_date = html.escape(trained_at)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="{safe_title} model output">
  <rect width="1200" height="630" fill="#f4f6f8"/>
  <rect x="50" y="46" width="1100" height="538" rx="18" fill="#ffffff" stroke="#d9dee5"/>
  <text x="86" y="112" fill="#1d6fd8" font-family="Arial, sans-serif" font-size="26" font-weight="700">UmaLab</text>
  <text x="86" y="166" fill="#101418" font-family="Arial, sans-serif" font-size="54" font-weight="800">{safe_title}</text>
  <text x="88" y="210" fill="#66707c" font-family="Arial, sans-serif" font-size="24">trained: {safe_date} / races: {races:,} / rows: {rows:,}</text>

  <rect x="86" y="265" width="238" height="118" rx="12" fill="#f9fafb" stroke="#d9dee5"/>
  <text x="112" y="310" fill="#66707c" font-family="Arial, sans-serif" font-size="22">Win AUC</text>
  <text x="112" y="356" fill="#101418" font-family="Arial, sans-serif" font-size="42" font-weight="800">{pct(win_auc, 2)}</text>

  <rect x="350" y="265" width="238" height="118" rx="12" fill="#f9fafb" stroke="#d9dee5"/>
  <text x="376" y="310" fill="#66707c" font-family="Arial, sans-serif" font-size="22">Place AUC</text>
  <text x="376" y="356" fill="#101418" font-family="Arial, sans-serif" font-size="42" font-weight="800">{pct(place_auc, 2)}</text>

  <rect x="614" y="265" width="238" height="118" rx="12" fill="#f9fafb" stroke="#d9dee5"/>
  <text x="640" y="310" fill="#66707c" font-family="Arial, sans-serif" font-size="22">Backtest ROI</text>
  <text x="640" y="356" fill="#0b8f68" font-family="Arial, sans-serif" font-size="42" font-weight="800">{pct(roi, 1)}</text>

  <rect x="878" y="265" width="238" height="118" rx="12" fill="#f9fafb" stroke="#d9dee5"/>
  <text x="904" y="310" fill="#66707c" font-family="Arial, sans-serif" font-size="22">Hit Rate</text>
  <text x="904" y="356" fill="#101418" font-family="Arial, sans-serif" font-size="42" font-weight="800">{pct(hit_rate, 1)}</text>

  <rect x="86" y="420" width="502" height="88" rx="12" fill="#edf5ff" stroke="#b8d4f5"/>
  <text x="112" y="456" fill="#66707c" font-family="Arial, sans-serif" font-size="22">Simulated bets</text>
  <text x="112" y="492" fill="#101418" font-family="Arial, sans-serif" font-size="30" font-weight="800">{int(bets):,}</text>

  <rect x="614" y="420" width="502" height="88" rx="12" fill="#fff5e5" stroke="#efd0a0"/>
  <text x="640" y="456" fill="#66707c" font-family="Arial, sans-serif" font-size="22">Max drawdown</text>
  <text x="640" y="492" fill="#b66a00" font-family="Arial, sans-serif" font-size="30" font-weight="800">{yen(max_drawdown)}</text>

  <text x="86" y="552" fill="#66707c" font-family="Arial, sans-serif" font-size="20">Generated from local metrics/backtest JSON. No model guarantees profit.</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render UmaLab model metrics/backtest summary as an SVG card.")
    parser.add_argument("--metrics", type=Path, default=Path("models/racequant/metrics.json"))
    parser.add_argument("--backtest", type=Path, default=Path("backtests/local-risk72.json"))
    parser.add_argument("--output", type=Path, default=Path("../public/model-output.svg"))
    parser.add_argument("--title", default="AI Model Output")
    args = parser.parse_args()

    svg = build_svg(read_json(args.metrics), read_json(args.backtest), args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
