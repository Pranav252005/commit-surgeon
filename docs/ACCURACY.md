# How accurate is it?

Measured on 2026-10-31. Two different questions, with very different answers: are the *facts* right, and is the
*judgement* right.

## 1. The facts: deterministic, checked against independent ground truth

| What | Check | Result |
|---|---|---|
| Who imports a changed file (blast radius) | `git grep` at the same commit, httpx: `_config`, `_types`, `_utils`, `_client`, `_main` | exact match on all 5 (same files, same counts) |
| same, Java | gson, `Gson.java`, grep of explicit + wildcard imports | 113 vs 113 |
| same, Rust | anyhow, `src/error.rs` | 3 vs 3 |
| same, Go | cobra root package via `go.mod` | 11; grep says 12, and the extra hit is an import inside a raw string literal in a test, so 11 is right |
| Which function a hunk belongs to | Python's own `ast` module as the reference, 3 real PRs | 82 of 82 hunks agree |
| Split patches | each patch `git apply --check` on the base; all applied in order must equal the PR head tree | passes in unit tests (added, deleted, renamed, shifted hunks, binary files) and on real PRs, see `bench/stress.py` |
| Everything else | 86 automated tests | pass |

Bugs this found and that are fixed: wrong base commit (the branch tip instead of the merge base), user git config
changing diff paths, "risky" applied to whitespace-only changes, Java `Latest.java` read as a test, Rust parent-module
imports, binary files breaking a patch.

Known limits: import resolution is static. Dynamic imports, reflection and cross-crate or cross-module-path
aliasing are not seen, so a count is a floor.

## 2. The judgement: the model labels, measured on ScopeBench

Ground truth: real PRs where a maintainer asked for a split or called a change out of scope, anchored to a file and
line. 120 candidates were collected by script, 40 kept by hand (maintainers merely deferring a contributor's idea were
dropped), and each PR is analyzed at the commit the maintainer reviewed.

**19 PRs completed for every model** (14 with a file anchor, 5 PR-level). The other 21 were skipped: the commented
commit is no longer on GitHub, or the PR is too large to judge in reasonable time.

| | agreed (>=1 objected hunk flagged) | 95% interval | hunk recall | precision (lower bound) | F1 |
|---|---|---|---|---|---|
| gemma3:4b | 5 of 14 | 16-61% | 35% | 13% | 0.19 |
| gemma3:1b | 6 of 14 | 21-67% | 35% | 13% | 0.19 |
| llama3.2:3b | 12 of 14 | 60-96% | 88% | 7% | 0.13 |
| heuristics only (no model) | 2 of 14 | 4-40% | 12% | 33% | 0.17 |
| flag everything | 14 of 14 | 78-100% | 100% | 7% | 0.12 |

### What that means, plainly

- **It is not accurate enough to trust blindly.** The best small models score F1 0.19. That is better than flagging
  everything (0.12) and about level with the no-model heuristics (0.17), not a clear step above them.
- **The two gemma models are tied**, and the sample is far too small to rank them. The intervals overlap almost entirely.
- **llama3.2:3b's "12 of 14" is not good.** It flags almost every hunk (recall 88%, precision 7%), which is why the
  leaderboard ranks by F1 and shows the flag-everything baseline.
- **Precision is a lower bound.** A hunk the maintainer did not mention counts as a miss even if it is out of scope too.
- **Where it works:** plainly unrelated changes (a doc edit in a feature PR, a reformat, a stray option). Where it can't:
  policy objections such as "split the config flow into its own PR" or "this section belongs in another doc". Nothing in
  the issue text says so, and no model can guess it.
- **The verdict is coarse.** The scope score is weighted by changed lines, so one small stray hunk in a large PR still
  reads FOCUSED. The grouped hunk list is the useful output, not the headline.
- **The labels are noisy.** Maintainer comments are an imperfect ground truth; this bench measures agreement with them,
  not truth.

### Rule-based signals came after these numbers

The risk rules (CI, auth/crypto, new dependencies, shell/network calls, removed tests, changed signatures) and the PR-level
warnings were added after the table above was measured. They are covered by unit tests only. They make more hunks `risky`, so a
new bench run would differ from the numbers here; they have not been re-measured.

### Tried, but only exploratory

- **Voting across the three models** (flag a hunk when 2 of 3 agree), replayed on the stored results: F1 0.22 against 0.19 for
  the best single model, from 3 more caught hunks out of 17. The rule was picked after seeing the results, so treat it as a lead.
- **A second prompt (`SURGEON_PROMPT=v2`)** that shows the model a map of the PR's files. It is implemented. Its test run was
  cancelled, so there is no number for it and v1 remains the default.

### What would likely help (not done, so not claimed)

Larger models (the bench takes any OpenAI-compatible endpoint, so this is a one-line run), more PRs, and a held-out
split before tuning the prompt. Tuning the prompt on these 19 PRs would overfit, so it was not done.

Reproduce: `bench/leaderboard.sh`, then read `bench/RESULTS.md` (per PR, every miss) and `bench/LEADERBOARD.md`.
