"""Project paths and calculation defaults."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHAIN_FILENAMES = ("0625_588000SH2607.csv",)
DEFAULT_SHIBOR_FILENAME = "Shibor_Historical_Data_副本.xlsx"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
GEX_CURVE_STEP = 0.005
GEX_PRICE_PADDING_STD_MULTIPLIER = 2.0
