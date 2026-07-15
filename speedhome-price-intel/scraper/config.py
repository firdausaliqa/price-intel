"""
Central config for the scraper. Nothing here hits the network -- it's just
constants so behavior (delays, headers, retry policy) is tuned in one place.
"""

BASE_URL = "https://speedhome.com"

USER_AGENT = "SpeedhomePriceIntelBot/1.0 (+educational-technical-test; contact: your-email@example.com)"

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Politeness settings -- overridden by robots.txt Crawl-delay if it's stricter
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 4.5
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2

# --- CONFIRMED via manual DevTools recon (2026-07-13) ---
# SPEEDHOME's Next.js frontend calls this JSON API directly. This is the
# primary data source -- no HTML parsing needed.
API_SEARCH_URL = f"{BASE_URL}/api/properties/search"
API_ITEMS_PER_PAGE = 40  # confirmed working page size from real browser request

# NOTE: SPEEDHOME's listing data (as of this recon) shows NO separate
# daily/monthly/yearly rental "types" -- `price` is a flat monthly RM rate,
# and `minRentalDuration` is a minimum lease length in months, not a
# distinct product. This matches Requirement 4's "if unavailable, display a
# clear message" case: SPEEDHOME appears to be a MONTHLY-ONLY platform.
# We still compute a derived Price/Year (price * 12) since that's simple
# arithmetic on the same monthly figure, not a separate scraped rental type.
RENTAL_TYPES_AVAILABLE = {
    "monthly": True,
    "daily": False,
    "yearly": False,  # not a native SPEEDHOME product; Price/Year is computed, not scraped
}

# Known area name -> URL slug mapping, used for the auto-suggest search box.
# Sourced from real area names referenced in SPEEDHOME's own site content
# (their area-guide FAQ sections), not guessed.
KNOWN_AREAS = {
    "Mont Kiara": "mont-kiara",
    "Bangsar": "bangsar",
    "KLCC": "klcc",
    "Bukit Bintang": "bukit-bintang",
    "Cheras": "cheras",
    "Petaling Jaya": "petaling-jaya",
    "Subang Jaya": "subang-jaya",
    "Puchong": "puchong",
    "Cyberjaya": "cyberjaya",
    "Shah Alam": "shah-alam",
    "Ara Damansara": "ara-damansara",
    "Bandar Utama": "bandar-utama",
    "Bukit Jalil": "bukit-jalil",
    "Gombak": "gombak",
    "Sentul": "sentul",
    "Wangsa Maju": "wangsa-maju",
    "Kota Damansara": "kota-damansara",
    "Damansara Perdana": "damansara-perdana",
    "Damansara Utama": "damansara-utama",
    "Kajang": "kajang",
    "Kelana Jaya": "kelana-jaya",
    "Kepong": "kepong",
    "Old Klang Road": "old-klang-road",
    "Klang": "klang",
    "Kuala Lumpur": "kuala-lumpur",
}
