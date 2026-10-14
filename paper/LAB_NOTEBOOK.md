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
