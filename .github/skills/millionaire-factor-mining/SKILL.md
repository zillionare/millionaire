---
name: millionaire-factor-mining
description: Build, wind-tunnel-check, study and compare external factors for the Millionaire community edition without bypassing audit gates.
---

# Millionaire factor mining

Use this skill when an AI agent is asked to create or evaluate an external
factor for Millionaire. The CLI is the source of truth; the Web UI reads the
same persisted audit evidence.

## Non-negotiable discipline

1. Generate one factor plugin at a time in `.py` form and run the deterministic
   wind tunnel before any research or backtest.
2. Never change audit thresholds, seeds, cutoffs, `scripts/check_quality.py`,
   or the audit code to turn `FAIL` into `PASS`.
3. Never drop a `FAIL` factor silently. Stop, show the first difference and fix
   the implementation.
4. `PASS` is only valid while the current source, configuration and data
   fingerprints match the persisted report. A changed fingerprint makes the
   badge `STALE`; rerun the check.
5. Research CLI commands may read market data and write factor/preset/research
   artifacts only. They must not start or stop paper/live runtimes, mutate
   paper positions, or place live orders.

## Closed loop

```bash
# 1. Create a metadata-rich plugin template in factor_dir.
millionaire factor init ai_momentum --group "AI 因子" --json

# 2. Edit only the generated file, then run all required checks.
millionaire factor check ai_momentum --json

# 3. If FAIL, read diagnostics[].first_difference, repair the factor and rerun.
#    If INCONCLUSIVE, improve coverage or add more cutoffs; do not claim success.

# 4. Inspect collinearity and IC after PASS.
millionaire factor study ai_momentum --start 2020-01-01 --end 2024-12-31 \
  --holdings 1,3,5 --json

# 5. Save only PASS, sufficiently orthogonal factors into a named preset.
#    `--features` is comma-separated; loading re-validates existence,
#    interval and wind-tunnel status, and never silently drops a factor.
millionaire preset save --id ai_momentum_v1 --name "量价+AI动量" \
  --features ma20_slope,bias_5,ai_momentum --label-kind cs_rank \
  --params '{"top_k": 20, "train_window": 252}' --json

# 6. Run the same preset and lock baseline/variant to one interval, cash,
#    fee model, PIT universe rule and seed. `--preset` is the Variant.
millionaire preset list --json
millionaire backtest run --strategy MLMomentumReversalStrategy \
  --preset ai_momentum_v1 --ablation-vs baseline_25 \
  --start 2020-01-01 --end 2024-12-31 --initial-cash 1000000 --json
```

Exit codes are part of the contract:

- `0`: success / `PASS`
- `2`: invalid arguments or plugin contract
- `3`: wind-tunnel `FAIL`
- `4`: `INCONCLUSIVE` or insufficient evidence/data

## Required plugin contract

- Export one `FACTOR_PLUGIN = FactorPlugin(...)` from a flat `.py` file.
- Compute on the full panel and group by asset manually:
  `pl.col("close").shift(1).over("asset")`.
- Never read future rows (`shift(-n)`, `reverse`, full-sample means/ranks).
- Use `null` for warmup/missing values; never emit `NaN` or `Inf`.
- Declare `required_columns`, `bar_interval`, `scope`, `price_adjustment`,
  `warmup_bars`, `availability`, and economic metadata.
- Add `GOLDEN_CASES` when possible; independent hand calculations are stronger
  evidence than a self-generated assertion.

## Evidence to report

Always return the run id, status, source/config/data fingerprints, failed check
names, and first-difference date/asset/expected/actual. For presets and
ablations, report `preset_hash`, the shared `start`/`end`/`principal`/fee/seed
conditions, each `portfolio_id`, annual excess, drawdown/turnover deltas and the
changed-factor SHAP share table. `diagnostics: ["shap_unavailable"]` means the
SHAP claim is not supported by evidence. Link the JSON or Markdown export from
the factor detail page instead of paraphrasing a pass.
