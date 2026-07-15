"""
SPEEDHOME Price Intelligence -- Streamlit UI (Step 3)

Data flow:
  user picks an area (name search or URL) + a data source mode
    -> live: SpeedhomeScraper.fetch_area() -> scraper.parser.normalize_listings()
    -> cached: read data/cache/{slug}.csv directly
  -> Pandas DataFrame
    -> data.processor.build_price_summary()  (Price Summary Table)
    -> raw DataFrame                          (Unit Listings Table)
    -> utils.export                           (CSV / XLSX download)
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from scraper.config import KNOWN_AREAS, RENTAL_TYPES_AVAILABLE, BASE_URL
from scraper.speedhome_scraper import SpeedhomeScraper, RobotsDisallowedError
from scraper.parser import normalize_listings
from data.processor import build_price_summary, rental_type_availability_notice
from utils.export import build_filename, to_csv_bytes, to_xlsx_bytes

CACHE_DIR = Path(__file__).parent / "data" / "cache"

st.set_page_config(
    page_title="SPEEDHOME Price Intelligence",
    page_icon="🏠",
    layout="wide",
)

# Minimal CSS: ensure tables scroll horizontally instead of squashing on
# narrow/mobile viewports (Requirement 6).
st.markdown(
    """
    <style>
    div[data-testid="stDataFrame"] { overflow-x: auto; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- helpers --

def slug_from_url(url: str) -> str | None:
    """Extract an area slug from a pasted SPEEDHOME URL, e.g.
    'https://speedhome.com/rent/mont-kiara' -> 'mont-kiara'
    Also tolerates a trailing property-type segment, e.g. '/rent/mont-kiara/studio'.
    """
    match = re.search(r"speedhome\.com/rent/([^/?#]+)", url.strip())
    return match.group(1) if match else None


def display_name_for_slug(slug: str) -> str:
    for name, s in KNOWN_AREAS.items():
        if s == slug:
            return name
    # Fall back to a readable title-cased version of the slug
    return slug.replace("-", " ").title()


def load_cached(slug: str) -> pd.DataFrame | None:
    path = CACHE_DIR / f"{slug}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def _cached_area_list() -> list[str]:
    return sorted(KNOWN_AREAS.keys())


def run_live_scrape(slug: str, max_pages: int, use_impersonation: bool = False) -> tuple[pd.DataFrame | None, str | None]:
    """Returns (dataframe_or_None, error_message_or_None)."""
    scraper = SpeedhomeScraper(respect_robots=True, use_browser_impersonation=use_impersonation)
    try:
        try:
            result = scraper.fetch_area(slug, max_pages=max_pages)
        except RobotsDisallowedError as e:
            return None, f"Blocked by robots.txt policy: {e}"

        if not result.success:
            return None, result.error or "Live scrape returned no listings."

        records = normalize_listings(result.listings, area_query=slug)
        df = pd.DataFrame(records)
        if result.error:
            # partial success -- still return data, but surface the warning
            st.warning(f"Live scrape partially succeeded: {result.error}")
        return df, None
    finally:
        # Close immediately in this same thread rather than leaving cleanup
        # to Python's GC, which can run on a different Streamlit rerun
        # thread and crash curl_cffi's native handle (see speedhome_scraper.close).
        scraper.close()


# ------------------------------------------------------------------ UI ----

st.title("🏠 SPEEDHOME Price Intelligence")
st.caption(
    "Rental price data collected from SPEEDHOME.com's public listings, "
    "grouped and summarized by unit type."
)

with st.sidebar:
    st.header("Settings")
    data_mode = st.radio(
        "Data source",
        options=["Auto (live, fall back to cached)", "Live scrape only", "Cached data only"],
        index=0,
        help=(
            "Live scraping can be blocked by SPEEDHOME's anti-bot protection, "
            "especially from cloud servers (e.g. Streamlit Cloud). 'Auto' tries "
            "live first and falls back to a previously saved snapshot if it fails."
        ),
    )
    max_pages = st.slider(
        "Max pages to fetch (live mode)", min_value=1, max_value=10, value=2,
        help="Each page is ~40 listings. Kept low by default to be polite to SPEEDHOME's servers.",
    )
    use_impersonation = st.checkbox(
        "Try browser impersonation for live scraping (experimental)",
        value=False,
        help=(
            "Uses curl_cffi to mimic a real Chrome browser's TLS fingerprint, "
            "which sometimes bypasses Cloudflare where plain requests get "
            "blocked. WARNING: this has a known crash risk inside Streamlit "
            "specifically -- it can crash the app a short while AFTER it's "
            "used (a delayed native crash during cleanup), not necessarily "
            "immediately. Recommended: leave this OFF and rely on the "
            "cached-data fallback, which is fully stable."
        ),
    )
    st.divider()
    st.caption(
        "This app respects SPEEDHOME's robots.txt and adds delays between requests."
    )

search_method = st.radio(
    "Search by", options=["Area name", "SPEEDHOME URL"], horizontal=True
)

area_slug = None
area_name = None

if search_method == "Area name":
    choice = st.selectbox(
        "Type an area name (e.g. 'Mont' finds 'Mont Kiara')",
        options=[""] + _cached_area_list(),
        index=0,
        placeholder="Start typing an area...",
    )
    if choice:
        area_name = choice
        area_slug = KNOWN_AREAS[choice]
else:
    url_input = st.text_input(
        "Paste a SPEEDHOME area URL",
        placeholder="https://speedhome.com/rent/mont-kiara",
    )
    if url_input:
        parsed_slug = slug_from_url(url_input)
        if parsed_slug:
            area_slug = parsed_slug
            area_name = display_name_for_slug(parsed_slug)
        else:
            st.error(
                "Couldn't parse an area from that URL. Expected a format like "
                f"{BASE_URL}/rent/mont-kiara"
            )

search_clicked = st.button("Search", type="primary", disabled=area_slug is None)

if search_clicked and area_slug:
    df = None
    status_notes = []

    if data_mode in ("Auto (live, fall back to cached)", "Live scrape only"):
        with st.spinner(f"Fetching live listings for {area_name}..."):
            df, err = run_live_scrape(area_slug, max_pages=max_pages, use_impersonation=use_impersonation)
        if err:
            status_notes.append(f"Live scrape failed: {err}")

    if df is None and data_mode in ("Auto (live, fall back to cached)", "Cached data only"):
        cached_df = load_cached(area_slug)
        if cached_df is not None:
            df = cached_df
            status_notes.append("Loaded previously saved (cached) data instead of live data.")
        else:
            status_notes.append(
                f"No cached snapshot exists yet for '{area_name}' "
                f"(expected at data/cache/{area_slug}.csv)."
            )

    st.session_state["current_df"] = df
    st.session_state["current_area_name"] = area_name
    st.session_state["status_notes"] = status_notes

# ------------------------------------------------------------ results ----

df = st.session_state.get("current_df")
area_name_shown = st.session_state.get("current_area_name")
status_notes = st.session_state.get("status_notes", [])

for note in status_notes:
    if note.startswith("Live scrape failed"):
        st.warning(note)
    else:
        st.info(note)

if df is not None and not df.empty:
    st.success(f"Showing {len(df)} listings for **{area_name_shown}**.")

    # Requirement 4: rental type availability messaging
    for notice in rental_type_availability_notice(RENTAL_TYPES_AVAILABLE):
        st.info(notice)

    st.subheader("Price Summary by Unit Type")
    summary_df = build_price_summary(df)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    st.subheader("Unit Listings")
    listing_cols = [
        "Title", "Area/Property Name", "Bedroom Count", "Price/Month (RM)",
        "Price/Year (RM)", "Size (sqft)", "Furnishing Status", "URL",
    ]
    available_cols = [c for c in listing_cols if c in df.columns]
    st.dataframe(
        df[available_cols],
        width='stretch',
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("Listing", display_text="View listing"),
            "Price/Month (RM)": st.column_config.NumberColumn(format="RM %d"),
            "Price/Year (RM)": st.column_config.NumberColumn(format="RM %d"),
        },
    )

    st.subheader("Export")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download CSV",
            data=to_csv_bytes(df),
            file_name=build_filename(area_name_shown, "csv"),
            mime="text/csv",
            width='stretch',
        )
    with col2:
        st.download_button(
            "⬇️ Download Excel (.xlsx)",
            data=to_xlsx_bytes(df),
            file_name=build_filename(area_name_shown, "xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
        )

elif df is not None and df.empty:
    st.warning(f"No listings found for {area_name_shown}.")
else:
    st.info("Search for an area above to see price intelligence data.")
