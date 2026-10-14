#!/usr/bin/env bash
# Runs ConstructBench for one or more models, each WITHOUT and WITH the harness (+code+submit), then the leaderboard.
#
#   scripts/bench.sh anthropic:claude-opus-5-5 anthropic:claude-sonnet-5-5
#   scripts/bench.sh api:deepseek-chat@https://api.deepseek.com/v1
#   scripts/bench.sh local:qwen3-4b-instruct-2507              # LM Studio
#   TASKS=data/dev.jsonl ONLY=harness scripts/bench.sh ...      # ONLY=base|harness to run one side
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

[ $# -gt 0 ] || { sed -n '2,10p' "$0"; exit 1; }

slug() { echo "$1" | sed -E 's#@https?://[^+]*##; s#[^A-Za-z0-9.+-]+#_#g'; }

for spec in "$@"; do
  sides=()
  [ "$ONLY" != harness ] && sides+=("$spec")
  [ "$ONLY" != base ] && sides+=("$(echo "$spec" | sed -E 's/(\+code|\+submit)//g')+code+submit")
  for s in "${sides[@]}"; do
    file="$OUT/$(slug "$s").jsonl"
    echo "== $s -> $file"
    "$PY" -m constructbench run --tasks "$TASKS" --provider "$s" --out "$file" --workers "$WORKERS" --effort "$EFFORT"
    "$PY" -m constructbench score "$file" --tasks "$TASKS" | head -1
  done
done

"$PY" -m constructbench leaderboard "$OUT"/*.jsonl --tasks "$TASKS" --out "$OUT/LEADERBOARD.md" >/dev/null
echo "leaderboard: $OUT/LEADERBOARD.md"
