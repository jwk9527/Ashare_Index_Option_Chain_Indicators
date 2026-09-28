"""Single-expiry option-chain metrics and gamma-exposure calculations."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

from .config import GEX_CURVE_STEP, GEX_PRICE_PADDING_STD_MULTIPLIER
from .models import ChainAnalysis, ChainMetadata
from .rates import get_shibor_rate

REQUIRED_COLUMNS = {"date", "ETF_close", "oi", "iv", "delta", "gamma", "mul", "DTE_n", "name", "hv30", "hv60", "hv90"}


def _parse_contract_name(name: str) -> tuple[int, int, float]:
    text = str(name)
    is_call = int("购" in text)
    is_put = int("沽" in text)
    strikes = re.findall(r"\d+", text)
    return is_call, is_put, float(strikes[-1]) / 1000 if strikes else np.nan


def load_option_chain(csv_path: Path) -> pd.DataFrame:
    """Load and validate an exported option-chain CSV."""
    options = pd.read_csv(csv_path).dropna().copy()
    missing = REQUIRED_COLUMNS.difference(options.columns)
    if missing:
        raise ValueError(f"Option-chain CSV is missing columns: {', '.join(sorted(missing))}")
    if options.empty:
        raise ValueError("Option-chain CSV has no complete records.")

    parsed = options["name"].map(_parse_contract_name)
    options[["is_call", "is_put", "strike_price"]] = pd.DataFrame(parsed.tolist(), index=options.index)
    if options[["is_call", "is_put", "strike_price"]].isna().any().any() or not (options["is_call"] | options["is_put"]).all():
        raise ValueError("Could not parse option type or strike price from one or more contract names.")
    return options


def _max_pain(options: pd.DataFrame) -> float:
    strikes = np.sort(options["strike_price"].unique())
    calls = options.loc[options["is_call"] == 1]
    puts = options.loc[options["is_put"] == 1]
    pain = [
        (strike, (calls["oi"] * np.maximum(0, strike - calls["strike_price"])).sum() + (puts["oi"] * np.maximum(0, puts["strike_price"] - strike)).sum())
        for strike in strikes
    ]
    return float(min(pain, key=lambda item: item[1])[0])


def fit_iv_smiles(options: pd.DataFrame, spot: float) -> tuple[CubicSpline, CubicSpline]:
    """Fit separate call and put IV smiles using the 1c CubicSpline method."""
    def spline_for(option_type: int) -> CubicSpline:
        subset = options.loc[options["is_call"] == option_type, ["strike_price", "iv"]].groupby("strike_price", as_index=False).mean().sort_values("strike_price")
        if len(subset) < 2:
            raise ValueError("At least two strikes are required for each option type to fit the IV smile.")
        return CubicSpline(subset["strike_price"].to_numpy() / spot, subset["iv"].to_numpy(), extrapolate=True)

    return spline_for(1), spline_for(0)


def _gex_curve(options: pd.DataFrame, spot: float, multiplier: float, tau: float, rate: float) -> pd.DataFrame:
    call_smile, put_smile = fit_iv_smiles(options, spot)
    strikes = options["strike_price"].to_numpy(dtype=float)
    types = options["is_call"].to_numpy(dtype=bool)
    open_interest = options["oi"].to_numpy(dtype=float)
    padding = options["strike_price"].std() * GEX_PRICE_PADDING_STD_MULTIPLIER
    low = max(round(spot - padding, 3), float(strikes.min()))
    high = min(round(spot + padding, 3), float(strikes.max()))
    prices = np.round(np.arange(low, high + GEX_CURVE_STEP / 2, GEX_CURVE_STEP), 3)
    sqrt_tau = np.sqrt(tau)
    records: list[dict[str, float]] = []

    for simulated_spot in prices:
        moneyness = strikes / simulated_spot
        iv = np.where(types, call_smile(moneyness), put_smile(moneyness))
        iv = np.clip(iv, 0.01, 5.0)
        d1 = (np.log(simulated_spot / strikes) + (rate + 0.5 * iv**2) * tau) / (iv * sqrt_tau)
        gamma = np.exp(-0.5 * d1**2) / (np.sqrt(2 * np.pi) * simulated_spot * iv * sqrt_tau)
        signs = np.where(types, 1.0, -1.0)
        total_gex = (gamma * open_interest * multiplier * simulated_spot**2 * 0.01 * signs).sum()
        records.append({"test_price": simulated_spot, "total_gex": total_gex})
    return pd.DataFrame.from_records(records)


def _zero_gamma(curve: pd.DataFrame, spot: float) -> float | None:
    gex = curve["total_gex"]
    crossings = curve.loc[gex.mul(gex.shift()).lt(0)].copy()
    if crossings.empty:
        return None
    crossings["distance"] = (crossings["test_price"] - spot).abs()
    return float(crossings.loc[crossings["distance"].idxmin(), "test_price"])


def _nearest_iv(options: pd.DataFrame, spot: float) -> tuple[float, float, float, float, float]:
    calls = options.loc[options["is_call"] == 1]
    puts = options.loc[options["is_put"] == 1]
    call_25 = calls.loc[(calls["delta"] - 0.25).abs().idxmin()]
    put_25 = puts.loc[(puts["delta"] + 0.25).abs().idxmin()]
    atm = options.loc[(options["strike_price"] - spot).abs().idxmin()]
    call_iv, put_iv = float(call_25["iv"]), float(put_25["iv"])
    return float(atm["iv"]), call_iv - put_iv, call_iv / put_iv, float(put_25["strike_price"] - call_25["strike_price"]), float(atm["strike_price"])


def analyze_option_chain(csv_path: Path, shibor_path: Path) -> ChainAnalysis:
    """Calculate core 1c metrics for one underlying and one expiry date."""
    options = load_option_chain(csv_path)
    first = options.iloc[0]
    valuation_date = pd.Timestamp(first["date"]).date()
    spot, multiplier, dte = float(first["ETF_close"]), float(first["mul"]), int(first["DTE_n"])
    tau = dte / 360.0
    rate = get_shibor_rate(shibor_path, valuation_date, dte)

    call_wall = options.loc[options["is_call"] == 1].groupby("strike_price")["oi"].sum().idxmax()
    put_wall = options.loc[options["is_put"] == 1].groupby("strike_price")["oi"].sum().idxmax()
    options["gex_amount"] = options["gamma"] * options["oi"] * multiplier * spot**2 * 0.01 * np.where(options["is_call"] == 1, 1, -1)
    strike_gex = options.groupby("strike_price", as_index=False)["gex_amount"].sum().sort_values("strike_price")
    curve = _gex_curve(options, spot, multiplier, tau, rate)
    zero_gamma = _zero_gamma(curve, spot)
    atm_iv, skew, volatility_ratio, risk_reversal, atm_strike = _nearest_iv(options, spot)
    metrics = pd.DataFrame([{
        "date": valuation_date.isoformat(), "spot": round(spot, 3), "risk_free_rate": rate,
        "days_to_expiry": dte, "call_wall": round(float(call_wall), 3), "put_wall": round(float(put_wall), 3),
        "max_pain": round(_max_pain(options), 3), "net_gex_million": round(options["gex_amount"].sum() / 1_000_000, 2),
        "zero_gamma": None if zero_gamma is None else round(zero_gamma, 3), "atm_iv": atm_iv,
        "atm_strike": atm_strike, "call25_put25_iv_skew": skew, "call25_put25_iv_ratio": volatility_ratio,
        "put25_minus_call25_strike": risk_reversal, "hv30": float(first["hv30"]), "hv60": float(first["hv60"]), "hv90": float(first["hv90"]),
    }])
    metadata = ChainMetadata(valuation_date, spot, multiplier, dte, rate)
    return ChainAnalysis(metadata, metrics, options, strike_gex, curve)
