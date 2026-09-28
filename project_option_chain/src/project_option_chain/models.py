"""Typed result containers for option-chain analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class ChainMetadata:
    valuation_date: date
    spot: float
    multiplier: float
    days_to_expiry: int
    risk_free_rate: float


@dataclass(frozen=True)
class ChainAnalysis:
    metadata: ChainMetadata
    metrics: pd.DataFrame
    options: pd.DataFrame
    strike_gex: pd.DataFrame
    gex_curve: pd.DataFrame
