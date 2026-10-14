#!/usr/bin/env bash
# Runs ConstructBench for one or more models, each WITHOUT and WITH the harness (+code+submit), then the leaderboard.
#
#   scripts/bench.sh anthropic:claude-opus-5-5 anthropic:claude-sonnet-5-5
#   scripts/bench.sh api:deepseek-chat@https://api.deepseek.com/v1
#   scripts/bench.sh local:qwen3-4b-instruct-2507              # LM Studio
#   TASKS=data/dev.jsonl ONLY=harness scripts/bench.sh ...      # ONLY=base|harness to run one side
#   BUDGET=4.50 TASK_BUDGET=0.30 LIMIT=2 scripts/bench.sh anthropic:claude-opus-5-5
#     BUDGET: USD hard stop shared by every Claude result file in the output folder (stops starting tasks)
#     TASK_BUDGET: USD cap per harness task;  LIMIT: only the first N tasks (a smoke test)
#
# Keys live in ~/.config/constructbench/keys.env (chmod 600, outside the repo) — never in this repo.
# Re-running is safe: finished tasks are skipped, API failures (rate limits, outages) are retried.
set -euo pipefail
cd "$(dirname "$0")/.."

KEYS="${KEYS:-$HOME/.config/constructbench/keys.env}"
[ -f "$KEYS" ] && source "$KEYS"
PY="${PY:-.venv313/bin/python}"
[ -x "$PY" ] || PY=python3
TASKS="${TASKS:-data/quick-families.jsonl}"
WORKERS="${WORKERS:-4}"
EFFORT="${EFFORT:-high}"
ONLY="${ONLY:-both}"
OUT="results/$(basename "$TASKS" .jsonl)"
mkdir -p "$OUT"
if [ -n "${LIMIT:-}" ]; then
  head -n "$LIMIT" "$TASKS" > "$OUT/.limit.jsonl"; TASKS="$OUT/.limit.jsonl"
fi
shopt -s nullglob
money() {  # re-globbed before every run, so files written earlier in this script count against BUDGET
  [ -n "${BUDGET:-}" ] && printf '%s\n' --budget "$BUDGET" --budget-files "$OUT"/anthropic*.jsonl
  [ -n "${TASK_BUDGET:-}" ] && printf '%s\n' --task-budget "$TASK_BUDGET"
  true
}

[ $# -gt 0 ] || { sed -n '2,10p' "$0"; exit 1; }

slug() { echo "$1" | sed -E 's#@https?://[^+]*##; s#[^A-Za-z0-9.+-]+#_#g'; }

for spec in "$@"; do
  sides=()
  [ "$ONLY" != harness ] && sides+=("$spec")
  [ "$ONLY" != base ] && sides+=("$(echo "$spec" | sed -E 's/(\+code|\+submit)//g')+code+submit")
  for s in "${sides[@]}"; do
    file="$OUT/$(slug "$s").jsonl"
    echo "== $s -> $file"
    m=(); while IFS= read -r x; do m+=("$x"); done < <(money)
    "$PY" -m constructbench run --tasks "$TASKS" --provider "$s" --out "$file" --workers "$WORKERS" --effort "$EFFORT" ${m[@]+"${m[@]}"}
    "$PY" -m constructbench score "$file" --tasks "$TASKS" | head -1
  done
done

"$PY" -m constructbench leaderboard "$OUT"/*.jsonl --tasks "$TASKS" --out "$OUT/LEADERBOARD.md" >/dev/null
echo "leaderboard: $OUT/LEADERBOARD.md"
