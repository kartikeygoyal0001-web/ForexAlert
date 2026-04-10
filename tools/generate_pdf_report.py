#!/usr/bin/env python3
"""
generate_pdf_report.py — WAT Framework Tool
Composes a professional PDF morning report using ReportLab.
Includes: cover page, per-event analysis sections, embedded candlestick charts,
and a summary table at the end.

Usage:
    python tools/generate_pdf_report.py
    python tools/generate_pdf_report.py --analyses .tmp/analyses.json --output .tmp/report_2026-04-10.pdf

Exit codes:
    0 — success
    1 — input file missing
    2 — PDF generation error
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS, CURRENCY_TO_INSTRUMENTS

# --- Colour palette ---
NAVY   = (0.10, 0.13, 0.18)   # #1a2130
RED    = (0.93, 0.33, 0.20)   # #ed5433
GREEN  = (0.15, 0.65, 0.60)   # #26a69a
GOLD   = (0.85, 0.65, 0.13)   # #d9a621
LIGHT  = (0.97, 0.98, 0.99)   # #f7fafc
GRAY   = (0.58, 0.60, 0.63)   # #949aa1
BLACK  = (0.10, 0.10, 0.10)
WHITE  = (1.0, 1.0, 1.0)


def build_pdf(analyses_payload: dict, output_path: Path, charts_dir: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image, PageBreak, KeepTogether,
    )
    from reportlab.platypus import FrameBreak
    from reportlab.lib.colors import Color, HexColor

    W, H = A4
    margin = 2 * cm
    inner_w = W - 2 * margin

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
        title="Forex Morning Alert",
        author="Forex Factory Alert System",
    )

    styles = getSampleStyleSheet()

    def style(name, **kwargs) -> ParagraphStyle:
        s = ParagraphStyle(name, parent=styles["Normal"], **kwargs)
        return s

    S = {
        "cover_title": style("ct", fontSize=28, textColor=Color(*WHITE), alignment=TA_CENTER,
                             fontName="Helvetica-Bold", spaceAfter=6),
        "cover_sub":   style("cs", fontSize=13, textColor=Color(*GOLD), alignment=TA_CENTER,
                             fontName="Helvetica", spaceAfter=4),
        "cover_date":  style("cd", fontSize=11, textColor=Color(*LIGHT), alignment=TA_CENTER,
                             fontName="Helvetica"),
        "h1":          style("h1", fontSize=15, textColor=Color(*NAVY), fontName="Helvetica-Bold",
                             spaceBefore=10, spaceAfter=4),
        "h2":          style("h2", fontSize=11, textColor=Color(*NAVY), fontName="Helvetica-Bold",
                             spaceBefore=6, spaceAfter=2),
        "body":        style("body", fontSize=10, textColor=Color(*BLACK), leading=14, spaceAfter=4),
        "label":       style("label", fontSize=9, textColor=Color(*GRAY), fontName="Helvetica-Bold",
                             spaceAfter=1),
        "small":       style("small", fontSize=9, textColor=Color(*GRAY), fontName="Helvetica-Oblique",
                             leading=12),
        "green_box":   style("gb", fontSize=10, textColor=Color(*BLACK), leading=14, spaceAfter=2,
                             borderPadding=6, borderColor=Color(*GREEN), borderWidth=1,
                             backColor=Color(0.93, 0.99, 0.97)),
        "red_box":     style("rb", fontSize=10, textColor=Color(*BLACK), leading=14, spaceAfter=2,
                             borderPadding=6, borderColor=Color(*RED), borderWidth=1,
                             backColor=Color(0.99, 0.94, 0.93)),
    }

    def color_rl(rgb) -> Color:
        return Color(*rgb)

    story = []
    date_str = analyses_payload.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    analyses = analyses_payload.get("analyses", [])
    event_count = len(analyses)

    # ─── COVER PAGE ───────────────────────────────────────────────────────────
    cover_bg = Table(
        [[Paragraph("FOREX MORNING ALERT", S["cover_title"])],
         [Paragraph(f"{event_count} High-Impact Event{'s' if event_count != 1 else ''} Today", S["cover_sub"])],
         [Paragraph(date_display, S["cover_date"])],
         [Spacer(1, 0.5 * cm)],
         [Paragraph("Generated at 06:30 UTC · Powered by OpenAI gpt-4o · Data: Forex Factory", S["small"])],
         ],
        colWidths=[inner_w],
    )
    cover_bg.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color_rl(NAVY)),
        ("TOPPADDING",    (0, 0), (-1, -1), 30),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [8, 8, 8, 8]),
    ]))
    story.append(cover_bg)
    story.append(Spacer(1, 1 * cm))

    # Summary table on cover
    if analyses:
        summary_data = [["Time (UTC)", "Currency", "Event", "Forecast", "Previous"]]
        for item in analyses:
            summary_data.append([
                item.get("time_utc") or item.get("time", "—"),
                item.get("country", "—"),
                item.get("title", "—"),
                item.get("forecast") or "—",
                item.get("previous") or "—",
            ])
        summary_table = Table(summary_data, colWidths=[2.5 * cm, 2 * cm, 6 * cm, 2.5 * cm, 2.5 * cm])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),  color_rl(NAVY)),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  color_rl(WHITE)),
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [color_rl(LIGHT), color_rl(WHITE)]),
            ("GRID",        (0, 0), (-1, -1), 0.5, color_rl(GRAY)),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph("Today's Red-Folder Events at a Glance", S["h1"]))
        story.append(summary_table)

    story.append(PageBreak())

    # ─── EVENT SECTIONS ───────────────────────────────────────────────────────
    for item in analyses:
        analysis = item.get("analysis") or {}
        title     = analysis.get("event_name") or item.get("title", "Unknown Event")
        currency  = item.get("country", "")
        time_utc  = item.get("time_utc") or item.get("time", "TBD")
        forecast  = item.get("forecast") or "N/A"
        previous  = item.get("previous") or "N/A"
        actual    = item.get("actual") or "Not yet released"
        # Use AI-provided list or fall back to currency mapping
        affected  = analysis.get("affected_instruments") or CURRENCY_TO_INSTRUMENTS.get(currency.upper(), [])[:4]

        section = []

        # Event header
        header = Table(
            [[Paragraph(f"🔴 {title}", S["h1"]),
              Paragraph(f"{time_utc} UTC · {currency}", S["label"])]],
            colWidths=[inner_w * 0.75, inner_w * 0.25],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",  (1, 0), (1, 0),  "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, color_rl(RED)),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        section.append(header)
        section.append(Spacer(1, 0.3 * cm))

        # Numbers row
        numbers = Table(
            [["PREVIOUS", "FORECAST", "ACTUAL"],
             [previous, forecast, actual]],
            colWidths=[inner_w / 3] * 3,
        )
        numbers.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  color_rl(LIGHT)),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("FONTNAME",      (0, 1), (-1, 1),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 1), (-1, 1),  13),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("GRID",          (0, 0), (-1, -1), 0.5, color_rl(GRAY)),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        section.append(numbers)
        section.append(Spacer(1, 0.3 * cm))

        # Affected instruments chips
        if affected:
            section.append(Paragraph("INSTRUMENTS AFFECTED", S["label"]))
            section.append(Paragraph("  ·  ".join(affected), S["body"]))
            section.append(Spacer(1, 0.2 * cm))

        # Analysis text blocks
        if analysis.get("plain_explanation"):
            section.append(Paragraph("WHAT IS THIS?", S["label"]))
            section.append(Paragraph(analysis["plain_explanation"], S["body"]))

        if analysis.get("historical_context"):
            section.append(Paragraph("HISTORICAL CONTEXT", S["label"]))
            section.append(Paragraph(analysis["historical_context"], S["body"]))

        if analysis.get("forecast_vs_previous"):
            section.append(Paragraph("FORECAST VS PREVIOUS", S["label"]))
            section.append(Paragraph(analysis["forecast_vs_previous"], S["body"]))

        # Scenario boxes
        if analysis.get("bullish_scenario"):
            section.append(Paragraph("BEAT SCENARIO (Bullish for currency)", S["label"]))
            beat_table = Table(
                [[Paragraph(f"▲  {analysis['bullish_scenario']}", S["green_box"])]],
                colWidths=[inner_w],
            )
            beat_table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), Color(0.93, 0.99, 0.97)),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEAFTER",     (0, 0), (0, -1), 4, color_rl(GREEN)),
            ]))
            section.append(beat_table)
            section.append(Spacer(1, 0.15 * cm))

        if analysis.get("bearish_scenario"):
            section.append(Paragraph("MISS SCENARIO (Bearish for currency)", S["label"]))
            miss_table = Table(
                [[Paragraph(f"▼  {analysis['bearish_scenario']}", S["red_box"])]],
                colWidths=[inner_w],
            )
            miss_table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), Color(0.99, 0.94, 0.93)),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEAFTER",     (0, 0), (0, -1), 4, color_rl(RED)),
            ]))
            section.append(miss_table)
            section.append(Spacer(1, 0.15 * cm))

        if analysis.get("trading_note"):
            section.append(Paragraph("TRADING NOTE", S["label"]))
            section.append(Paragraph(f"💡 {analysis['trading_note']}", S["small"]))

        section.append(Spacer(1, 0.4 * cm))

        # Embed charts for affected instruments
        for inst in affected:
            chart_path = charts_dir / f"{inst}_5day.png"
            if chart_path.exists():
                try:
                    img = Image(str(chart_path), width=inner_w, height=inner_w * 0.5)
                    section.append(Paragraph(f"{inst} — 5-Day 1H Chart", S["label"]))
                    section.append(img)
                    section.append(Spacer(1, 0.3 * cm))
                except Exception as exc:
                    section.append(Paragraph(f"[Chart unavailable for {inst}: {exc}]", S["small"]))

        section.append(HRFlowable(width=inner_w, thickness=0.5, color=color_rl(GRAY)))
        section.append(Spacer(1, 0.5 * cm))

        story.append(KeepTogether(section[:6]))  # keep header + numbers together
        story.extend(section[6:])

    # ─── FOOTER PAGE ──────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("About This Report", S["h1"]))
    story.append(Paragraph(
        "This report is generated automatically each weekday at 06:30 UTC. "
        "Event data is sourced from Forex Factory. Analysis is generated by OpenAI gpt-4o. "
        "Charts use 5-day 1-hour OHLC data from Yahoo Finance (via yfinance). "
        "Red dashed vertical lines on charts indicate the scheduled event release time.",
        S["body"],
    ))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "This report is for informational purposes only and does not constitute financial advice. "
        "All trading involves risk. Past performance is not indicative of future results.",
        S["small"],
    ))

    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PDF morning report from analyses.")
    parser.add_argument("--analyses", default=PATHS["analyses"], help="Analyses JSON path")
    parser.add_argument("--charts-dir", default=PATHS["charts_dir"], help="Charts PNG directory")
    parser.add_argument("--output", default=None, help="Output PDF path (default: auto from date)")
    args = parser.parse_args()

    analyses_path = Path(args.analyses)
    if not analyses_path.exists():
        print(json.dumps({"error": f"Analyses file not found: {args.analyses}"}), file=sys.stderr)
        sys.exit(1)

    payload = json.loads(analyses_path.read_text(encoding="utf-8"))

    date_str = payload.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    output_path = Path(args.output) if args.output else Path(PATHS["pdf"].format(date=date_str))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    charts_dir = Path(args.charts_dir)

    print(f"[pdf] Generating report for {date_str} -> {output_path}", flush=True)

    try:
        build_pdf(payload, output_path, charts_dir)
    except Exception as exc:
        print(json.dumps({"error": f"PDF generation failed: {exc}"}), file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    size_kb = output_path.stat().st_size // 1024
    print(f"[pdf] Done — {size_kb} KB", flush=True)
    print(json.dumps({
        "status": "ok",
        "output": str(output_path),
        "size_kb": size_kb,
        "date": date_str,
    }, indent=2))


if __name__ == "__main__":
    main()
