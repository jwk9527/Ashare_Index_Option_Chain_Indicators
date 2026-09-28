"""Command-line entry point for a single option-chain analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from .analytics import analyze_option_chain
from .config import DATA_DIR, DEFAULT_CHAIN_FILENAMES, DEFAULT_SHIBOR_FILENAME, OUTPUT_DIR, PROJECT_ROOT
from .plotting import plot_gamma_exposure, plot_volatility_smile


def _default_input(filename: str) -> Path:
    for directory in (DATA_DIR, PROJECT_ROOT):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return DATA_DIR / filename


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate metrics and GEX for one ETF option chain.")
    parser.add_argument("--chain", type=Path, default=_default_input(DEFAULT_CHAIN_FILENAMES[0]), help="Option-chain CSV path.")
    parser.add_argument("--shibor", type=Path, default=_default_input(DEFAULT_SHIBOR_FILENAME), help="Shibor Excel path.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Directory for CSV results and chart.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analysis = analyze_option_chain(args.chain, args.shibor)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.chain.stem
    analysis.metrics.to_csv(args.output_dir / f"{stem}_metrics.csv", index=False)
    analysis.strike_gex.to_csv(args.output_dir / f"{stem}_strike_gex.csv", index=False)
    analysis.gex_curve.to_csv(args.output_dir / f"{stem}_gex_curve.csv", index=False)
    chart_path = args.output_dir / f"{stem}_gex.png"
    smile_path = args.output_dir / f"{stem}_smile.png"
    plot_gamma_exposure(analysis, chart_path)
    plot_volatility_smile(analysis, smile_path)
    print(analysis.metrics.to_string(index=False))
    print(f"Saved results to: {args.output_dir}")
    print(f"Saved chart to: {chart_path}")
    print(f"Saved volatility smile chart to: {smile_path}")


if __name__ == "__main__":
    main()
