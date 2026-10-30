#!/usr/bin/env bash
# Evaluate several open models on ScopeBench, one at a time, then rebuild LEADERBOARD.md.
#   bench/leaderboard.sh                       # the default model list
#   bench/leaderboard.sh gemma3:4b qwen2.5:3b  # your own list (Ollama names)
# Results are resumable: rerun it and finished PRs are skipped.
set -u
cd "$(dirname "$0")/.."
MODELS=("$@")
[ ${#MODELS[@]} -eq 0 ] && MODELS=(gemma3:4b llama3.2:3b qwen2.5:3b phi4-mini gemma3:1b)
MAX_HUNKS="${MAX_HUNKS:-40}"

nice uv run python bench/run_eval.py --no-model --max-hunks "$MAX_HUNKS"   # heuristics-only baseline, no model needed
for m in "${MODELS[@]}"; do
  ollama list | awk 'NR>1{print $1}' | grep -qx "$m" || nice ollama pull "$m"
  echo "=== $m"
  nice uv run python bench/run_eval.py --model "$m" --max-hunks "$MAX_HUNKS"
done
uv run python bench/run_eval.py --report-only
