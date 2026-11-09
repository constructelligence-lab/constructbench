# Results

Generated from [`paper/report/runs.csv`](../paper/report/runs.csv) by `scripts/make_leaderboard.py`. Every row is a model run on a fixed, seeded task set;
accuracy is **strict** (every field of the answer must be right) with a 95% Wilson interval. Read the caveats at the bottom before quoting a number.

## expert-s20261015

| Model | Condition | Tasks run | Strict accuracy (95% CI) | Field score | Cost | $ per correct |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | No harness | 28 | 92.9% (77.4% to 98.0%) | 95.7% | $0.09 | $0.0034 |
| claude-haiku-5-5 | Code tool + strict answer | 28 | 100.0% (87.9% to 100.0%) | 100.0% | $0.05 | $0.0019 |

## expert84-s20261015

| Model | Condition | Tasks run | Strict accuracy (95% CI) | Field score | Cost | $ per correct |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | No harness | 84 | 91.7% (83.8% to 95.9%) | 95.1% | $0.27 | $0.0036 |
| claude-haiku-5-5 | Code tool + strict answer | 82 | 100.0% (95.5% to 100.0%) | 100.0% | $0.15 | $0.0019 |
| deepseek-flash | No harness | 84 | 92.9% (85.3% to 96.7%) | 92.9% | n/a | n/a |
| deepseek-flash | Code tool + strict answer | 84 | 97.6% (91.7% to 99.3%) | 99.0% | n/a | n/a |
| inclusionai/ling-3.0-flash | No harness | 84 | 40.5% (30.6% to 51.2%) | 46.7% | $0.11 | $0.0034 |
| inclusionai/ling-3.0-flash | Code tool + strict answer | 84 | 96.4% (90.0% to 98.8%) | 98.2% | $0.09 | $0.0011 |
| openai/gpt-oss-120b | No harness | 10 of 84 | 0.0% (0.0% to 27.8%) | 32.0% | $0.03 | n/a |
| openai/gpt-oss-120b | Code tool + strict answer | 1 of 84 | 0.0% (0.0% to 79.3%) | 0.0% | n/a | n/a |

## extreme-smoke

| Model | Condition | Tasks run | Strict accuracy (95% CI) | Field score | Cost | $ per correct |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | No harness | 4 | 100.0% (51.0% to 100.0%) | 100.0% | $0.02 | $0.0041 |
| claude-haiku-5-5 | Code tool + strict answer | 4 | 100.0% (51.0% to 100.0%) | 100.0% | $0.01 | $0.0024 |

## fresh-s20261014

| Model | Condition | Tasks run | Strict accuracy (95% CI) | Field score | Cost | $ per correct |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | No harness | 51 | 100.0% (93.0% to 100.0%) | 100.0% | $0.03 | $0.0006 |
| claude-haiku-5-5 | Code tool + strict answer | 51 | 98.0% (89.7% to 99.7%) | 99.0% | $0.04 | $0.0008 |
| claude-opus-5-5 | No harness | 51 | 100.0% (93.0% to 100.0%) | 100.0% | $0.88 | $0.0173 |
| claude-opus-5-5 | Code tool + strict answer | 48 | 100.0% (92.6% to 100.0%) | 100.0% | $0.86 | $0.0179 |
| claude-sonnet-5-5 | No harness | 51 | 100.0% (93.0% to 100.0%) | 100.0% | $0.36 | $0.0070 |
| claude-sonnet-5-5 | Code tool + strict answer | 51 | 100.0% (93.0% to 100.0%) | 100.0% | $0.45 | $0.0089 |

## quick-families

| Model | Condition | Tasks run | Strict accuracy (95% CI) | Field score | Cost | $ per correct |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | No harness | 41 | 100.0% (91.4% to 100.0%) | 100.0% | $0.02 | $0.0005 |
| claude-haiku-5-5 | Code tool + strict answer | 41 | 97.6% (87.4% to 99.6%) | 98.8% | $0.02 | $0.0006 |
| claude-opus-5-5 | No harness | 41 | 100.0% (91.4% to 100.0%) | 100.0% | $0.62 | $0.0151 |
| claude-opus-5-5 | Code tool + strict answer | 41 | 100.0% (91.4% to 100.0%) | 100.0% | $0.69 | $0.0169 |
| claude-sonnet-5-5 | No harness | 41 | 100.0% (91.4% to 100.0%) | 100.0% | $0.24 | $0.0059 |
| claude-sonnet-5-5 | Code tool + strict answer | 41 | 100.0% (91.4% to 100.0%) | 100.0% | $0.32 | $0.0078 |
| deepseek-flash | No harness | 1 | 100.0% (20.7% to 100.0%) | 100.0% | n/a | n/a |
| deepseek-flash | Code tool + strict answer | 1 | 100.0% (20.7% to 100.0%) | 100.0% | n/a | n/a |
| deepseek-v4-pro | No harness | 1 | 100.0% (20.7% to 100.0%) | 100.0% | n/a | n/a |
| deepseek-v4-pro | Code tool + strict answer | 1 | 100.0% (20.7% to 100.0%) | 100.0% | n/a | n/a |

## Caveats

- **Frontier models are at the ceiling on the original sets.** Claude Opus, Sonnet and Haiku score at or near 100% on `quick-families` and `fresh-*`, so those sets cannot separate them. The harder expert sets, and the families still being added, exist for that reason.
- **Incomplete runs are not failures.** Where "Tasks run" is lower than the set size, the run stopped (a cost cap or a rate limit) and the missing tasks are reported as not run, never as wrong. Treat those rows as partial; the wide intervals show it.
- **`quick-families` is a development set.** It was used while the harness was being built, so it is not a clean test of anything. `fresh-*` and `expert*` sets were generated afterwards.
- **One seed per set.** A different seed gives different numbers; the intervals cover task sampling within a set, not seed-to-seed variation.
- **Costs are client-side estimates** from token counts and list prices. DeepSeek rows have no cost: its spend was measured as an account balance change, not per task.
- **Held-out sets are private.** The sets used to check a model that may have trained on public items are not in this repository.

Add your own run with `python -m constructbench run ...` and `leaderboard` (see the README). Open a pull request with the result file and the exact command.
