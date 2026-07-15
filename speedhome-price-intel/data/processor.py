"""
Pandas layer: turns a raw listings DataFrame (as produced by
scraper.parser.normalize_listings) into the Price Summary Table required
by the spec: Count, Average Price, Median Price, Mode Price, Fair Price,
Average Size -- grouped by Unit Type.
"""
from __future__ import annotations
import pandas as pd
import numpy as np

# Disable pandas' PyArrow-backed string storage. Recent pandas versions
# (3.x) default to Arrow-backed strings, and groupby() on such columns
# routes through PyArrow's native compute kernels (dictionary_encode /
# factorize). On some Python/PyArrow version combinations (observed on
# Python 3.14 on macOS) this segfaults -- a hard native crash, not a
# catchable Python exception. We don't need Arrow-backed strings anywhere
# in this app, so we force plain object-dtype strings globally to avoid
# that code path entirely.
try:
    pd.set_option("future.infer_string", False)
except Exception:
    pass  # older pandas versions don't have this option; nothing to do


PRICE_COL = "Price/Month (RM)"
SIZE_COL = "Size (sqft)"
UNIT_TYPE_COL = "Unit Type"


def _mode_price(series: pd.Series) -> float | None:
    """
    Mode of a small numeric sample is often not unique (ties), or -- with
    small samples -- every value may be unique (no repeats at all). We take
    the first modal value in that case, which pandas' own .mode() already
    sorts ascending, so this is deterministic run-to-run.
    """
    clean = series.dropna()
    if clean.empty:
        return None
    modes = clean.mode()
    if modes.empty:
        return None
    return float(modes.iloc[0])


def _fair_price(series: pd.Series) -> float | None:
    """
    'Fair Price' = interquartile mean (the average of values strictly
    within the 25th-75th percentile band). This is a well-established
    robust central-tendency estimator: it discounts outlier listings
    (e.g. penthouses or heavily discounted units) more than a plain mean,
    while using more of the data than the median alone.

    Falls back to the median when the sample is too small (<4) for
    quartiles to be meaningful.
    """
    clean = series.dropna()
    if clean.empty:
        return None
    if len(clean) < 4:
        return float(clean.median())

    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    within_iqr = clean[(clean >= q1) & (clean <= q3)]
    if within_iqr.empty:  # extremely unlikely, but guard anyway
        return float(clean.median())
    return float(within_iqr.mean())


def build_price_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns the Price Summary Table required by Requirement 2:
    grouped by Unit Type -> Count, Average Price, Median Price, Mode Price,
    Fair Price, Average Size (sqft).
    """
    if df.empty:
        return pd.DataFrame(
            columns=["Unit Type", "Count", "Average Price (RM)", "Median Price (RM)",
                     "Mode Price (RM)", "Fair Price (RM)", "Average Size (sqft)"]
        )

    rows = []
    # Defensive cast: force plain object-dtype strings for the groupby key,
    # regardless of what dtype the incoming DataFrame happens to use. This
    # guarantees pandas' groupby uses the plain Python/NumPy hash-table path
    # rather than PyArrow's compute kernels, which is the actual segfault
    # trigger we've seen on some Python/PyArrow version combinations.
    df = df.copy()
    df[UNIT_TYPE_COL] = df[UNIT_TYPE_COL].astype(object)

    for unit_type, group in df.groupby(UNIT_TYPE_COL):
        prices = group[PRICE_COL]
        sizes = group[SIZE_COL]
        rows.append({
            "Unit Type": unit_type,
            "Count": int(group.shape[0]),
            "Average Price (RM)": round(prices.mean(), 0) if prices.notna().any() else None,
            "Median Price (RM)": round(prices.median(), 0) if prices.notna().any() else None,
            "Mode Price (RM)": _mode_price(prices),
            "Fair Price (RM)": round(_fair_price(prices), 0) if prices.notna().any() else None,
            "Average Size (sqft)": round(sizes.mean(), 0) if sizes.notna().any() else None,
        })

    summary = pd.DataFrame(rows)

    # Sort in a sensible reading order: Studio, 1BR..N BR, then Room variants, then Unknown
    def _sort_key(unit_type: str):
        if unit_type == "Studio":
            return (0, 0)
        if unit_type.endswith("BR"):
            try:
                return (1, int(unit_type.replace("BR", "")))
            except ValueError:
                return (1, 999)
        if unit_type.startswith("Room"):
            return (2, unit_type)
        return (3, unit_type)

    summary["_sort"] = summary["Unit Type"].map(_sort_key)
    summary = summary.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    return summary


def rental_type_availability_notice(rental_types_available: dict[str, bool]) -> list[str]:
    """
    Requirement 4: if a rental type (daily/monthly/yearly) is unavailable,
    return clear human-readable messages instead of leaving data blank.
    """
    notices = []
    labels = {"daily": "Daily", "monthly": "Monthly", "yearly": "Yearly"}
    for key, available in rental_types_available.items():
        label = labels.get(key, key.title())
        if not available:
            notices.append(
                f"This platform lists monthly long-term rentals only; no "
                f"{label.lower()} rental data exists to display for this "
                f"rental type."
            )
    return notices
