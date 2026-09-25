# ConstructBench

A benchmark of AI models on construction work — the calculations, checks and readings people in the
industry do every day — scored per domain so a result says *where* a model is strong or weak.

| Domain | What it tests |
|---|---|
| Architecture | Occupant load & egress, stair geometry, zoning floor area (rules given in the prompt) |
| Design & engineering | Beam moment/shear/deflection, 3-phase load & breaker, duct velocity |
| Estimating | Quantity takeoff, unit-rate estimates, change-order pricing with markups |
| Preconstruction | Bid leveling with scope gaps, the bid-day number |
| Scheduling | Critical path, total & free float, delay impact on the finish, 3-week look-ahead, schedule quality checks |
| Project management | Earned value, labor productivity, RFI log aging |
| Cost control & finance | WIP / over-under billing, retainage & payment due, 13-week cash flow |
| Document recognition | Invoice / delivery ticket / lien waiver extraction, G703 error-finding |
| Visual intelligence | Rendered floor plans (areas), plan symbol counts, Gantt chart reading — as images |
| Safety | Incident rates (TRIR/DART/LTIR), fall clearance, trench protection — plus rendered drawings: ladder setup (4:1, 3 ft extension), workers inside a crane swing radius, guardrail heights |
| Robotics | Robot path planning on a rendered occupancy map, layout-robot coordinate transforms, arm kinematics & reach, drone survey flight plans, rebar-tying and bricklaying robots vs crews |

## How it works

- **Generated, not written.** Every task comes from a seeded generator; the answer is computed by the same
  code from the same numbers (and images are drawn from them), so references are right by construction and a
  new seed gives a fresh, unseen set. Publish on a dev seed; keep a private seed for held-out scoring.
- **Strict grading.** Models end with `ANSWER: {json}`. Each field is graded (numeric tolerances, sets, dates);
  a task is correct only when every field is. Field-level partial credit is reported alongside.
- **Honest error bars.** Accuracy is reported with a 95% Wilson interval, per domain and per difficulty, with mean time per task.
- **No dependencies** for generating and scoring (Python 3.10+ stdlib). `pip install anthropic` only to run Claude.

## Use

```bash
python -m constructbench generate --seed 1 --per-family 10 --out data/dev.jsonl
python -m constructbench run --tasks data/dev.jsonl --provider anthropic:claude-opus-5 --out results/opus-5.jsonl
python -m constructbench run --tasks data/dev.jsonl --provider local:qwen2.5-7b-instruct --out results/ours.jsonl   # LM Studio
python -m constructbench run --tasks data/dev.jsonl --provider local:qwen2.5:7b-instruct@http://127.0.0.1:11434/v1 --out results/ours.jsonl  # Ollama
python -m constructbench compare results/ours.jsonl results/opus-5.jsonl --tasks data/dev.jsonl --out results/COMPARE.md
python -m constructbench leaderboard results/*.jsonl --tasks data/dev.jsonl --out results/LEADERBOARD.md
python -m constructbench show data/dev.jsonl vis-plan-0000 --save-images out/
python -m unittest discover -s tests
```

Providers: `anthropic:<model>` (official SDK, adaptive thinking, `--effort`), `local:<model>[@url][+images]` (any OpenAI-compatible local server — how the Constructelligence assistant's open model is served), `command:<cmd>` (any model via
stdin/stdout; text only, so image tasks are skipped), `oracle` (must score 100%), `blank` (0%).
Claude runs record refusals as refusals — no fallback model, so the score is the named model's.
Runs are resumable and store raw responses, so a grader fix re-scores without re-running.

## Add a task family

Write `fn(rng, i) -> Task` in `constructbench/generators/`, compute the answer in code, state every
convention in the prompt (so there is exactly one right answer), and register it in `registry.FAMILIES`.
The tests check the oracle scores 100% on it.
