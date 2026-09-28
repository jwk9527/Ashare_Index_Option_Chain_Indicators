# Project Option Chain

This project reorganizes the core calculations from
`1c_calculate_chain_copy_副本.ipynb` into a reusable Python package.

It analyzes one underlying and one expiry-date option chain, producing:

- risk-free rate interpolated from Shibor;
- call/put walls, max pain, net GEX and zero-gamma level;
- ATM IV, 25-delta IV skew, IV ratio and historical volatility; and
- CSV exports plus open-interest/GEX and Call/Put volatility-smile charts.

## Run

```bash
uv sync
uv run project-option-chain
```

The default command analyzes only `data/0625_588000SH2607.csv`. Select a
different point-in-time chain explicitly; the program does not combine or loop
over multiple files:

```bash
uv run project-option-chain --chain data/0623_588000SH2607.csv
```

Results are saved to `output/`. The analysis assumes the supplied vendor data
uses call-positive and put-negative GEX signs, matching the original notebook.
