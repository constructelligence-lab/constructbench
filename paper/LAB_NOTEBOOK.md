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

### 2026-10-14 (later) — hidden rules, chained tasks, report, DeepSeek
- **DeepSeek:** the key the user supplied returns `401 Authentication Fails … invalid` on `GET /models` (a valid key
  without credit returns 402 instead). No DeepSeek run. OpenAI-compatible runs now record the server's raw usage
  totals (cache hits, reasoning tokens) per run so cost can be computed afterwards from the provider's price list
  (commit 536c6c2).
- **Hidden-rule families** (commit ebf33e1, frozen before any model run), difficulty `extreme`:
  - pay_app_contract: the prompt says only "under the payment terms of the subcontract below"; the deciding terms are
    in a numbered excerpt among 4–6 distractor clauses (insurance limits, 150% dispute withholding, termination 5%…).
    Per-task variants: retainage scheme (10%→5% step at 50% / flat 5% incl. stored / 10% on work, none on stored) ×
    stored materials (all payable / off site only if bonded and approved). Unsigned PCO lines excluded per §9.2.
  - delay_contract: notice period (7/10/14/21 days), concurrency (excusable-not-compensable vs contractor bears),
    weather excusable only beyond Exhibit W's anticipated days per month, extended GC compensation per owner-only day,
    LD per day with a cap of 0.5/1/2/5% of the Contract Sum (cap binds in ≈36% of tasks; range tightened before
    freezing because at 3–10% it bound in only ≈2.5%).
  - Validation reads the rules out of the excerpt text (the test never sees the variant): all answers agree; all three
    retainage schemes and all four concurrency × cap-binding combinations occur.
- **Chained family** chained_concrete: takeoff (slab, footings, pads, waste, half-yard ordering) → direct cost
  (concrete, rebar, formwork contact area, crew) → bid (GC, OH, profit, bond compounded) → duration (forms, pours at
  CY/day rounded up, cure, strip) → cash flow (20-day months, retainage, one-month pay lag) → peak deficit.
  `chain_values(params, overrides)` recomputes downstream stages from a model's own upstream answers, for error-
  propagation analysis (first error vs carried error). Rounding knife-edges redrawn.
- **Evaluation set:** `data/rules-chain-s20261017.jsonl`, 8 per family = 24 tasks, SHA-256
  `7d09e40573b06056daf18399958574f89c9ac011ccec4f3aec41f3a6babbfd44`. Not read.
- **Report command** (`python -m constructbench report`, `constructbench/report.py`): from every results folder
  writes `paper/report/` — report.md, runs.csv, paired.csv, failures.csv and SVG figures (accuracy by model × condition
  with Wilson CIs per set; accuracy vs prompt-length bins per model; failure categories; cost per task vs accuracy with
  the non-dominated frontier). Figures follow the dataviz method: categorical palette validated with
  validate_palette.js (4 condition colours: all checks pass; contrast relief via value labels + tables), legends +
  direct labels, `<title>` hover text per mark; rendered and inspected (label collisions, clipped labels, misleading
  rounded tick labels found and fixed). Failure classifier categories, in priority: prose in an ID list, numeric error
  > 1%, wrong non-numeric value, numeric near miss ≤ 1%, out of tokens, unparseable, task-budget stop, refusal, API
  error. On existing results it reproduces the hand analysis exactly (2 × prose-in-ID-list for Haiku harness;
  1 numeric error + 1 out-of-tokens for Haiku baseline on expert).
- Added to the pre-registered plan: rules-chain (24 tasks) joins expert84 + extreme32 → 140 tasks; Haiku arm A
  ≈ $5–6 at the measured per-run cost. Chained-task secondary outcome: share of downstream errors that are carried
  (correct given the model's own upstream value) vs new.

### 2026-10-14 — DeepSeek
- The same DeepSeek key, re-sent, now authenticates (likely activation delay; first attempt 401). Balance $0.47
  (topped up, no granted credit). `GET /models` lists `deepseek-flash` (DeepSeek-V4.1-Flash; 1M context, 393k max
  output, effort low/high/max, default high, text+image input) and `deepseek-v4-pro` (DeepSeek-V4-Pro; same limits,
  text only). The API returns no prices: **cost is measured as the account-balance difference**
  (`scripts/deepseek-balance.sh`, 2-decimal resolution; `results/deepseek-balance.log`) and token usage is stored per
  run (cache hit/miss and reasoning tokens).
- Settings: OpenAI-compatible `/chat/completions`, temperature 0 (sent; thinking models may ignore it), server-default
  effort (high), max 32,000 output tokens per reply (`MAX_TOKENS`), same `Toolbox` harness via function calling
  (schema checked client-side; a malformed submission is returned once).
- Smoke test (quick set, task arch-far-0000): both models correct in both conditions; harness path ran 1 code call and
  submitted via tool; reasoning content echoed back between tool turns without error; balance unchanged ($0.47) at
  2-decimal resolution for 4 runs (≈ 7k tokens).
- Run plan for the $0.47: DeepSeek Flash on expert84 (both conditions) first; balance read after each chunk; then
  extreme32 and rules-chain24; then Pro as balance allows. When the balance runs out the API refuses (HTTP 402); those
  runs are stored as failures and re-run on resume — never scored as wrong.

### 2026-10-14 (later still) — DeepSeek Flash on expert84, both conditions — *times below are machine local (EDT)*
- **Scope: Flash only.** `deepseek-v4-pro` is explicitly deferred at the user's instruction — no Pro results exist.
  Set `data/expert84-s20261015.jsonl` (84 expert tasks), settings unchanged from the smoke test: OpenAI-compatible,
  temperature 0, server-default effort, `MAX_TOKENS=32000`, workers 4.
- **The 08:47 chunk was interrupted, not refused:** the log stops at `[35/84]` with no summary, no process, and no
  `402`/`ok:false` rows. **Its cost is unmeasured** — the "after" balance read was never taken, so only the account
  balance delta of the resume chunks is known. Recorded as a gap, not estimated.
- **Resume, no harness (09:57, 49 to run, 35 already done — finished tasks are skipped):** balance 4.95 → 4.68 =
  **$0.27 for 49 runs ≈ $0.0055/run**, ~25 min.
- **Harness (`+code+submit`) (10:00–10:13, 84 runs):** balance 4.68 → 4.32 = **$0.36 for 84 runs ≈ $0.0043/run**,
  ~13 min. Session spend $0.63; balance left 4.32.
- **Results:** no harness **78/84 = 92.9%** (95% CI 85.3–96.7), field 92.9%; harness **82/84 = 97.6%**
  (91.7–99.3), field 99.0%. Paired by task: **+4.8 pts**, bootstrap 95% CI −1.2 to +11.9, sign-flip p = 0.2891,
  exact McNemar p = 0.2891; harness better on **6** tasks and worse on **2**. **Not significant** at n = 84. The
  direction reproduces the 28-task Haiku 5.5 pilot, whose baseline had already broken the ceiling (26/28 = 92.9% →
  28/28 = 100%), and DeepSeek's baseline lands on the *same* 92.9% over the full 84. The pilot's 28 items are a strict
  subset of these 84 (checked), so the Haiku pilot runs carry over — but there are no Haiku runs on the other 56 items,
  so the pooled cross-model comparison on the full set is not available yet.
- **The two failure modes are different in kind.** No harness: every failure is in `wip_portfolio` (6/12) — **5
  out-of-tokens** (32,000 output tokens consumed by reasoning, empty reply → unparsed) and **1** stop with prose and no
  `ANSWER:` line (`x-wip-0003` — also one of Haiku 5.5's two pilot misses, and one the DeepSeek harness then got right,
  so it is a shared without-a-harness trap rather than a model-specific one). Harness: **zero** format/length failures
  and all six wip tasks correct, but **2 substantive misses** on `mass_haul` (`x-haul-0000`, `x-haul-0005`, 3/5 fields):
  the mass-diagram maximum ordinate's value *and* station are wrong while the cut/fill/net totals are right. Net effect
  of the harness here is to trade a length/format failure mode for a small number of reasoning errors — consistent with
  (3) of the Claude conclusions, which found the harness's only accuracy *change* was negative.
- **Efficiency (the clearest effect):** harness cuts mean output tokens **13,960 → 6,069 (−57%)** and mean run time
  **60.6 s → 33.6 s (−45%)**, reproducing the Claude-family output-token result at a much larger scale. For scale,
  Haiku 5.5 on the same tier (28-task pilot) ran **5,877 → 2,305** tokens/task, so DeepSeek spends ~2.4× Haiku's
  baseline on the same items, and the harness cuts both models by a similar ~60%.
- **Caveats for the write-up.** (1) The 32k ceiling is *our setting*, not a model limit (DeepSeek advertises 393,216
  max output), so 5 tasks are scored as failures at a cap we chose; a labelled higher-`MAX_TOKENS` rerun would test
  whether they are really beyond the model. (2) `--effort` is never sent for `api:` providers (the manifest records
  `effort: null` → server default *high*), so this arm is **not** effort-controlled. (3) DeepSeek publishes no prices
  and `providers.PRICES` has no DeepSeek entry, so rows carry no `cost_usd`: `report`, `compare` and `--budget` all
  show "—", DeepSeek cost is only ever the balance delta, and `--budget` must **not** be set for these runs (with no
  price seen, `runner.affordable()` serialises the run to one worker and never stops).
- **Artifacts:** `results/expert84-s20261015/{api_deepseek-flash,api_deepseek-flash+code+submit}.jsonl`, logs
  `results/deepseek-flash-expert84-{resume,harness}.log`, `results/deepseek-balance.log`; `paper/report/` regenerated
  (new row pair for `expert84-s20261015` and `fig_accuracy_expert84-s20261015.svg`). 130 unit tests pass.
- **Status vs. the pre-registered plan:** arm F is **half done** — Flash on expert84 complete in both conditions;
  `extreme32` and `rules-chain24` not run; Pro deferred. Remaining balance 4.32 covers them.
- **Other models (surveyed, none run):** nothing else is reachable without new credentials — `OPENROUTER_API_KEY`
  exists in `keys.env` but is commented out (uncommenting unlocks a large OpenAI-compatible catalogue), the other
  `KEY_ENV` hosts (OpenAI, Together, Groq, Fireworks, Gemini, Mistral) have no keys, and the local arm needs
  `lms server start` (LM Studio is installed with Qwen2.5-1.5B and Qwen3-4B on disk but its server is **off**;
  measured ~minutes/task, so the full expert84 set would take ~a day).

### 2026-10-14 (later still) — Haiku 5.5 on expert84, both conditions — the paired effect the study was missing
- **Why this run:** the expert tier is the only place in the study where the baseline is not at ceiling, so it is the
  only place a harness effect can be measured. The full 84-task set was run for Haiku 5.5, the cheapest arm.
- **Budget position first:** total Claude spend before this run was **$4.7099** of the $5.00 study cap (summed from
  every `anthropic_*.jsonl` `response.extra.cost_usd`), i.e. **$0.29 left**.
- **How 112 runs fit in $0.29 — the pilot rows carry over.** The 28-task pilot's items are a verified *subset* of these
  84 and the pilot ran under identical settings (Haiku 5.5, effort high, 16,000 max tokens, adaptive thinking,
  `--task-budget 0.05`, the same harness words). So the 28 pilot rows per condition were **copied into the 84-set
  result files** instead of re-run, leaving 56+56. Stated explicitly because those two files now hold rows from two
  invocations — the run manifests beside them carry only this run's command and task-set hash.
- **Commands** (direct CLI rather than `bench.sh`: `bench.sh`'s `BUDGET` counts every Claude file in the output folder,
  so after the base leg the harness leg would have been blocked before its first task):
  base `--provider anthropic:claude-haiku-5-5 --budget 0.30 --task-budget 0.05`, harness the same with
  `+code+submit` and `--budget 0.156` (sized to the remaining study allowance).
- **Results:** no harness **77/84 = 91.7%** (95% CI 83.8–95.9), field 95.1%, $0.2748*, 6,142 tok, 22.3 s; harness
  **82/82 = 100%** (95.5–100), field 100%, $0.1548, 2,280 tok, 12.0 s. *(*includes the carried-over rows.)*
- **Paired on the 82 tasks answered by both: 92.7% → 100.0%, +7.3 pts (bootstrap 95% CI +2.4 to +13.4), sign-flip
  p = 0.03125, exact McNemar p = 0.03125 — the study's first *significant* harness effect, and in the harness's
  favour, with 6 tasks better and none worse.** (The pilot's own 26/28 → 28/28 was a 2-discordant-pair result,
  p = 0.5.)
- **The budget stop is honest, not hidden:** the harness leg reached the $5 cap after $0.15; `x-level-0010` and
  `x-level-0011` are **not run** and are reported as not run, per the pre-registered rule. The harness figure is
  therefore on 82 tasks, and the paired analysis uses the 82 common ones. Re-running either file resumes it.
- **Failure profiles differ by model, and the harness removes them all.** Haiku baseline: **4 numeric errors (>1%) +
  3 out-of-tokens**. DeepSeek baseline: **0 numeric errors**, 5 out-of-tokens + 1 unparseable. So DeepSeek computes
  more reliably but spends ~2.3× the tokens and runs into the ceiling; Haiku computes a little worse but finishes.
  The harness removes **all 7** of Haiku's failures and all 6 of DeepSeek's — but adds **2** fresh numeric errors for
  DeepSeek. Only Haiku's harness effect is clean and significant.
- **Head-to-head on the same tasks:** no harness 91.7% (Haiku) vs 92.9% (DeepSeek) — a tie inside the noise;
  with the harness **100.0% (Haiku) vs 97.6% (DeepSeek)**. The cheaper model is the one that ends up perfect.
- **Efficiency — and this is the opposite of the Claude finding on quick/fresh:** the harness cuts Haiku's output
  tokens **6,142 → 2,280 (−63%)** and time **22.3 → 12.0 s**, so **cost per correct answer falls, $0.0036 → $0.0019**.
  On quick/fresh the harness raised cost 12–31%; on the expert tier it halves it. (There, the tasks were short enough
  that tool descriptions dominated the bill; here the baseline's own reasoning dominates.)
- **Spend after: true study spend ≈ $4.9986 of $5.00 — the cap is reached.** ⚠️ **A naive sum over every
  `anthropic_*.jsonl` now reads $5.1395 and must not be read as overspend:** the 28 carried-over rows are counted once
  in the pilot files (`results/expert-s20261015/`) and again in the 84-set files. Reconcile by subtracting the
  duplicate pair — $0.0878 + $0.0531 = **$0.1409** — which is exactly the work the carry-over avoided paying for twice.
  Further Claude arms (Sonnet, Opus, repeats, the effort sweep) need a new budget decision before they can run.
- 130 unit tests pass; `paper/report/` regenerated (Haiku expert84 rows with cost, and the new paired row).

### 2026-10-15 — Reporting policy: completion, format compliance and strict accuracy are now published separately
Found while running the OpenRouter arms, where two ways a single accuracy number misleads both showed up in one session.
- **An API failure was being counted as a wrong answer.** When the OpenRouter balance ran out mid-run, 208 rows were
  stored with `ok=false` (HTTP 402). `summarize()` divided by *every* row, so ling's harness read 35/84 = 41.7% when the
  truth on the answers actually received was 35/36 = 97.2%, and gpt-oss-120b read a meaningless 0.0%. Fixed: a call that
  produced no answer at all is **`not_run`** — excluded from accuracy and reported as its own number, which is what the
  pre-registration always said. A refusal still counts (a refusal *is* an answer). `stats.paired()` drops the same rows
  per side, so a paired test can no longer be poisoned by one side's credit failure.
- **Format compliance was invisible.** gpt-oss-120b wrote the *correct* values for `x-pdm-0000` as bare JSON with no
  `ANSWER:` line and scored **0**. A benchmark that scores serialisation as competence is measuring formatting.
  `score --lenient` now reports, *beside* the strict score and never instead, what the score would be if the `ANSWER:`
  line were not required (fenced JSON, else the first balanced object). It recovers exactly that task: `+1 recovered`.
  Supporting number: ling's baseline **format compliance is 52.4%** — its 40.5% baseline was mostly *failing to answer
  at all*, not answering wrongly, which the old single number hid completely.
- **Published per run now:** strict accuracy (of answers received) · partial credit (mean field score) · completion
  (answered/attempted) · format compliance (parsed/answered). The leaderboard carries all four as columns; the domain
  columns stay strict accuracy. Cost per correct answer stays as before.
- **New `calibrate` subcommand** — per-item pass rate across every run given, flagging items every run passes or fails.
  On expert84 over 8 result files: **informativeness (mean p(1−p)) = 0.111** against 0.25 ideal, with **29 of 84 items
  passed by every run** (35%) and none failed by all. Those 29 carry no information for a frontier comparison and are
  the first candidates to retire or re-seed before this set is published as a standard. This is the measurement that
  had been missing: the set is too easy at the top, which is why a +4.8 pt effect could not reach significance.
- **No published number moved.** Re-scored after the change: haiku base 91.7%, haiku harness 100.0%, deepseek base
  92.9%, deepseek harness 97.6% — identical, because no earlier run had API failures to exclude. `paper/report/`
  regenerates unchanged.
- Also in this pass, aimed at international coverage (the benchmark is US-customary throughout): toolkit gains
  `convert()` / `convert_temp()` / `unit_dimension()` — metric↔US across length, area, volume, mass, force, stress,
  flow, velocity, power and energy, tolerant of how the unit is written (`'sq ft'`, `'sf'`, `'ft²'`, `'CY'`, `'cu yd'`,
  `'m/s'`), refusing cross-dimension conversions and routing temperature to the right helper. The quantity-units card
  now carries the metric equivalents (1 m³ = 1.30795 yd³, 1 MPa = 145.038 psi, …) and the rule to convert everything
  to one system *before* the arithmetic. 156 unit tests pass (was 144).

### 2026-10-15 (later) — `calibrate` found the ceiling; the first harder family is in
- **Where the dead weight is.** `calibrate` over expert84 and 8 result files: informativeness (mean p(1−p)) **0.111**
  against 0.25 ideal, **29 of 84 items passed by every run**. By family: `pay_app_certification` **11/12**,
  `delay_tia` **9/12**, `bid_leveling_expert` **8/12**, `mass_haul` 1/12, and `pdm_calendar` / `wip_portfolio` /
  `cost_ledger` 0. Those three families carry 28 of the 29 dead items; the other four already discriminate.
- **Cause, not just the count.** The three easy families state every rule explicitly and need one well-formed loop
  (find the arithmetic errors, drop the pending lines, apply the retainage step). Nothing *interacts*, so a model with
  a calculator cannot fail. Difficulty in this benchmark must come from interacting conventions, not volume.
- **Fix, started: a second level per family.** Registered as its own family so the frozen first level is untouched
  (`pay_app_certification_hard`, `registry.FAMILIES`). Three rules that interact: (3) stored materials whose Stored OK
  is N are excluded from *every* total while the printed G still contains them — so the arithmetic-error rule never
  flags them; (2+6) pending change orders whose billings are already inside the previous-certificates figure, so the
  exclusion rule only completes with the adjustment rule; (4) an approved deductive change order with a **negative**
  scheduled value that must be carried with its sign into the contract sum and therefore into the percent complete and
  the 50% retainage knife-edge. **Seven answer fields instead of five**, so missing one rule costs fields rather than
  the item — which the new partial-credit column now reports.
- **Verified three ways.** Oracle 100% across seeds (the suite's per-family sweep); the independent re-derivation test
  in `tests/test_expert.py` extended so all seven fields are recomputed from the prompt text by code written separately
  from the generator (this is the "second implementation" a standard needs, not a restatement of the generator);
  determinism and keys-in-prompt unchanged. **157 tests pass.** Mean prompt 5.2k chars vs 3.7k.
- **Measured effect on discriminating power.** ling-3.0-flash, base condition: first level **11/12 = 91.7%** (all-pass)
  → second level **4/12 = 33.3%** (95% CI 13.8–60.9; partial credit 59.5%; format compliance 75.0%). **A 58-point fall
  on the cheapest model in the study**, on items that previously separated nobody. The partial-credit figure is the
  tell that the design works: models are getting *some* fields (59.5%) while failing the item — the traps are
  interacting, not just harder to read.
- Set used for the check: `data/hard-smoke-s20261021.jsonl` (12 items, seed 20261021); both conditions cost ~$0.02.
- **Next:** the same second level for `delay_tia` (9/12 all-pass) and `bid_leveling_expert` (8/12), then a v2 tier =
  second levels for those three + the four families that already discriminate, re-calibrated *before* publication so
  the informativeness figure of the published set is a measured number rather than a hope.

### 2026-10-15 (later still) — the other two ceiling families get a second level
- **`delay_tia_hard`** — four interacting rules on top of the plain one: a **per-month weather allowance** (a
  weather-only day is excusable only after that month's anticipated days are used up, so the day table can no longer
  be read in one pass), **two notice periods** (Owner 21 calendar days, Weather 10 — applying one period to both is
  the trap), and **two caps** (liquidated damages capped at a percentage of the contract sum, extended general
  conditions capped separately). The extension therefore moves the LD start date, which decides whether the cap
  binds. Fields 5 → 7 (`weather_days_not_excusable` joins the set so the allowance itself is scorable).
- **`bid_leveling_expert_hard`** — two mechanisms that each change the winner: a **non-responsive bid** (excludes a
  mandatory item and carries no allowance for it → rejected outright, never levelled) and a **correction that only
  applies when the form says so** (words govern over figures, but on a form marked "unit prices govern" whose line
  items total differs, the line-item total governs). Both the opposite mistakes are present in every item: a decoy
  form says "unit prices govern" while agreeing with its words, and a second bidder excludes a mandatory item *with*
  an allowance, which is responsive. Fields 3 → 5 (rejected bidders and the leveled spread join the top two).
- **Two bugs of my own, both caught by tests, both worth recording.**
  1. The first attempt *hunted* for the traps with conjunctive `Retry` guards. `test_generators`'s per-family sweep
     caught it at once: `bid_leveling_expert_hard: no unambiguous draw in 200 tries`. Sampling for a conjunction of
     three unlikely events is not a design.
  2. The independent re-derivation test then caught a genuine **design** flaw: the rejected bid was chosen from the
     naive ranking, but a model that ignores the rejection rule levels that bid *with the exclusion's plug added
     back in*, which can lift it out of first place — so the trap sometimes did not bite at all. The test asserted the
     trap must change the winner and failed, which is exactly what an independent reading of the prompt is for.
  Both are fixed by **constructing** the traps from the ranking a rule-ignoring model actually sees
  (`excluded_total()` tries the exclusion on each bidder and keeps the one that then levels lowest). Generation went
  from failing to instant (0.00 s for 10 items) and every item now provably carries both traps — asserted, not hoped.
- **159 tests pass** (was 157). Three second-level families exist — `pay_app_certification_hard`, `delay_tia_hard`,
  `bid_leveling_expert_hard` — and all three are re-derived field by field from their own prompt text by code written
  separately from the generator (`tests/test_expert.py`), which is the second implementation a benchmark needs before
  anyone else is asked to trust it.

### 2026-10-15 (later still) — autonomous robotics, and one escalation that failed
- **New domain coverage: autonomous operation** (the robotics domain had navigation, layout, kinematics, survey and
  productivity, but nothing that turns on *autonomy*). Two families, both `expert`:
  - **`fleet_allocation`** — dispatch 4 tasks across a 5-robot fleet minimising total distance, with a per-robot
    remaining range. The range trap is **constructed**, not sampled: the plan that ignores the range limit is found
    first and the range of the robot it leans on furthest is capped, so that plan is provably infeasible and rule 2
    must change the answer. The nearest-robot-first (greedy) dispatcher is also wrong on 6 of 10 items; that trap is
    recorded in `meta.greedy_trap` rather than required, because it cannot be constructed reliably. Fields:
    assignment, total distance, makespan, idle robots.
  - **`agv_safety_envelope`** — ISO 13855-style protective stop distance for an autonomous site vehicle
    (`S = K·T + v²/2a + C`), then the highest approach speed that still fits the scanner's zone. The deceleration is
    reduced by the stated payload, C is in millimetres against metres elsewhere, and rule 4 must be *solved* rather
    than scaled — and it depends on the answer to rule 2. Fields: stopping distance, payload-reduced deceleration,
    permitted, max permitted speed.
  Both are re-derived independently in `tests/test_robotics.py`. **161 tests pass** (was 159).
- **A design flaw I introduced and then measured: `bid_leveling_expert_hard` is not harder.** ling-3.0-flash, base:

  | family | first level | second level | Δ |
  |---|---|---|---|
  | `pay_app_certification` | 11/12 = 91.7% | **3/12 = 25.0%** | **−66.7** |
  | `delay_tia` | 10/12 = 83.3% | **5/12 = 41.7%** | **−41.7** |
  | `bid_leveling_expert` | 9/12 = 75.0% | 12/12 = 100.0% | **+25.0** |

  Two of the three second levels work exactly as intended (aggregate over the 36 items: 30/36 = 83.3% first level →
  the second level cuts it by roughly half, with partial credit well above strict accuracy, which is the signature of
  traps that cost fields rather than whole items). **The third is a genuine failure of my design**: adding the
  rejection rule and the unit-price correction made the item *more* structured, not harder — the rules are explicit
  and the traps are mechanical once read, whereas the first level's words-versus-figures trap is a reading trap that
  ling actually fails. n = 12 on one model, so treat the +25 as no better than flat, but there is no evidence the
  second level helps and one clear reason to think it hurts.
  **Action:** do not ship `bid_leveling_expert_hard` in a v2 tier until it is redesigned — the lever for that family is
  the *form* (handwriting-style ambiguity, an illegible figure, a bid needing a written clarification), not more rules.
  This is recorded rather than quietly dropped, because "we raised difficulty" is exactly the claim a benchmark
  maintainer must be able to prove per family, and `calibrate` is the tool that proves or refutes it.

### 2026-10-28 — first full manuscript draft
- Wrote `paper/PAPER.md` (abstract, benchmark, harness, design, results, methodological findings, threats, remaining work).
  Every number is copied from this notebook, `paper/report/report.md` and `results/hard3-s20261021/LEADERBOARD.md`; no new
  runs, no spend. Unmeasured items are marked **[TODO]** in the draft; the same list is its section 8.
- Not re-checked in this pass: the decontam figures (0/288, 5/5) come from project notes, not a fresh run.
