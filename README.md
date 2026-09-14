# Ashare Index Option Chain Indicators

1a-1e文件意在构建面向 A 股 ETF 期权（以科创50ETF 588000为例）的时刻截面分析工具包：
通过 **iFind 量化接口**拉取某一到期月在某交易日收盘时的完整期权链，清洗后计算
**持仓墙（call/put wall）、最大痛苦点（max pain）、Gamma 暴露（GEX）与 zero-gamma、
隐含波动率微笑/偏斜、无模型 VIX** 等期权链指标。

整体流水线：

```
1a 合约映射  →  1b 拉取单日截面  →  1c 计算指标
                                    ↑
              1d（按日循环 1b，出 HTML）   1e（按日循环 1c，汇总 xlsx）
```

---

## 1a — `get_chain_list.ipynb`：构建合约代码映射

- 在 iFind 超级命令中勾选**同一到期日**的全部合约，把代码串粘贴进 notebook。
- 调用 iFind `date_sequence` 接口拉取每个代码的中文简称（`ths_option_short_name_option`）。
- 生成 `thscode → 简称` 映射，按 `标的_到期月`（如 `588000.SH_2608`）写入
  `option_code_map.json`，供后续脚本直接读取，避免每次手填合约代码。
- 含完整性校验：认购/认沽应成对，行数须为偶数。

**输入参数**：合约代码串、标的代码、查询日期、到期月（YYMM）、iFind access token（约 7 天有效）。

---

## 1b — `fetch_chain_data.ipynb`：拉取单日期权链截面

给定 `日期 / 标的 / 到期月`，从 iFind 拉取三类数据：

| 类别 | 字段（iFind 指标） |
|---|---|
| 合约级 | 持仓量 `oi`、持仓变化 `d_oi`、结算价 `settle`、隐含波动率 `iv`；希腊值 delta/gamma/theta/vega/rho（行情口径 + 交易所口径各一套） |
| 标的级 | 历史波动率 HV30/60/90、合约乘数、剩余自然日 `DTE_n`、剩余交易日 `DTE_t`、到期日 |
| 标的行情 | ETF 收盘价 `ETF_close` |

随后：

1. 由中文简称正则解析方向与行权价——名称含"**购**"记为 call、含"**沽**"记为 put；
   行权价取名称末尾数字除以 1000。
2. 拼接为一张宽表，落盘到 `ifind_raw_data/{MMDD}_{标的}{到期月}.csv`。

---

## 1c — `calculate_chain.ipynb`：指标计算（核心）

读取 1b 落盘的单日 CSV，结合 `Shibor_Historical_Data.xlsx` 计算当日全部指标。

### 0. 无风险利率与时间

- `tau = DTE_n / 360`（剩余自然日 / 360）。
- 按查询日期取当日 Shibor，在期限 `[1, 7, 14, 30, 90, 180, 270, 365]` 天上**线性插值**到期权实际剩余天数，得连续复利利率 `r`。

### 1. 持仓墙与最大痛苦点

- **call_wall（压力）**：所有 call 按行权价聚合持仓量 `oi`，取 `oi` 最大的行权价。
- **put_wall（支撑）**：所有 put 同理。
- **max pain**：对每个候选行权价 `K*` 计算全市场卖方的总赔付
  `pain(K*) = Σ_call oi·max(0, K*−K) + Σ_put oi·max(0, K−K*)`，
  取 `pain` 最小的 `K*`。

### 2. 静态 Net Gamma Exposure（收盘快照）

直接使用 iFind 提供的 gamma（不重算 BS）：

```
sign_i        = +1（call）/ −1（put）
gex_amount_i  = gamma_i · oi_i · multiplier · S² · 0.01 · sign_i
net_gex       = Σ gex_amount_i / 1,000,000      # 单位：百万
```

> 符号口径：当前代码 call 取正、put 取负（做市商常用的反向口径在注释中另有说明）。

### 3. IV 微笑与 Zero-Gamma 动态曲线

1. 以 `moneyness = K / S0` 为自变量，分别对 call、put 的 IV 做 **三次样条（CubicSpline）**拟合（允许外推）。
2. 模拟现货价格 `S` 在 `[S0·(1−padding), S0·(1+padding)]`（截断到挂牌行权价区间，步长 0.005）上扫描。
3. 对每个 `S`：重算 moneyness `K/S`，从对应 smile 插值出新 IV（截断到 `[0.01, 5.0]`），
   并用 Black-Scholes 公式**正向重算 gamma**：

   ```
   d1   = [ln(S/K) + (r + 0.5·σ²)·τ] / (σ·√τ)
   gamma = φ(d1) / (S · σ · √τ)
   single_gex = gamma · oi · multiplier · S² · 0.01 · sign(call + / put −)
   total_gex(S) = Σ single_gex
   ```

4. **zero-gamma**：在 `total_gex(S)` 由正转负/负转正的穿越点中，取**最接近平值（ATM）**的那个价位；
   若扫描区间内无穿越，则回退到最大行权价。

### 4. 偏斜与平值波动率

- **25Δ skew**：找 delta 最接近 `+0.25` 的 call 与最接近 `−0.25` 的 put，分别取其 IV：
  - `skew = IV_c25 − IV_p25`
  - `vol_ratio = IV_c25 / IV_p25`
  - `risk_reversal 价格 = strike_p25 − strike_c25`
- **ATM IV**：行权价最接近现价 `S0` 的合约 IV，结果乘以 100。

### 5. VIX（无模型隐含波动率）

按 CBOE VIX 口径离散计算：

```
# 理论远期价（看跌-看涨平价）
K_near      = 最接近现价的行权价
F           = K_near + (C − P) · e^(r·T)      # C/P 为 K_near 处 call/put 结算价
K0          = 不超过 F 的最大挂牌行权价

# Q(K0) 期权价序列
K < K0 → 取 put 结算价；K > K0 → 取 call 结算价；K = K0 → (C+P)/2

# 方差贡献与无模型方差
contribution = (0.05 / K²) · Q_K0
σ²   = (2·e^(r·τ) / τ) · Σ contribution  −  (1/τ)·(F/K0 − 1)²
VIX  = √max(σ², 0) · 100
```

### 输出

当日一行指标表 `metrics_df`（spot、put/call wall、max pain、net_gex、zero-gamma、
ATM IV、25Δ skew、VIX 等）写入 `tmp_metrics_temp.csv`，并绘制 OI 双柱图、IV smile、GEX 曲线图。

---

## 1d / 1e — 批处理（前者的循环）

- **1d `loop_fetch.ipynb`**：用 `papermill` 在日期区间内逐日调用 1b，逐日导出 HTML 报告（隐藏代码）。
- **1e `loop_calc_export.ipynb`**：用 `papermill` 在 MMDD 区间内逐日调用 1c，读取每日
  `tmp_metrics_temp.csv` 拼接，最终导出区间汇总 `.xlsx`。

---

## 依赖与配置

- Python：`pandas numpy scipy requests matplotlib papermill nbconvert openpyxl`
- 外部输入：iFind access token（约 7 天有效）、`option_code_map.json`、`Shibor_Historical_Data.xlsx`
- 默认标的 588000.SH、合约乘数 10000 等参数写在各 notebook 顶部，使用时按目标合约修改。

## 免责声明

本项目仅供学习与研究，希腊值与隐含波动率直接取自行情数据（zero-gamma 曲线除外），
未独立重算全部 Black-Scholes；输出不构成任何投资建议。
