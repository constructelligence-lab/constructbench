# ConstructBench — lab notebook (harness vs. no harness, frontier and open models)

Running record for a paper. Entries are dated (local time unless stated) and never rewritten — later
corrections are new entries that point back. Every run also writes a machine-readable manifest next to its results
(`results/<set>/<run>.jsonl.manifest.jsonl`: git commit, dirty files, model, settings, task-set SHA-256, the harness's
exact prompts, prices, SDK/Python versions). `results/` is git-ignored: archive it with the paper's data.

---

## 1. Research question

How much does a tool harness (code execution + schema-constrained answer submission) change the accuracy of frontier
and open-weight language models on construction-industry tasks, and does the gain differ by model size and domain?

## 2. Materials

### 2.1 Benchmark
- ConstructBench, local repository `~/Downloads/constructbench` (not public). Tasks are produced by seeded Python
  generators; answers are computed by the generator, never hand-keyed. A set is fully determined by (seed, per-family).
- Grading: the reply's last `ANSWER: {json}` line; per-field tolerances; **strict accuracy** = every field correct;
  field score = partial credit; 95% Wilson intervals.

### 2.2 Task set used: `data/quick-families.jsonl`
- 41 tasks, one per task family, 13 domains, text only (the 7 image families are excluded), seed 1.
- Difficulty: 18 easy / 19 medium / 4 hard.
- SHA-256 `a642df49fc6c0694dc9024be0f8dd671b4fb0a8785a785d5d88889110ac445a1`.
- Generated before the quality, contracts & claims, and BIM domains were added (current generator: 58 families,
  17 domains); those domains are therefore absent from this set.

### 2.3 Conditions
- **Baseline** (`anthropic:<model>` / `api:<model>@<url>` / `local:<model>`): one request; system prompt `SYSTEM`
  asks for a final `ANSWER: {json}` line; no tools.
- **Harness** (`…+code+submit`), identical across APIs (class `Toolbox` in `constructbench/providers.py`):
  - `run_python`: runs model-written Python in a sandbox subprocess (`python -I -S`, allow-listed modules: datetime,
    decimal, fractions, functools, itertools, json, math, statistics; no files/network; 30 s). Preloaded: the task's
    markdown tables as `TABLES`, verbatim blocks as `TEXTS`, bullet lists as `BULLETS` (parsed from the prompt), and
    a toolkit (`cpm`, `pv`, `pv_annuity`, `npv`, `irr`, `round_half_up`, `parse_step`, `box_overlap`, `box_gap`).
  - `submit_answer`: JSON schema built from the prompt's own "Answer keys" line (names and types only; the grader's
    answers and tolerances are never read). Claude: enforced by the API (`strict: true`). OpenAI-compatible servers:
    checked by the harness; a submission with missing/mistyped/extra keys is returned once for correction.
  - Extra system text (verbatim in manifests): `CODE_NOTE`, `SUBMIT_NOTE`; at the last allowed turn `LAST_TURN_NOTE`.
  - Up to 12 model turns per task. Tool choice `auto` (forced tool use is rejected by the current Claude models).
- Claude settings: adaptive thinking, effort `high` (set explicitly; Opus 5.5 defaults to `medium`), max 16,000
  output tokens per reply, prompt caching on (automatic), no server-side refusal fallback (a fallback would answer
  with a different model). OpenAI-compatible: temperature 0, max 4,096 tokens per reply unless `--max-tokens`.

### 2.4 Cost accounting
- Cost per reply computed client-side from `usage` × list price (`PRICES` in providers.py, as of 2026-10):
  input + 1.25 × input price for cache writes + cache-read price for cache reads + output price for output tokens
  (thinking tokens are billed as output and are included in `output_tokens`). Not reconciled against the invoice yet.
- Hard limits: `--budget` (USD, shared across all Claude result files in the run folder; a task starts only if
  spend so far + mean cost per in-flight task stays under it; one task at a time until a price is seen) and
  `--task-budget` (USD per harness task; nudge to submit at 60%, stop at 100%, recorded as `stop_reason: task_budget`).

## 3. Known limitations / threats to validity (keep updating)

1. **Development seed.** The quick set is seed 1, the same public dev seed on which the small-model `ci:` agent and
   the toolkit were developed (Sept–Oct 2026). The harness tools were designed with these task *families* in mind
   (e.g. a CPM helper because scheduling families need one). Generic over items, not over families. A clean result
   needs a never-inspected seed (§5 plan).
2. **One task per family**: n = 41 per condition → 95% CIs roughly ±15 points; per-domain numbers are 2–5 tasks
   and are descriptive only.
3. **Single sample per task**: thinking models are not deterministic (no temperature control on current Claude
   models); no run-to-run variance is measured.
4. **Budget truncation**: with a $5 Claude budget some conditions may not finish; unfinished tasks are reported as
   not run, never as wrong. Task-budget stops are reported separately.
5. `data/heldout-text.jsonl` (seed 90210, 82 tasks, 2 per family of the same 41 families) exists; whether it was
   inspected during harness development is **not recorded** — treat as possibly seen.
6. Image tasks excluded, so results say nothing about drawing/plan reading.
7. Untracked files `constructbench/aec.py`, `constructbench/hf_server.py` (another project) appear as dirty in
   manifests; they are not imported by the run path (checked 2026-10-13 with grep).

## 4. Prior results on this task set (before this study)

| Run | Model | Condition | Strict | Field | Notes |
|---|---|---|---|---|---|
| 2026-09-27 | qwen2.5-1.5b-instruct Q4_K_M (LM Studio) | baseline | 0/41 (0.0%) | 3.9% | `results/qwen-family.jsonl` |
| 2026-09/10 | qwen2.5-1.5b-instruct | `ci:` agent v1 | 2/41 (4.9%) | 16.8% | different harness (program-of-thought + voting) |
| 2026-10 | qwen3-4b-instruct-2507 | baseline | 6/10 (partial run) | 66.7% | stopped early |
| 2026-10 | qwen3-4b-instruct-2507 | `ci:` agent v1 | 3/4 (partial) | 83.3% | same 3/4 as baseline on the overlapping 4 tasks |

The `ci:` agent is a different harness from `+code+submit` and is not part of this study's comparison.

## 5. Plan

1. Smoke test: Claude Opus 5.5, first task only, baseline and harness (`LIMIT=1`) — checks the API path and gives a
   real cost per task.
2. From the measured cost, choose what fits the $5 Claude budget (options: Opus both conditions; Opus harness +
   Sonnet both; Sonnet + Haiku both). Decision and reasoning to be logged here before running.
3. Other models (DeepSeek, "Astra" — to be identified, open-weight models via an OpenAI-compatible API) on both
   conditions with the identical harness.
4. If budget allows later: same 41 families on a fresh, never-inspected seed (threat 1).

## 6. Run log

### 2026-10-13
- Code prepared: Claude `+code`/`+submit` (af5a983); shared harness for OpenAI-compatible APIs, failed-call
  retries, `scripts/bench.sh` (7b99399); budgets, cost accounting, manifests (dec0233). Unit tests pass (harness
  tested against a scripted fake client and a stub OpenAI-compatible server — no live model yet).
- Environment: Python 3.13.2 venv `.venv313` (uv), `anthropic` SDK 1.13.0; macOS 26.4 arm64, 8 GB Mac
  (system load average ~30–40 during setup from other work — affects wall-clock times, not scores).
- Anthropic key supplied by the user is **user-scoped**: every request returns HTTP 400 until the
  `anthropic-workspace-id` header is sent. Provider now sends it from `ANTHROPIC_WORKSPACE_ID`. **Blocked** on the
  workspace ID; no Claude request has succeeded yet, $0 spent.

### 2026-10-13 (late evening)
- Workspace ID supplied; header path works. `models.list` shows: claude-haiku-5-5, claude-sonnet-5-5,
  claude-opus-5-5, claude-fable-5-1, claude-opus-5, claude-sonnet-5, claude-fable-5, claude-opus-4-8/4-7/4-6,
  claude-sonnet-4-6, claude-opus-4-5, claude-haiku-4-5. Quick-set prompts total 12,280 input tokens (Opus 5.5
  count_tokens, prompt text only).
- **Smoke test** (`LIMIT=1`, task arch-far-0000, easy, Opus 5.5, effort high, BUDGET 4.50, TASK_BUDGET 0.40):
  baseline correct, 337 in / 431 out tokens, $0.0100, 3.8 s; harness correct, 2 turns, 1 code run, submitted via
  tool, 3,126 in / 242 out, $0.0133, 9.1 s. Harness input is ~10× baseline (tool descriptions + toolkit help + a
  second turn) but cached on later turns.
- Bug found and fixed during smoke test: `bench.sh` passed `*.manifest.jsonl` to `leaderboard` (crash, no effect
  on results). Fixed by filtering manifests.
- **Decision** (before full runs): measured ~$0.01–0.015 per easy task ⇒ Opus 5.5 both conditions on all 41 tasks
  estimated at $1–3 (hard tasks think longer). Order: (1) Opus 5.5 baseline + harness, (2) Haiku 5.5 both
  (≈1/40 of Opus price), (3) Sonnet 5.5 both with what remains. Global cap $4.50 across all Claude files, task cap
  $0.40, 4 workers. Smoke-test records are kept (same task ids, resumed, not re-run).
- **Result — Opus 5.5, quick set (41 tasks), effort high:** baseline 41/41 (100%, 95% CI 91.4–100%), $0.620,
  mean 677 output tokens, 6.6 s/task; harness 41/41 (100%, same CI), $0.693, mean 355 output tokens, 9.8 s/task,
  2.2 turns and 1.2 code runs per task, 41/41 answers via submit_answer, 0 rejected submissions, 0 task-budget
  stops, 0 API errors. Field score 100% both. **Ceiling effect: the quick set cannot separate the conditions for
  Opus 5.5.** Note: wall times measured under high machine load (load avg ~30–40) and 4 parallel workers.
- Claude spend so far: $1.326 (incl. smoke test). Next: Haiku 5.5 and Sonnet 5.5, both conditions, same settings.
- LM Studio (0.4.16) local server did not respond (`lms server start` stuck at "Waking up LM Studio service");
  local open-weight runs deferred until it is restarted.
- **Fresh held-out set created** (addresses threat 1): `data/fresh-s20261014.jsonl` = `registry.build(seed=20261014,
  per_family=1)`, text-only tasks kept → 51 tasks, 16 domains (all text families incl. quality, contracts & claims,
  BIM), 18 easy / 26 medium / 7 hard. SHA-256 `70cbf07a690043581f2783d6df09e3920f33828d69388c872ca59c5ecaf8d50c`.
  Seed chosen after the harness was frozen at commit dec0233 (+ bench.sh manifest-filter fix); prompts were not
  read by anyone before the runs (only counts were printed). Planned for all models after the quick set.
- **Result — Haiku 5.5 and Sonnet 5.5, quick set, effort high** (same settings as Opus):
  | Model | Baseline | Harness | Cost base / harness | Mean output tok base / harness | s/task base / harness |
  |---|---|---|---|---|---|
  | Opus 5.5 | 41/41 | 41/41 | $0.620 / $0.693 | 677 / 355 | 6.6 / 9.8 |
  | Sonnet 5.5 | 41/41 | 41/41 | $0.243 / $0.319 | 515 / 289 | 3.8 / 4.0 |
  | Haiku 5.5 | 41/41 | 40/41 | $0.021 / $0.025 | 946 / 649 | 4.2 / 5.0 |
  Harness: every task answered through submit_answer except one Haiku task (40/41 submitted; the other ended by
  the ANSWER line); mean 1.0–1.2 code runs and 2.0–2.2 turns; no rejected submissions, no task-budget stops, no
  API errors in any run. Haiku price for cache reads assumed $0.01/MTok (not in the cached price table); effect on
  totals < $0.001.
- **Observed harness failure mode (Haiku, g703-0000, pay-application check):** the model identified the right two
  erroneous lines (items 4 and 6) and the right corrected total, but submitted `error_lines` as two explanatory
  sentences instead of line identifiers. The submit schema (array of strings, from the "Answer keys" line) cannot
  express "identifiers only", so a correct finding was graded wrong; the baseline Haiku run answered this task
  correctly. Not fixed — a change made after seeing a test result would be tuning on the test set; any fix must be
  frozen before the fresh-seed runs and reported as a harness revision.
- Interpretation so far: on seed-1 quick tasks all three current Claude models are at ceiling without tools; the
  harness reduces output tokens 30–50% and costs 12–31% more (larger input, extra turn), with no accuracy gain
  measurable at n = 41.
- Spend so far $1.921. Next: fresh seed (51 tasks), Haiku → Sonnet → Opus, both conditions, cap $2.55 for that
  folder (keeps the overall total ≤ $4.50).
- **Result — fresh seed 20261014 (51 text tasks, 16 domains, never inspected), effort high:**
  | Model | Baseline | Harness | Cost base / harness | Mean output tok base / harness | s/task base / harness |
  |---|---|---|---|---|---|
  | Opus 5.5 | 51/51 | 48/48 (3 not run, budget) | $0.882 / $0.859 | 758 / ~360 | 7.2 / 6.8 |
  | Sonnet 5.5 | 51/51 | 51/51 | $0.356 / $0.454 | 592 / 341 | 4.8 / 4.8 |
  | Haiku 5.5 | 51/51 | 50/51 | $0.031 / $0.039 | 1124 / 888 | 4.6 / 6.6 |
  95% Wilson CI for 51/51: 93.0–100%. Harness: mean 1.1–1.2 code runs, 2.1 turns; no rejected submissions,
  task-budget stops or API errors. Opus harness tasks not run: bim-cobie-0000, bim-name-0000, bim-5d-0000 (stopped by
  the budget cap; a top-up run completed bim-ifc-0000 correct at $0.050 — 13,176 input tokens because the IFC file
  text is preloaded into the tool description and the prompt).
- **The Haiku failure mode replicated on the fresh seed:** g703-0000 (pay application) again — correct line found
  (item 2), correct corrected total, but `error_lines` submitted as an explanatory sentence instead of the line
  identifier. 2/2 Haiku harness misses across both sets are this same failure; 0 baseline misses. Systematic, not
  noise: the free-form string array in the submit schema invites prose where the grader expects identifiers.
- Budget accounting: the run cap stopped new tasks as designed; overshoot from tasks already in flight was $0.02
  (cap 2.55, spent 2.572). **Total Claude spend (client-side estimate): $4.54** (quick $1.921 + fresh $2.622).
  To be reconciled against the Console invoice.
- **Conclusions so far (Claude family):** (1) Both task sets are at ceiling for Opus/Sonnet/Haiku 5.5 without
  tools (92/92 baseline tasks correct for each of the three models across both sets); accuracy differences
  between conditions are not measurable here. (2) The harness halves output tokens for Opus/Sonnet (−40 to −53%)
  and trims Haiku's (−21 to −31%), but raises cost 12–31% except Opus on the fresh set (−3%), because tool
  descriptions and the extra turn add input. (3) The only accuracy change caused by the harness is negative and
  systematic (Haiku, identifier lists). (4) To study accuracy effects the benchmark needs harder items or weaker
  models — open-weight runs (LM Studio, needs a restart) and DeepSeek are next.

### 2026-10-14 — expert tier (harder tasks)
- Motivation: ceiling effect on quick/fresh sets for all Claude 5.5 models (above).
- **Design** (commit 0a3a172, frozen before any model saw it): 7 new families, difficulty `expert`, in
  `constructbench/generators/expert.py`. Each combines volume, several interacting stated conventions and a trap from
  real documents:
  | Family | Domain | Size | Conventions / traps |
  |---|---|---|---|
  | pdm_calendar | scheduling | 24–32 activities | FS/SS/FF with lags; working-day calendar with 4–7 holidays; answers as dates |
  | pay_app_certification | finance | 22–30 SOV lines | planted G/H arithmetic errors; pending CO billed anyway (excluded); retainage 10% → 5% on D+E above 50% complete, 10% on stored |
  | wip_portfolio | finance | 14–20 jobs | cost-to-cost POC; over/under billing not netted; full loss provision; 2 prior-year closed jobs to exclude |
  | cost_ledger | finance | 110–155 CSV rows | other jobs; post-cut-off rows; duplicate entries; VOIDs cancelling invoices; credit memos; vs budgets |
  | mass_haul | civil | 21–31 stations | average end area; shrinkage; mass-haul ordinates; balance in bcy |
  | delay_tia | contracts | 6–9 events | day-level concurrency of owner/contractor/weather; 21-day notice bar; non-critical events; LDs |
  | bid_leveling_expert | preconstruction | 5 bidders × 12 items | amount in words governs figures (1–2 bidders mis-typed); plugs; allowances; bond on subtotal; accepted alternate |
  Ambiguous draws (ties, a value on a threshold) are redrawn from the same rng, so seeds stay reproducible.
- **Validation:** `tests/test_expert.py` re-derives every answer from the prompt text alone with separately written
  parsing/computation (seeds 1–3 × 8 per family): all agree. Also: oracle 100%, all answer keys readable by the
  harness, both retainage branches occur (≈65/35), the "lowest figures ≠ low bidder" trap occurs, every ledger has
  duplicates. One coverage bug found and fixed before freezing (pay apps were always > 50% complete).
- Only seeds 1–3 were inspected while building. **Evaluation set:** `data/expert-s20261015.jsonl` =
  `registry.build(seed=20261015, per_family=4)` over the 7 families → 28 tasks (scheduling 4, finance 12, civil 4,
  contracts 4, preconstruction 4); prompts 102,570 characters in total. SHA-256
  `35815916f558fb9b62153a6c7c8189a865bf1e7fc3d55d0b2b38d722d9e54849`. Not read before runs.
- Plan: Haiku 5.5 pilot both conditions now (remaining Claude budget ≈ $0.46; folder cap $0.30 keeps the overall
  total ≤ $4.85). Opus/Sonnet on this set need a budget top-up. Open-weight models when LM Studio is restarted.
- **Result — Haiku 5.5, expert set (28 tasks), effort high:**
  | Condition | Strict | Field | Cost | Mean output tok | s/task |
  |---|---|---|---|---|---|
  | baseline | 26/28 (92.9%, CI 77.4–98.0%) | 95.7% | $0.088 | 5,877 | 21.3 |
  | harness | 28/28 (100%, CI 87.9–100%) | 100% | $0.053 | 2,305 | 13.2 |
  Harness: 1.5 code runs, 2.5 turns per task; all 28 submitted via tool; no task-budget stops.
  **First accuracy separation between conditions** (paired: harness right on both baseline misses, wrong on none).
  Too small for significance (exact McNemar on 2 discordant pairs: p = 0.5) — a pilot result only.
  Baseline misses: (1) x-ledger-0001 — 4 of 5 fields right; total cost to date $1,273,264.97 vs $1,301,188.59
  (summing ~100 ledger rows by hand); (2) x-wip-0003 — stop_reason max_tokens: the 16,000-token reply limit was
  exhausted before an answer (17-job WIP by hand). The second is partly a setting effect (max_tokens), report it
  as such. Here the harness was **cheaper** (−40%) and faster (−38%), unlike on the easy sets, because writing
  code replaced long hand calculation.
- Claude spend: expert folder $0.141; total ≈ $4.68 (client-side estimate).

### 2026-10-14 — study infrastructure for improvements 1, 2, 3, 4, 5, 7
- **Repeats** (commit 7d9a9e9): `run --repeats N`; rows carry `rep`; resumable per (task, rep).
- **Statistics** (`constructbench/stats.py`, `compare`): unit of analysis = task; with repeats a task's score is the
  share of its runs fully correct. Reported: mean per-task difference with percentile bootstrap 95% CI (10,000
  resamples over tasks, seed 0); two-sided sign-flip permutation p (exact up to 20 non-zero differences, else 20,000
  Monte Carlo draws, seed 0); exact McNemar p when every task ran once; accuracy per repeat (mean ± sd); total cost and
  cost per correct answer. Tested against known values (`tests/test_stats.py`).
- **Ablations / effort sweep:** `bench.sh` `CONDITIONS` = base (no tools), code (+code), submit (+submit), harness
  (+code+submit); `EFFORTS` = Claude effort levels (result files tagged `@low`/`@medium`); `REPEATS`.
- **Harder tasks — extreme tier** (commit ee5a968, frozen before any model run): 4 families, difficulty `extreme`:
  co_reconciliation (contracts; shuffled CO log with revisions, statuses, owner directive priced from T&M tickets,
  billing vs approved value), addendum_takeoff (estimating; 15–22 rooms in feet-inches, three overriding addenda incl.
  a deleted room, waste then package rounding, base less doors, sales tax), ledger_xl (finance; 280–400 rows, three
  jobs, duplicates, voids, credit memos, reclass journals), cashflow_forecast (finance; schedule-spread costs, payment
  split, markup, retainage, payment lag, retainage release). `tests/test_extreme.py` re-derives every answer from the
  prompt text (seeds 1–3 × 6): all agree (one test-side parsing bug fixed; no generator change needed).
- **Larger evaluation sets:**
  - `data/expert84-s20261015.jsonl`: 12 per expert family = 84 tasks (scheduling 12, finance 36, civil 12,
    contracts 12, preconstruction 12), 310,219 prompt characters, SHA-256
    `01d27f698b405d2bc9d0d55950abeccdc902a2a110783fd0aff1903d9fc9d803`. Contains the 28-task pilot set exactly
    (verified byte for byte), so pilot runs carry over. Caveat: the reference answers of the two pilot misses
    (x-ledger-0001, x-wip-0003) were read during error analysis.
  - `data/extreme-s20261016.jsonl`: 8 per extreme family = 32 tasks (contracts 8, estimating 8, finance 16),
    264,512 characters, SHA-256 `e17c8226c0f2c478fe16aeb2ed227ffdea201c0c5358dc82a67dd7dc202b0b1d`. Not read.
  - `data/extreme-smoke.jsonl`: the first task of each extreme family (4 tasks, a subset of the 32) for a smoke test.
- **Smoke test — Haiku 5.5, extreme-smoke (4 tasks), effort high:** baseline 4/4, harness 4/4; cost $0.0163 vs
  $0.0097; mean output tokens 7,245 vs 2,461; 26.4 vs 15.3 s/run. No errors, no budget stops. These 4 tasks are now
  seen (results only; prompts not read).
- Claude spend: ≈ $4.71 total (client-side estimate). Remaining budget ≈ $0.29 — **the study below is not run.**

### Pre-registered plan for the full study (written before any of these runs)
- **Tasks:** expert84 + extreme32 = 116 tasks.
- **Primary outcome:** per-task strict accuracy, harness (+code+submit) minus baseline, paired by task; report the
  mean difference with bootstrap 95% CI and sign-flip p; per tier (expert, extreme) and pooled.
- **Secondary:** cost per correct answer, total cost, output tokens, seconds per run; field score; failure categories
  (wrong arithmetic, unparsed answer, max_tokens, task-budget stop, format/identifier errors).
- **Arms and estimated cost** (from measured per-run costs: Haiku ≈ $0.003/run on these tiers; Sonnet ≈ 12× and Opus
  ≈ 30× Haiku, ratios measured on the quick set):
  | Arm | Model | Conditions | Effort | Repeats | Runs | Est. cost |
  |---|---|---|---|---|---|---|
  | A main + ablation | Haiku 5.5 | base, code, submit, harness | high | 3 | 1,392 | ≈ $4–5 |
  | B effort sweep | Haiku 5.5 | base, harness | low, medium | 1 | 464 | ≈ $1 |
  | C | Sonnet 5.5 | base, harness | high | 1 | 232 | ≈ $8 |
  | D | Opus 5.5 | base, harness | high | 1 | 232 | ≈ $20 |
  | E | Qwen2.5-1.5B, Qwen3-4B (LM Studio) | all four | — (temperature 0) | 1 | 928 | $0 (slow: Qwen3-4B ≈ minutes/task) |
  | F | DeepSeek (API) | base, harness | — | 1 | 232 | < $1 |
- **Commands:**
  `TASKS=data/expert84-s20261015.jsonl CONDITIONS="base code submit harness" REPEATS=3 BUDGET=… scripts/bench.sh anthropic:claude-haiku-5-5`
  (and the same with `TASKS=data/extreme-s20261016.jsonl`); arm B adds `EFFORTS="low medium" CONDITIONS="base harness"`;
  arms C/D `scripts/bench.sh anthropic:claude-sonnet-5-5` / `anthropic:claude-opus-5-5`; comparisons with
  `python -m constructbench compare <harness file> <base file> --tasks <set>`.
- **Decision rules fixed in advance:** no harness or task changes between arms; any harness revision (e.g. the
  identifier-list fix) is a new labelled version run on all arms; budget-stopped tasks are reported as not run.
