"""
config.py — Shared constants for the Forex Factory Alert system.
Imported by tool scripts; never run directly.
"""

# Common trading timezone aliases → IANA names.
# Accepted as --timezone values in manage_users.py.
TIMEZONE_ALIASES: dict[str, str] = {
    "ET":   "America/New_York",
    "EST":  "America/New_York",
    "EDT":  "America/New_York",
    "CT":   "America/Chicago",
    "CST":  "America/Chicago",
    "CDT":  "America/Chicago",
    "MT":   "America/Denver",
    "MST":  "America/Denver",
    "MDT":  "America/Denver",
    "PT":   "America/Los_Angeles",
    "PST":  "America/Los_Angeles",
    "PDT":  "America/Los_Angeles",
    "GMT":  "UTC",
    "UTC":  "UTC",
    "BST":  "Europe/London",
    "WET":  "Europe/London",
    "CET":  "Europe/Paris",
    "CEST": "Europe/Paris",
    "EET":  "Europe/Helsinki",
    "IST":  "Asia/Kolkata",
    "SGT":  "Asia/Singapore",
    "JST":  "Asia/Tokyo",
    "HKT":  "Asia/Hong_Kong",
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "NZST": "Pacific/Auckland",
    "BRT":  "America/Sao_Paulo",
    "MSK":  "Europe/Moscow",
    "GST":  "Asia/Dubai",
    "PKT":  "Asia/Karachi",
}

# Maps FF event currency to the instruments most affected.
# Used by generate_event_analysis.py (to tell the AI which pairs to discuss)
# and render_email.py (to filter events per user).
CURRENCY_TO_INSTRUMENTS: dict[str, list[str]] = {
    "USD": [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
        "AUDUSD", "NZDUSD", "XAUUSD", "XAGUSD", "US30", "NAS100", "SPX500",
    ],
    "EUR": ["EURUSD", "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD"],
    "GBP": ["GBPUSD", "EURGBP", "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD"],
    "JPY": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY"],
    "CHF": ["USDCHF", "EURCHF", "GBPCHF", "CHFJPY"],
    "CAD": ["USDCAD", "EURCAD", "GBPCAD", "CADJPY", "AUDCAD", "NZDCAD"],
    "AUD": ["AUDUSD", "EURAUD", "GBPAUD", "AUDJPY", "AUDCAD", "AUDNZD"],
    "NZD": ["NZDUSD", "EURNZD", "GBPNZD", "NZDJPY", "AUDNZD", "NZDCAD"],
    "CNY": ["USDCNH", "AUDUSD"],
    "XAU": ["XAUUSD"],
    "XAG": ["XAGUSD"],
}

# Maps instrument name to the yfinance ticker symbol.
# GC=F (Gold Futures) is more reliable than XAUUSD=X on Yahoo Finance.
YFINANCE_TICKERS: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "USDCAD": "USDCAD=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "US30":   "YM=F",
    "NAS100": "NQ=F",
    "SPX500": "ES=F",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "AUDJPY": "AUDJPY=X",
    "CADJPY": "CADJPY=X",
    "CHFJPY": "CHFJPY=X",
    "NZDJPY": "NZDJPY=X",
    "USDCNH": "USDCNH=X",
}

# Full set of accepted instrument names for subscriber validation.
VALID_INSTRUMENTS: set[str] = set(YFINANCE_TICKERS.keys()) | {
    "USDMXN", "USDZAR", "EURCHF", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    "EURCAD", "EURAUD", "EURNZD", "AUDCAD", "AUDNZD", "NZDCAD", "NZDCHF",
    "AUDCHF", "GBPSGD", "EURSGD", "XAGUSD",
}

# Paths (relative to project root — scripts must be run from project root)
FF_ENDPOINT = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
JBLANKED_ENDPOINT = "https://api.jblanked.com/forex-factory/api/today/high-impact/"

PATHS = {
    "ff_raw":       ".tmp/ff_events_raw.json",
    "ff_today":     ".tmp/ff_events_today.json",
    "news_context": ".tmp/event_news_context.json",
    "analyses":     ".tmp/analyses.json",
    "charts_dir":   ".tmp/charts",
    "email":        ".tmp/email_{user_id}.html",
    "run_log":      ".tmp/run_log_{date}.json",
}
