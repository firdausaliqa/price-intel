"""
Normalizes raw SPEEDHOME API listing records (as returned by
scraper.speedhome_scraper.SpeedhomeScraper) into the flat schema our
Streamlit app / Pandas layer expects.

Field mapping is based on a REAL sample record captured via manual DevTools
inspection on 2026-07-13 (see conversation notes). If SPEEDHOME changes
their API shape, this is the one place to update.
"""
from __future__ import annotations
from typing import Any

# --- known enum-ish value maps (extend as new values are observed) ---
FURNISH_MAP = {
    "NONE": "Unfurnished",
    "UNFURNISHED": "Unfurnished",
    "PARTIAL": "Partially Furnished",
    "FULL": "Fully Furnished",
    "FULLY": "Fully Furnished",
}

# CONFIRMED via DevTools (Referer header on the page's own prefetch request):
# individual listing pages live at /details/{slug}
LISTING_URL_TEMPLATE = "https://speedhome.com/details/{slug}"


def _unit_type_label(record: dict[str, Any]) -> str:
    """Derive the grouping label used in the Price Summary Table."""
    room_type = record.get("roomType")
    if room_type:
        return f"Room ({room_type.title()})"

    bedroom = record.get("bedroom")
    if bedroom is None:
        return "Unknown"
    if bedroom == 0:
        return "Studio"
    return f"{bedroom}BR"


def _furnishing_label(furnish_type: str | None) -> str:
    if not furnish_type:
        return "Not specified"
    return FURNISH_MAP.get(furnish_type.upper(), furnish_type.replace("_", " ").title())


def normalize_listing(record: dict[str, Any], area_query: str) -> dict[str, Any]:
    """
    Convert one raw API listing dict into our flat schema.
    Missing/None fields are handled explicitly rather than left to raise.
    """
    price_month = record.get("price")
    slug = record.get("slug", "")

    return {
        "Title": record.get("name") or "Untitled listing",
        "Area/Property Name": record.get("name") or area_query,
        "Address": record.get("address"),
        "City": record.get("city"),
        "State": record.get("state"),
        "Unit Type": _unit_type_label(record),
        "Bedroom Count": record.get("bedroom"),
        "Bathroom Count": record.get("bathroom"),
        "Price/Month (RM)": price_month,
        "Price/Year (RM)": (price_month * 12) if isinstance(price_month, (int, float)) else None,
        "Size (sqft)": record.get("sqft"),
        "Furnishing Status": _furnishing_label(record.get("furnishType")),
        "Property Type": record.get("type"),  # HIGHRISE / LANDED / ROOM etc.
        "No Deposit": record.get("noDeposit"),
        "Pet Friendly": record.get("petFriendly"),
        "Listing Ref": record.get("ref"),
        "URL": LISTING_URL_TEMPLATE.format(slug=slug) if slug else None,
        "_raw_id": record.get("id"),
    }


def normalize_listings(records: list[dict[str, Any]], area_query: str) -> list[dict[str, Any]]:
    return [normalize_listing(r, area_query) for r in records]
