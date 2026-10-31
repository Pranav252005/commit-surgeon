# ScopeBench leaderboard

Models ranked by hunk-level F1 on the 19 bench PRs every listed model completed (PRs the tool skipped as too large or that errored are excluded for all).
Each PR is analyzed as the maintainer saw it, at the commit they commented on. Same prompt, same settings, temperature 0, one run per model.

**Best models, tied: `gemma3:4b`, `gemma3:1b`** (F1 0.19; 14 PRs is too few to separate them).

| # | model | agreed (>=1 objected hunk flagged) | hunk recall | hunk precision (lower bound) | F1 | PR-level not-FOCUSED | median s/PR |
|---|---|---|---|---|---|---|---|
| 1 | `gemma3:4b` | 5 of 14 | 35% | 13% | 0.19 | 4/5 | 134.0 |
| 2 | `gemma3:1b` | 6 of 14 | 35% | 13% | 0.19 | 5/5 | 104.0 |
| 3 | `llama3.2:3b` | 12 of 14 | 88% | 7% | 0.13 | 5/5 | 44.2 |

Baselines (no model):

| | agreed | recall | precision | F1 |
|---|---|---|---|---|
| heuristics-only | 2 of 14 | 12% | 33% | 0.17 |
| flag everything (baseline) | 14 of 14 | 100% | 7% | 0.12 |

Precision is a lower bound: a hunk the maintainer did not mention is counted as a miss even if it is out of scope too.
A model that beats `flag everything` on F1 is doing more than guessing.

## Add your model

```bash
uv run python bench/run_eval.py --model <name> --base-url <openai-compatible endpoint>/v1
```
Then commit the new `bench/results/<name>.json` and the regenerated `LEADERBOARD.md` in a PR. Same bench, same prompt.
