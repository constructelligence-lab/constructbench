#!/usr/bin/env bash
# Runs ConstructBench for one or more models, each WITHOUT and WITH the harness (+code+submit), then the leaderboard.
#
#   scripts/bench.sh anthropic:claude-opus-5-5 anthropic:claude-sonnet-5-5
#   scripts/bench.sh api:deepseek-chat@https://api.deepseek.com/v1
#   scripts/bench.sh local:qwen3-4b-instruct-2507              # LM Studio
#   TASKS=data/dev.jsonl ONLY=harness scripts/bench.sh ...      # ONLY=base|harness to run one side
#   CONDITIONS="base code submit harness" EFFORTS="low medium high" REPEATS=3 scripts/bench.sh anthropic:claude-haiku-5-5
#     CONDITIONS: base (no tools), code (+code), submit (+submit), harness (+code+submit); default "base harness"
#     EFFORTS: Claude effort levels (file names get @<effort> unless it is high); REPEATS: runs per task
#   BUDGET=4.50 TASK_BUDGET=0.30 LIMIT=2 scripts/bench.sh anthropic:claude-opus-5-5
#   MAX_TOKENS=32000 scripts/bench.sh api:deepseek-flash@https://api.deepseek.com/v1   # per-reply output limit
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
CONDITIONS="${CONDITIONS:-base harness}"
[ "$ONLY" = base ] && CONDITIONS=base
[ "$ONLY" = harness ] && CONDITIONS=harness
EFFORTS="${EFFORTS:-$EFFORT}"
REPEATS="${REPEATS:-1}"
MAX_TOKENS="${MAX_TOKENS:-}"
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
  plain="$(echo "$spec" | sed -E 's/(\+code|\+submit)//g')"
  for cond in $CONDITIONS; do
    case "$cond" in
      base) s="$plain" ;; code) s="$plain+code" ;; submit) s="$plain+submit" ;; harness) s="$plain+code+submit" ;;
      *) echo "unknown condition $cond"; exit 1 ;;
    esac
    efforts="$EFFORTS"; case "$s" in anthropic:*) ;; *) efforts=high ;; esac
    for eff in $efforts; do
      tag=""; [ "$eff" != high ] && tag="@$eff"
      file="$OUT/$(slug "$s")$tag.jsonl"
      echo "== $s effort=$eff repeats=$REPEATS -> $file"
      m=(); while IFS= read -r x; do m+=("$x"); done < <(money)
      "$PY" -m constructbench run --tasks "$TASKS" --provider "$s" --out "$file" --workers "$WORKERS" --effort "$eff" \
        --repeats "$REPEATS" ${MAX_TOKENS:+--max-tokens "$MAX_TOKENS"} ${m[@]+"${m[@]}"}
      "$PY" -m constructbench score "$file" --tasks "$TASKS" | head -1
    done
  done
done

res=(); for f in "$OUT"/*.jsonl; do case "$f" in *.manifest.jsonl) ;; *) res+=("$f");; esac; done
"$PY" -m constructbench leaderboard "${res[@]}" --tasks "$TASKS" --out "$OUT/LEADERBOARD.md" >/dev/null
echo "leaderboard: $OUT/LEADERBOARD.md"
