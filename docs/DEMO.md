# Demo script (3 minutes)

Three real PRs, all read-only. Run `scripts/warm_demo.sh` first so the clones and the model answers are cached.
Keep the clones off a small disk with `export SURGEON_CACHE_DIR=/tmp/surgeon-cache`.

| Beat | PR | What to say |
|---|---|---|
| Focused | `pallets/flask#2936` | "A real fix. It says FOCUSED and why each hunk is needed." |
| Scope creep + risky | `cockpit-project/cockpit#19024` at `3bc11384b38879091df0671fa4231c31cca9c58d` | "A maintainer told the author to split this. The tool found the same hunk and shows who imports it." |
| The split | same PR | "And these are the patches, verified to reproduce the PR exactly." |

```bash
# 1. Focused PR
surgeon analyze pallets/flask#2936

# 2. Scope creep, as the maintainer saw it (the author changed the PR afterwards)
surgeon analyze cockpit-project/cockpit#19024 --at 3bc11384b38879091df0671fa4231c31cca9c58d

# 3. Split it
surgeon split cockpit-project/cockpit#19024 --at 3bc11384b38879091df0671fa4231c31cca9c58d --out /tmp/surgeon-demo-patches

# 4. Your own work, before you push
surgeon check --against origin/main --issue-title "what this change is for"
```

Point at, in beat 2: the verdict and score at the top; the **Risky** group (each line shows how many files import the
touched code); and `NetworkManagerModel.refresh_settings`, which the maintainer asked to be split into its own commit.

## The number

Open `bench/LEADERBOARD.md`. Say the measured figure and the baseline next to it, and say it is small: the bench has
real PRs where a maintainer objected, scored on whether the tool points at the same hunks. Be ready to show a miss
(`bench/RESULTS.md` lists every one). Policy-style objections ("split the config flow into its own PR") cannot be
known from the issue text, and no model gets those.

## Questions

- *Devin / Copilot already review PRs?* They write or comment on code. This is for the maintainer who receives 40 PRs: it checks the *shape*, and runs locally.
- *False positives?* It only suggests, never blocks or comments on its own. The precision figure in the leaderboard is a lower bound and we say so.
- *Why a small model?* Heuristics and the import graph do most of the work; the model answers one narrow question per hunk. Any OpenAI-compatible model works (`--model`, `--base-url`).
- *Languages?* Python, JS/TS, Java, Go and Rust, through tree-sitter.
- *Your code stays private?* Yes with the default local model. Only GitHub reads happen, and they are read-only.
