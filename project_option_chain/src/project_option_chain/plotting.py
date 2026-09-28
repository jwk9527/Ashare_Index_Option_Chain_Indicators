"""Matplotlib visualizations for a completed option-chain analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .models import ChainAnalysis
from .analytics import fit_iv_smiles


def _strike_position(value: float | None, strikes: np.ndarray) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return float(np.interp(value, strikes, np.arange(len(strikes))))


def plot_gamma_exposure(analysis: ChainAnalysis, output_path: Path) -> None:
    """Save the 1c open-interest and gamma-exposure chart."""
    options, metrics, strike_gex = analysis.options, analysis.metrics.iloc[0], analysis.strike_gex
    strikes = np.sort(options["strike_price"].unique())
    call_oi = options.loc[options["is_call"] == 1].groupby("strike_price")["oi"].sum().reindex(strikes, fill_value=0)
    put_oi = options.loc[options["is_put"] == 1].groupby("strike_price")["oi"].sum().reindex(strikes, fill_value=0)
    positions = np.arange(len(strikes))
    figure, (ax_oi, ax_gex) = plt.subplots(2, 1, figsize=(15, 12), sharex=True, layout="constrained")

    width = 0.36
    call_bars = ax_oi.bar(positions - width / 2, call_oi, width, label="Call OI", color="#d95f5f")
    put_bars = ax_oi.bar(positions + width / 2, put_oi, width, label="Put OI", color="#4db6a1")
    for key, color, style, label in (("call_wall", "#8b0000", "-", "Call wall"), ("put_wall", "#006400", "-", "Put wall"), ("max_pain", "#1f77b4", ":", "Max pain"), ("spot", "#0000aa", "--", "Spot")):
        ax_oi.axvline(_strike_position(float(metrics[key]), strikes), color=color, linestyle=style, linewidth=2, label=f"{label}: {metrics[key]:.3f}")
    ax_oi.set_title(f"{metrics['date']} option chain: open interest and gamma exposure")
    ax_oi.set_ylabel("Open interest")
    ax_oi.grid(alpha=0.25)
    ax_oi.legend(ncol=2)
    for bars in (call_bars, put_bars):
        for bar in bars:
            ax_oi.annotate(
                f"{bar.get_height() / 1000:.0f}k",
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )

    curve_positions = [_strike_position(price, strikes) for price in analysis.gex_curve["test_price"]]
    curve_values = analysis.gex_curve["total_gex"].to_numpy()
    ax_gex.plot(curve_positions, curve_values, color="#666666", linewidth=1.2, label="Aggregate GEX curve")
    curve_limit = float(np.abs(curve_values).max())
    ax_gex.set_ylim(-curve_limit, curve_limit)
    ax_gex.axhline(0, color="black", linewidth=1)
    ax_gex_right = ax_gex.twinx()
    gex_values = strike_gex["gex_amount"].to_numpy()
    gex_bars = ax_gex_right.bar(positions, gex_values, width=0.62, color=np.where(gex_values >= 0, "#d95f5f", "#4db6a1"), alpha=0.75, label="GEX by strike")
    bar_limit = float(np.abs(gex_values).max())
    ax_gex_right.set_ylim(-bar_limit, bar_limit)
    zero_gamma = metrics["zero_gamma"]
    if zero_gamma is not None and np.isfinite(zero_gamma):
        zero_position = _strike_position(float(zero_gamma), strikes)
        ax_gex.axvspan(ax_gex.get_xlim()[0], zero_position, facecolor="#ffdddd", alpha=0.4, zorder=-1)
        ax_gex.axvspan(zero_position, ax_gex.get_xlim()[1], facecolor="#ddffdd", alpha=0.4, zorder=-1)
        ax_gex.axvline(zero_position, color="#d97706", linewidth=2.5, label=f"Zero gamma: {zero_gamma:.3f}")
    ax_gex.axvline(_strike_position(float(metrics["spot"]), strikes), color="#0000aa", linestyle="--", linewidth=2, label=f"Spot: {metrics['spot']:.3f}")
    ax_gex.set_ylabel("Aggregate GEX")
    ax_gex_right.set_ylabel("GEX by strike")
    ax_gex.set_xlabel("Strike price")
    ax_gex.set_xticks(positions, [f"{strike:.3f}" for strike in strikes], rotation=45)
    ax_gex.grid(alpha=0.25)
    handles, labels = ax_gex.get_legend_handles_labels()
    right_handles, right_labels = ax_gex_right.get_legend_handles_labels()
    ax_gex.legend(handles + right_handles, labels + right_labels, loc="upper left")
    for bar in gex_bars:
        height = bar.get_height()
        ax_gex_right.annotate(
            f"{height / 1_000_000:.1f}M",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom" if height >= 0 else "top",
            fontsize=9,
        )

    net_gex = float(metrics["net_gex_million"])
    if zero_gamma is None or not np.isfinite(zero_gamma):
        gamma_message = "Zero gamma was not found within the simulated range."
    else:
        distance_pct = (float(metrics["spot"]) - float(zero_gamma)) / float(zero_gamma) * 100
        gamma_side = "above" if distance_pct >= 0 else "below"
        gamma_effect = "E.Stabilizing" if distance_pct >= 0 else "E.Squeezing"
        gamma_message = f"Close prc. {gamma_side} zero gamma:\n{distance_pct:+.2f}% -> *{gamma_effect}*"
    net_gex_label = f"+{net_gex:.2f}" if net_gex >= 0 else f"{net_gex:.2f}"
    gamma_regime = "Long Gamma" if net_gex >= 0 else "Short Gamma"
    ax_gex.text(
        0.98,
        0.03,
        f"net GEX: {net_gex_label} mil.CNY -> {gamma_regime}\n{gamma_message}",
        transform=ax_gex.transAxes,
        ha="right",
        va="bottom",
        fontsize=12,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "alpha": 0.7},
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_volatility_smile(analysis: ChainAnalysis, output_path: Path) -> None:
    """Save the Call/Put IV-smile inspection chart from the original 1c notebook."""
    options = analysis.options
    spot = analysis.metadata.spot
    call_smile, put_smile = fit_iv_smiles(options, spot)
    calls = options.loc[options["is_call"] == 1].sort_values("strike_price")
    puts = options.loc[options["is_put"] == 1].sort_values("strike_price")

    call_moneyness = calls["strike_price"].to_numpy() / spot
    put_moneyness = puts["strike_price"].to_numpy() / spot
    call_iv = calls["iv"].to_numpy()
    put_iv = puts["iv"].to_numpy()
    lower = min(call_moneyness.min(), put_moneyness.min())
    upper = max(call_moneyness.max(), put_moneyness.max())
    dense_moneyness = np.linspace(lower - 0.1, upper + 0.1, 300)
    call_curve = np.clip(call_smile(dense_moneyness), 0.01, 5.0)
    put_curve = np.clip(put_smile(dense_moneyness), 0.01, 5.0)

    figure, (call_axis, put_axis) = plt.subplots(1, 2, figsize=(12, 5))
    call_axis.scatter(call_moneyness, call_iv, color="crimson", label="Raw DB IV (Call)", s=40, zorder=3)
    call_axis.plot(dense_moneyness, call_curve, color="royalblue", linestyle="--", linewidth=1.5, label="CubicSpline Curve")
    call_axis.axvline(1.0, color="darkgray", linestyle=":", label="ATM (M=1.0)")
    call_axis.set_title("Call Option Volatility Smile (Sticky Delta)", fontsize=11)
    call_axis.set_xlabel("Moneyness (K / S)")
    call_axis.set_ylabel("Implied Volatility")
    call_axis.legend()
    call_axis.grid(True, alpha=0.3)

    put_axis.scatter(put_moneyness, put_iv, color="darkorange", label="Raw DB IV (Put)", s=40, zorder=3)
    put_axis.plot(dense_moneyness, put_curve, color="forestgreen", linestyle="--", linewidth=1.5, label="CubicSpline Curve")
    put_axis.axvline(1.0, color="darkgray", linestyle=":", label="ATM (M=1.0)")
    put_axis.set_title("Put Option Volatility Smile (Sticky Delta)", fontsize=11)
    put_axis.set_xlabel("Moneyness (K / S)")
    put_axis.set_ylabel("Implied Volatility")
    put_axis.legend()
    put_axis.grid(True, alpha=0.3)

    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
