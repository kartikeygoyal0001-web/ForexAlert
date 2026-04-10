#!/usr/bin/env python3
"""
fetch_chart_data.py — WAT Framework Tool
Pulls 5-day 1-hour OHLC data for a given instrument via yfinance.
Writes to .tmp/charts/<INSTRUMENT>_ohlc.json for use by generate_charts.py.

Usage:
    python tools/fetch_chart_data.py --instrument EURUSD
    python tools/fetch_chart_data.py --instrument XAUUSD --output-dir .tmp/charts

Exit codes:
    0 — success
    1 — unknown instrument or argument error
    2 — yfinance fetch failed (non-fatal in pipeline — caller should log and skip)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import YFINANCE_TICKERS, PATHS


def fetch_ohlc(ticker: str, instrument: str) -> list[dict]:
    import yfinance as yf

    tf = yf.Ticker(ticker)
    df = tf.history(period="5d", interval="1h", auto_adjust=True)

    if df is None or df.empty:
        raise ValueError(f"No data returned for ticker {ticker}")

    # Convert to JSON-serialisable list of dicts
    records = []
    for ts, row in df.iterrows():
        records.append({
            "datetime": ts.strftime("%Y-%m-%d %H:%M"),
            "open":  round(float(row["Open"]),  5),
            "high":  round(float(row["High"]),  5),
            "low":   round(float(row["Low"]),   5),
            "close": round(float(row["Close"]), 5),
            "volume": int(row.get("Volume", 0) or 0),
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch 5-day 1H OHLC for a forex instrument.")
    parser.add_argument("--instrument", required=True, help="Instrument name, e.g. EURUSD")
    parser.add_argument("--output-dir", default=PATHS["charts_dir"], help="Directory for output JSON")
    args = parser.parse_args()

    instrument = args.instrument.upper()
    ticker = YFINANCE_TICKERS.get(instrument)
    if not ticker:
        print(json.dumps({
            "error": f"Unknown instrument: {instrument}",
            "known": list(YFINANCE_TICKERS.keys()),
        }), file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{instrument}_ohlc.json"

    print(f"[chart-data] Fetching {instrument} ({ticker}) — 5d 1h...", flush=True)

    try:
        records = fetch_ohlc(ticker, instrument)
    except Exception as exc:
        print(json.dumps({
            "error": f"yfinance failed for {instrument}: {exc}",
            "instrument": instrument,
            "ticker": ticker,
        }), file=sys.stderr)
        sys.exit(2)

    output_file.write_text(
        json.dumps({"instrument": instrument, "ticker": ticker, "ohlc": records}, indent=2),
        encoding="utf-8",
    )

    print(f"[chart-data] {instrument}: {len(records)} candles -> {output_file}", flush=True)
    print(json.dumps({
        "status": "ok",
        "instrument": instrument,
        "ticker": ticker,
        "candle_count": len(records),
        "output": str(output_file),
    }, indent=2))


if __name__ == "__main__":
    main()
