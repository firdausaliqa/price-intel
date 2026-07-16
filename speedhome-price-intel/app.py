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

# --- Fintech-style visual theme (matched to reference image) ---
# Palette: white background, near-black cards/buttons, neon lime-green
# accent, warm cream secondary cards. Buttons are fully pill-shaped;
# cards use large (20-24px) rounded corners. Every text color below is
# set explicitly (never inherited) to avoid any dark-on-dark or
# light-on-light contrast clashes.
st.markdown(
    """
    <style>
    :root {
        --black: #141414;
        --neon: #D4F832;
        --cream: #F3F1EA;
        --cream-light: #F7F6F1;
        --gray-text: #6B6B68;
        --radius-card: 22px;
        --radius-pill: 999px;
    }

    .stApp { background-color: #FFFFFF; }

    /* Force every default text element to an explicit, safe color --
       eliminates any inherited-color contrast issues regardless of cause */
    .stApp, .stApp p, .stApp span,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    .stMarkdown, .stCaption {
        color: var(--black) !important;
    }
    .stApp h1, .stApp h2, .stApp h3 { font-weight: 800 !important; }

    /* Sidebar: cream background, explicit dark text */
    section[data-testid="stSidebar"] {
        background-color: var(--cream);
        border-right: 1px solid var(--black);
    }
    section[data-testid="stSidebar"] * { color: var(--black) !important; }

    /* Alert boxes (st.info/warning/success): force light bg + dark text
       explicitly rather than trusting theme-derived defaults */
    div[data-testid="stAlert"] {
        background-color: var(--cream-light) !important;
        border: 1px solid var(--black) !important;
        border-radius: var(--radius-card) !important;
    }
    div[data-testid="stAlert"] p { color: var(--black) !important; }

    /* Tables: rounded card container */
    div[data-testid="stDataFrame"] {
        overflow-x: auto;
        border: 1px solid var(--black);
        border-radius: var(--radius-card);
        padding: 4px;
        background-color: #FFFFFF;
    }
    /* The interactive grid inside st.dataframe is canvas-rendered, so it
       reads its colors from these custom properties rather than normal
       CSS inheritance -- force them to the light palette explicitly. */
    div[data-testid="stDataFrame"] {
        --gdg-bg-cell: #FFFFFF;
        --gdg-bg-cell-medium: var(--cream-light);
        --gdg-bg-header: var(--cream);
        --gdg-bg-header-has-focus: var(--cream);
        --gdg-bg-bubble: var(--cream-light);
        --gdg-text-dark: var(--black);
        --gdg-text-light: var(--gray-text);
        --gdg-text-header: var(--black);
        --gdg-border-color: #E0DDD3;
        --gdg-accent-color: var(--neon);
        --gdg-accent-fg: var(--black);
        --gdg-accent-light: var(--cream-light);
    }

    /* Inputs: crisp border, rounded, explicit dark text on white.
       Placeholder text and the small "Press Enter to apply" instructions
       Streamlit shows below an unsubmitted input both need their own
       explicit color -- they don't inherit from the input's own color. */
    div[data-testid="stTextInput"] input,
    div[data-baseweb="select"] > div {
        border: 1px solid var(--black) !important;
        border-radius: var(--radius-card) !important;
        background-color: #FFFFFF !important;
        color: var(--black) !important;
        padding: 6px 8px !important;
    }
    div[data-testid="stTextInput"] input::placeholder {
        color: #8A8A85 !important;
        opacity: 1 !important;
    }
    div[data-testid="stTextInput"] div[data-testid="InputInstructions"],
    div[data-testid="stTextInput"] small {
        color: #8A8A85 !important;
    }

    /* Buttons: fully pill-shaped, per the reference.
       Primary (Search) = neon fill + black text (the reference reserves
       neon for its single top CTA, "Get App"/"Subscribe").
       Secondary (Download) = black fill + white text ("Read FAQ" style).
       Streamlit often wraps button labels in an inner <p> or <div> --
       the broad ".stApp p" rule above would otherwise force that inner
       text back to black regardless of the button's own color, so we
       explicitly make button-internal text inherit from the button. */
    button[kind="primary"] {
        background-color: var(--neon) !important;
        color: var(--black) !important;
        border: 1px solid var(--black) !important;
        border-radius: var(--radius-pill) !important;
        font-weight: 700 !important;
        padding: 0.6rem 1.6rem !important;
    }
    button[kind="primary"]:hover {
        background-color: #c2e82a !important;
        color: var(--black) !important;
    }
    button[kind="primary"] p, button[kind="primary"] div, button[kind="primary"] span {
        color: inherit !important;
    }

    button[kind="secondary"], .stDownloadButton button {
        background-color: var(--black) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--black) !important;
        border-radius: var(--radius-pill) !important;
        font-weight: 700 !important;
        padding: 0.6rem 1.6rem !important;
    }
    .stDownloadButton button:hover {
        background-color: #000000 !important;
        color: var(--neon) !important;
    }
    button[kind="secondary"] p, button[kind="secondary"] div, button[kind="secondary"] span,
    .stDownloadButton button p, .stDownloadButton button div, .stDownloadButton button span {
        color: inherit !important;
    }

    /* KPI summary cards -- two alternating variants, echoing the
       black/cream/black rhythm of the reference's stat-card row.
       Each variant pins ALL its own text colors, so alternating never
       risks a mismatched pairing. */
    .kpi-card {
        border-radius: var(--radius-card);
        padding: 22px 24px;
        margin-bottom: 16px;
        height: 100%;
    }
    .kpi-card--light {
        background-color: var(--cream-light);
        border: 1px solid var(--black);
    }
    .kpi-card--dark {
        background-color: var(--black);
        border: 1px solid var(--black);
    }

    .kpi-card--light .kpi-title {
        background-color: var(--black);
        color: var(--neon) !important;
    }
    .kpi-card--dark .kpi-title {
        background-color: var(--neon);
        color: var(--black) !important;
    }
    .kpi-card .kpi-title {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        border-radius: var(--radius-pill);
        padding: 4px 14px;
        margin-bottom: 14px;
    }

    .kpi-card--light .kpi-fair-price { color: var(--black) !important; }
    .kpi-card--dark .kpi-fair-price { color: #FFFFFF !important; }
    .kpi-card .kpi-fair-price {
        font-size: 1.9rem;
        font-weight: 800;
        line-height: 1.1;
        margin-bottom: 2px;
    }

    .kpi-card--light .kpi-fair-label { color: var(--gray-text) !important; }
    .kpi-card--dark .kpi-fair-label { color: #B8B8B0 !important; }
    .kpi-card .kpi-fair-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 14px;
    }

    .kpi-card--light .kpi-stats-grid { border-top: 1px solid #ddd9cf; }
    .kpi-card--dark .kpi-stats-grid { border-top: 1px solid #3a3a3a; }
    .kpi-card .kpi-stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px 16px;
        padding-top: 12px;
    }

    .kpi-card--light .kpi-stat-label { color: var(--gray-text) !important; }
    .kpi-card--dark .kpi-stat-label { color: #B8B8B0 !important; }
    .kpi-card .kpi-stat-label { font-size: 0.72rem; }

    .kpi-card--light .kpi-stat-value { color: var(--black) !important; }
    .kpi-card--dark .kpi-stat-value { color: #FFFFFF !important; }
    .kpi-card .kpi-stat-value { font-size: 0.95rem; font-weight: 700; }
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


def render_summary_cards(summary_df: pd.DataFrame, cols_per_row: int = 3) -> None:
    """
    Renders the Price Summary DataFrame as a grid of high-contrast KPI
    cards (one per Unit Type) instead of a plain table -- Fair Price is
    the visual focal point of each card, with the other stats (Count,
    Average, Median, Mode, Avg Size) as a secondary stat grid underneath.
    """
    def _fmt_rm(value) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"RM {value:,.0f}"

    def _fmt_sqft(value) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{value:,.0f} sqft"

    rows = summary_df.to_dict("records")
    for i in range(0, len(rows), cols_per_row):
        row_chunk = rows[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, (col, stat) in enumerate(zip(cols, row_chunk)):
            variant = "kpi-card--dark" if (i + j) % 2 == 1 else "kpi-card--light"
            with col:
                st.markdown(
                    f"""
                    <div class="kpi-card {variant}">
                        <span class="kpi-title">{stat['Unit Type']}</span>
                        <div class="kpi-fair-price">{_fmt_rm(stat['Fair Price (RM)'])}</div>
                        <div class="kpi-fair-label">Fair Price · {stat['Count']} listing{'s' if stat['Count'] != 1 else ''}</div>
                        <div class="kpi-stats-grid">
                            <div class="kpi-stat-label">Average</div>
                            <div class="kpi-stat-value">{_fmt_rm(stat['Average Price (RM)'])}</div>
                            <div class="kpi-stat-label">Median</div>
                            <div class="kpi-stat-value">{_fmt_rm(stat['Median Price (RM)'])}</div>
                            <div class="kpi-stat-label">Mode</div>
                            <div class="kpi-stat-value">{_fmt_rm(stat['Mode Price (RM)'])}</div>
                            <div class="kpi-stat-label">Avg Size</div>
                            <div class="kpi-stat-value">{_fmt_sqft(stat['Average Size (sqft)'])}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


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
            status_notes.append(("warning", f"Live scrape failed: {err}"))

    if df is None and data_mode in ("Auto (live, fall back to cached)", "Cached data only"):
        cached_df = load_cached(area_slug)
        if cached_df is not None:
            df = cached_df
            status_notes.append(("info", "Loaded previously saved (cached) data instead of live data."))
        else:
            status_notes.append((
                "error",
                f"No data available for **{area_name}**: live scraping "
                f"{'failed' if data_mode != 'Cached data only' else 'was skipped (Cached data only mode)'}, "
                f"and no cached snapshot exists yet for this area "
                f"(expected at `data/cache/{area_slug}.csv`). Try a different "
                f"area name, or Mont Kiara, which has a saved snapshot."
            ))

    st.session_state["current_df"] = df
    st.session_state["current_area_name"] = area_name
    st.session_state["status_notes"] = status_notes

# ------------------------------------------------------------ results ----

df = st.session_state.get("current_df")
area_name_shown = st.session_state.get("current_area_name")
status_notes = st.session_state.get("status_notes", [])

for level, note in status_notes:
    if level == "error":
        st.error(note)
    elif level == "warning":
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
    render_summary_cards(summary_df)

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
