#!/usr/bin/env python3
"""
generate_charts.py — WAT Framework Tool
Reads analyses.json, identifies all affected instruments, fetches OHLC data,
and renders a candlestick chart PNG per instrument via mplfinance.

Usage:
    python tools/generate_charts.py
    python tools/generate_charts.py --analyses .tmp/analyses.json --output-dir .tmp/charts

Exit codes:
    0 — success (even if some charts failed — those are skipped gracefully)
    1 — analyses file missing or unreadable
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — safe for scheduled runs

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS, YFINANCE_TICKERS

FETCH_TOOL = Path(__file__).parent / "fetch_chart_data.py"


def render_chart(instrument: str, ohlc_file: Path, output_dir: Path, event_times: list[str]) -> Path | None:
    """Render a candlestick PNG for one instrument. Returns output path or None on failure."""
    import pandas as pd
    import mplfinance as mpf
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    try:
        data = json.loads(ohlc_file.read_text(encoding="utf-8"))
        records = data.get("ohlc", [])
        if not records:
            print(f"[charts] No OHLC records for {instrument} — skipping", file=sys.stderr)
            return None

        df = pd.DataFrame(records)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
        df.index = df.index.tz_localize("UTC")
        df.columns = [c.capitalize() for c in df.columns]  # mplfinance expects capitalised cols

        output_path = output_dir / f"{instrument}_5day.png"

        # Build vertical lines for event release times
        vlines_args = {}
        if event_times:
            valid_times = []
            for t in event_times:
                try:
                    vt = pd.Timestamp(t, tz="UTC")
                    if df.index.min() <= vt <= df.index.max():
                        valid_times.append(vt)
                except Exception:
                    pass
            if valid_times:
                vlines_args = {
                    "vlines": valid_times,
                    "vline_width": 1.5,
                    "vline_colors": ["red"] * len(valid_times),
                    "vline_linestyle": "--",
                }

        # Style
        mc = mpf.make_marketcolors(
            up="#26a69a", down="#ef5350",
            edge="inherit", wick="inherit",
            volume={"up": "#26a69a", "down": "#ef5350"},
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle=":",
            gridcolor="#e0e0e0",
            facecolor="#fafafa",
            figcolor="#ffffff",
        )

        mpf.plot(
            df,
            type="candle",
            style=style,
            title=f"\n{instrument} — 5-Day 1H Chart",
            ylabel="Price",
            volume="Volume" in df.columns,
            figsize=(12, 6),
            savefig=dict(fname=str(output_path), dpi=150, bbox_inches="tight"),
            **vlines_args,
        )
        plt.close("all")
        print(f"[charts] {instrument} -> {output_path}", flush=True)
        return output_path

    except Exception as exc:
        print(f"[charts] WARNING: Failed to render {instrument}: {exc}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate candlestick charts for today's events.")
    parser.add_argument("--analyses", default=PATHS["analyses"], help="Analyses JSON path")
    parser.add_argument("--output-dir", default=PATHS["charts_dir"], help="Chart output directory")
    args = parser.parse_args()

    analyses_path = Path(args.analyses)
    if not analyses_path.exists():
        print(json.dumps({"error": f"Analyses file not found: {args.analyses}"}), file=sys.stderr)
        sys.exit(1)

    payload = json.loads(analyses_path.read_text(encoding="utf-8"))
    if payload.get("clear_day"):
        print("[charts] Clear day — no charts needed", flush=True)
        print(json.dumps({"status": "ok", "clear_day": True, "charts": []}))
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    from config import CURRENCY_TO_INSTRUMENTS

    # Collect all unique instruments and their event times.
    # Primary: use affected_instruments from AI analysis.
    # Fallback: derive from event's country (currency) via CURRENCY_TO_INSTRUMENTS.
    instrument_events: dict[str, list[str]] = {}
    for item in payload.get("analyses", []):
        analysis = item.get("analysis") or {}
        affected = analysis.get("affected_instruments") or []

        # Fallback: derive from currency if AI analysis unavailable
        if not affected:
            country = item.get("country", "").upper()
            affected = CURRENCY_TO_INSTRUMENTS.get(country, [])[:4]  # limit to top 4

        event_time = item.get("time_utc", "")
        for inst in affected:
            if inst in YFINANCE_TICKERS:
                instrument_events.setdefault(inst, [])
                if event_time:
                    date_str = payload.get("date", "")
                    if date_str and event_time:
                        try:
                            dt_str = f"{date_str} {event_time}"
                            instrument_events[inst].append(dt_str)
                        except Exception:
                            pass

    if not instrument_events:
        print("[charts] No chartable instruments found in analyses", flush=True)
        print(json.dumps({"status": "ok", "charts": []}))
        return

    print(f"[charts] Instruments to chart: {list(instrument_events.keys())}", flush=True)

    # Fetch OHLC for each instrument
    ohlc_files: dict[str, Path] = {}
    for instrument in instrument_events:
        result = subprocess.run(
            [sys.executable, str(FETCH_TOOL), "--instrument", instrument,
             "--output-dir", str(output_dir)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            ohlc_file = output_dir / f"{instrument}_ohlc.json"
            if ohlc_file.exists():
                ohlc_files[instrument] = ohlc_file
        else:
            print(f"[charts] WARNING: yfinance fetch failed for {instrument} — skipping chart",
                  file=sys.stderr)

    # Render charts
    chart_paths: list[str] = []
    for instrument, ohlc_file in ohlc_files.items():
        event_times = instrument_events.get(instrument, [])
        out = render_chart(instrument, ohlc_file, output_dir, event_times)
        if out:
            chart_paths.append(str(out))

    print(json.dumps({
        "status": "ok",
        "chart_count": len(chart_paths),
        "charts": chart_paths,
    }, indent=2))


if __name__ == "__main__":
    main()
