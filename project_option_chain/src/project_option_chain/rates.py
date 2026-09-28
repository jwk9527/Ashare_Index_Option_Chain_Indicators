"""Shibor lookup and tenor interpolation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

SHIBOR_DAYS = np.array([1, 7, 14, 30, 90, 180, 270, 365], dtype=float)
SHIBOR_COLUMNS = ("O/N", "1W", "2W", "1M", "3M", "6M", "9M", "1Y")


def get_shibor_rate(shibor_path: Path, valuation_date: date, days_to_expiry: int) -> float:
    """Return a decimal annualized Shibor rate interpolated to the option tenor.

    When the requested date is not present, the latest available observation on
    or before it is used; if the file begins after that date, its oldest row is
    used instead.
    """
    if not shibor_path.is_file():
        raise FileNotFoundError(f"Shibor file was not found: {shibor_path}")

    rates = pd.read_excel(shibor_path, usecols=["Date", *SHIBOR_COLUMNS])
    rates["Date"] = pd.to_datetime(rates["Date"], errors="coerce")
    rates = rates.dropna(subset=["Date"]).sort_values("Date")
    if rates.empty:
        raise ValueError("The Shibor file contains no valid dated observations.")

    target = pd.Timestamp(valuation_date)
    eligible = rates.loc[rates["Date"] <= target]
    selected = eligible.iloc[-1] if not eligible.empty else rates.iloc[0]
    values = selected.loc[list(SHIBOR_COLUMNS)].to_numpy(dtype=float) / 100.0
    return float(np.interp(days_to_expiry, SHIBOR_DAYS, values))
