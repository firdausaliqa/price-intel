"""
Export helpers: produce CSV/XLSX bytes and a dynamic filename per
Requirement 5, e.g. SPEEDHOME_MontKiara_2026-07-13.csv
"""
from __future__ import annotations
import io
import re
from datetime import date
import pandas as pd


def _slugify_area_name(area_name: str) -> str:
    """'Mont Kiara' -> 'MontKiara' (CamelCase, no spaces/punctuation)."""
    words = re.findall(r"[A-Za-z0-9]+", area_name)
    return "".join(w.capitalize() for w in words) or "Area"


def build_filename(area_name: str, extension: str, as_of: date | None = None) -> str:
    as_of = as_of or date.today()
    area_part = _slugify_area_name(area_name)
    return f"SPEEDHOME_{area_part}_{as_of.isoformat()}.{extension}"


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Listings") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()
