# ConstructBench results

16 run files across 4 task sets.

## Runs

| Set | Model | Condition | Effort | Tasks | Runs | Accuracy (95% CI) | Field | Cost | $/correct | Out tok | s/run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| expert-s20261015 | claude-haiku-5-5 | No harness | high | 28 | 28 | 92.9% (77.4%–98.0%) | 95.7% | $0.0878 | $0.0034 | 5877 | 21.3 |
| expert-s20261015 | claude-haiku-5-5 | Harness (code + submit) | high | 28 | 28 | 100.0% (87.9%–100.0%) | 100.0% | $0.0531 | $0.0019 | 2305 | 13.2 |
| extreme-smoke | claude-haiku-5-5 | No harness | high | 4 | 4 | 100.0% (51.0%–100.0%) | 100.0% | $0.0163 | $0.0041 | 7245 | 26.4 |
| extreme-smoke | claude-haiku-5-5 | Harness (code + submit) | high | 4 | 4 | 100.0% (51.0%–100.0%) | 100.0% | $0.0097 | $0.0024 | 2461 | 15.3 |
| fresh-s20261014 | claude-haiku-5-5 | No harness | high | 51 | 51 | 100.0% (93.0%–100.0%) | 100.0% | $0.0314 | $0.0006 | 1124 | 4.6 |
| fresh-s20261014 | claude-haiku-5-5 | Harness (code + submit) | high | 51 | 51 | 98.0% (89.7%–99.7%) | 99.0% | $0.0394 | $0.0008 | 888 | 6.6 |
| fresh-s20261014 | claude-opus-5-5 | No harness | high | 51 | 51 | 100.0% (93.0%–100.0%) | 100.0% | $0.8819 | $0.0173 | 758 | 7.2 |
| fresh-s20261014 | claude-opus-5-5 | Harness (code + submit) | high | 48 | 48 | 100.0% (92.6%–100.0%) | 100.0% | $0.8593 | $0.0179 | 365 | 6.9 |
| fresh-s20261014 | claude-sonnet-5-5 | No harness | high | 51 | 51 | 100.0% (93.0%–100.0%) | 100.0% | $0.3560 | $0.0070 | 592 | 4.8 |
| fresh-s20261014 | claude-sonnet-5-5 | Harness (code + submit) | high | 51 | 51 | 100.0% (93.0%–100.0%) | 100.0% | $0.4545 | $0.0089 | 341 | 4.8 |
| quick-families | claude-haiku-5-5 | No harness | high | 41 | 41 | 100.0% (91.4%–100.0%) | 100.0% | $0.0210 | $0.0005 | 946 | 4.2 |
| quick-families | claude-haiku-5-5 | Harness (code + submit) | high | 41 | 41 | 97.6% (87.4%–99.6%) | 98.8% | $0.0246 | $0.0006 | 649 | 5.0 |
| quick-families | claude-opus-5-5 | No harness | high | 41 | 41 | 100.0% (91.4%–100.0%) | 100.0% | $0.6196 | $0.0151 | 677 | 6.6 |
| quick-families | claude-opus-5-5 | Harness (code + submit) | high | 41 | 41 | 100.0% (91.4%–100.0%) | 100.0% | $0.6932 | $0.0169 | 355 | 9.8 |
| quick-families | claude-sonnet-5-5 | No harness | high | 41 | 41 | 100.0% (91.4%–100.0%) | 100.0% | $0.2434 | $0.0059 | 515 | 3.8 |
| quick-families | claude-sonnet-5-5 | Harness (code + submit) | high | 41 | 41 | 100.0% (91.4%–100.0%) | 100.0% | $0.3188 | $0.0078 | 289 | 4.0 |

## Each condition vs the same model's baseline (paired by task)

| Set | Model | Effort | Condition | Tasks | Δ accuracy, pts (95% CI) | Better / worse tasks | p (sign-flip) | p (McNemar) | $/correct vs base |
|---|---|---|---|---|---|---|---|---|---|
| expert-s20261015 | claude-haiku-5-5 | high | Harness (code + submit) | 28 | +7.1 (+0.0 to +17.9) | 2 / 0 | 0.5 | 0.5 | $0.0019 vs $0.0034 |
| extreme-smoke | claude-haiku-5-5 | high | Harness (code + submit) | 4 | +0.0 (+0.0 to +0.0) | 0 / 0 | 1 | 1 | $0.0024 vs $0.0041 |
| fresh-s20261014 | claude-haiku-5-5 | high | Harness (code + submit) | 51 | -2.0 (-5.9 to +0.0) | 0 / 1 | 1 | 1 | $0.0008 vs $0.0006 |
| fresh-s20261014 | claude-opus-5-5 | high | Harness (code + submit) | 48 | +0.0 (+0.0 to +0.0) | 0 / 0 | 1 | 1 | $0.0179 vs $0.0170 |
| fresh-s20261014 | claude-sonnet-5-5 | high | Harness (code + submit) | 51 | +0.0 (+0.0 to +0.0) | 0 / 0 | 1 | 1 | $0.0089 vs $0.0070 |
| quick-families | claude-haiku-5-5 | high | Harness (code + submit) | 41 | -2.4 (-7.3 to +0.0) | 0 / 1 | 1 | 1 | $0.0006 vs $0.0005 |
| quick-families | claude-opus-5-5 | high | Harness (code + submit) | 41 | +0.0 (+0.0 to +0.0) | 0 / 0 | 1 | 1 | $0.0169 vs $0.0151 |
| quick-families | claude-sonnet-5-5 | high | Harness (code + submit) | 41 | +0.0 (+0.0 to +0.0) | 0 / 0 | 1 | 1 | $0.0078 vs $0.0059 |

## Failure categories (runs)

| Set | Model | Condition | Effort | Runs | format: prose in ID list | numeric error (>1%) | no answer: out of tokens |
|---|---|---|---|---|---|---|---|
| expert-s20261015 | claude-haiku-5-5 | Harness (code + submit) | high | 28 | 0 | 0 | 0 |
| expert-s20261015 | claude-haiku-5-5 | No harness | high | 28 | 0 | 1 | 1 |
| extreme-smoke | claude-haiku-5-5 | Harness (code + submit) | high | 4 | 0 | 0 | 0 |
| extreme-smoke | claude-haiku-5-5 | No harness | high | 4 | 0 | 0 | 0 |
| fresh-s20261014 | claude-haiku-5-5 | Harness (code + submit) | high | 51 | 1 | 0 | 0 |
| fresh-s20261014 | claude-haiku-5-5 | No harness | high | 51 | 0 | 0 | 0 |
| fresh-s20261014 | claude-opus-5-5 | Harness (code + submit) | high | 48 | 0 | 0 | 0 |
| fresh-s20261014 | claude-opus-5-5 | No harness | high | 51 | 0 | 0 | 0 |
| fresh-s20261014 | claude-sonnet-5-5 | Harness (code + submit) | high | 51 | 0 | 0 | 0 |
| fresh-s20261014 | claude-sonnet-5-5 | No harness | high | 51 | 0 | 0 | 0 |
| quick-families | claude-haiku-5-5 | Harness (code + submit) | high | 41 | 1 | 0 | 0 |
| quick-families | claude-haiku-5-5 | No harness | high | 41 | 0 | 0 | 0 |
| quick-families | claude-opus-5-5 | Harness (code + submit) | high | 41 | 0 | 0 | 0 |
| quick-families | claude-opus-5-5 | No harness | high | 41 | 0 | 0 | 0 |
| quick-families | claude-sonnet-5-5 | Harness (code + submit) | high | 41 | 0 | 0 | 0 |
| quick-families | claude-sonnet-5-5 | No harness | high | 41 | 0 | 0 | 0 |

## Figures

![fig_accuracy_expert-s20261015.svg](fig_accuracy_expert-s20261015.svg)
![fig_accuracy_extreme-smoke.svg](fig_accuracy_extreme-smoke.svg)
![fig_accuracy_fresh-s20261014.svg](fig_accuracy_fresh-s20261014.svg)
![fig_accuracy_quick-families.svg](fig_accuracy_quick-families.svg)
![fig_size.svg](fig_size.svg)
![fig_failures.svg](fig_failures.svg)
![fig_pareto.svg](fig_pareto.svg)

Costs are client-side estimates from token usage × list price (Claude); runs without a recorded cost are left out of cost columns and the Pareto figure. Accuracy CIs are Wilson intervals over runs; paired differences use the task as the unit (repeats averaged) with a bootstrap CI.
