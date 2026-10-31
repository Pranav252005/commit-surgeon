# Commit Surgeon

Reviews the *shape* of a pull request, not its code quality.

Give it a PR and its linked issue. It labels every hunk as **needed for the issue**, **cleanup the issue
did not ask for**, **unrelated**, or **risky** (touches code many files import), shows the blast radius of
each change, and writes the patches that split the PR into small, focused ones. It never comments on, blocks
or closes anything: it only reads a PR and tells the reviewer what they are looking at.

It works on a PR from any author: a person, Copilot, Claude Code, Devin or a spam bot.

**Try it:** [c-surgeon.vercel.app](https://c-surgeon.vercel.app) checks any public PR in your browser (rule-based half, no install). [c-surgeon-site.vercel.app](https://c-surgeon-site.vercel.app) explains what it is, which models it uses and what it costs.

```
$ surgeon analyze owner/repo#123
 SPLIT SUGGESTED: scope score 61/100 (412 judged changed lines)
 This PR does what the issue asks. 3 hunk(s) would merge faster as separate, smaller PRs.

 Needed for the issue  9 hunk(s)
 Risky: touches shared code the issue did not ask about  1 hunk(s)
   utils/date.py::parse  +4/-1
     imported by 14 files (11 non-test); 9 of them use `parse`
 ...
```

## How it works

```
diff ──► heuristics ──► import graph ──► model ──► report ──► split
```

1. **Diff**: the PR diff is split into hunks, and each hunk is mapped to its enclosing function or class with tree-sitter (Python, JS/TS).
2. **Heuristics, no model needed**: whitespace-only hunks, pure renames, lockfiles and generated files are labelled right away. Docs/test/config kinds and "does the issue mention this file or symbol" become signals.
3. **Import graph**: the base branch is read straight from git objects (shallow fetch, no checkout) to find who imports each changed module and symbol. A stray change inside a module imported by 5 or more non-test files is labelled **risky**, unless nobody outside the module uses that symbol.
4. **Model**: for each hunk the heuristics left open, one narrow question: *is this needed for the issue?* The answer is cached per model and prompt. If the model is down you still get the heuristics report.
5. **Report**: a verdict (`FOCUSED` / `SPLIT SUGGESTED` / `MOSTLY OUT OF SCOPE`), a scope score (share of judged changed lines that are needed), and grouped hunks with their evidence.
6. **Split**: one patch per group. Every patch is checked with `git apply --check` on the base, and the series is applied to a scratch index to prove it reproduces the PR head exactly.

## Install and use

Not on PyPI yet. Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Pranav252005/commit-surgeon && cd commit-surgeon
uv sync
ollama pull gemma3:4b          # any OpenAI-compatible model works, see below

uv run surgeon analyze owner/repo#123              # terminal report
uv run surgeon analyze owner/repo#123 --md out.md --json out.json
uv run surgeon analyze owner/repo#123 --no-model   # heuristics and import graph only
uv run surgeon split owner/repo#123 --out patches  # patches + the git commands to apply them
```

GitHub access is read-only. The token comes from `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`; without one you hit the unauthenticated rate limit.

### Check your own change before you push

```bash
git add -p                                          # stage what you mean to ship
surgeon check --issue-title "Fix crash in parse()"  # staged changes vs the issue
surgeon check --against origin/main --issue 123     # HEAD vs a base branch, issue fetched from origin
surgeon check --json -                              # stable JSON for scripts and coding agents
surgeon check --fail-under 80                       # exit 1 below this scope score: a pre-push hook
```

Everything runs on your machine. The issue is only fetched from GitHub if you pass `--issue N`.

### For coding agents (MCP)

`surgeon mcp` is an MCP server (stdio) with one tool, `check_scope`. An agent calls it before opening a PR,
trims the hunks it labels cleanup / unrelated / risky, and checks again.

```bash
uv sync --extra mcp                                # from your clone of this repo
claude mcp add commit-surgeon -- uv run --directory "$PWD" surgeon mcp   # or the same command in Codex / Cursor
```

### Rule-based flags and warnings (no model)

Pure pattern matching on paths and changed lines, so they work offline and cost nothing. A hunk that carries one of these
signals is marked **risky** unless the issue asked for it (an asked-for hunk keeps its label and gets a "review carefully" note):

- changes CI or workflow configuration (GitHub Actions, CircleCI, GitLab CI, ...)
- touches authentication or cryptography code (`auth/`, `crypto`, `hashlib`, `verify=False`, ...)
- adds a dependency to a manifest (`requirements.txt`, `package.json`, `Cargo.toml`, `go.mod`, ...), not a version bump
- adds a shell or network call (`subprocess`, `fetch(`, `requests.get(`, ...)
- removes tests, or changes the signature of a public function (Python, JS/TS exports, Go, Rust, Java)

Two PR-level warnings are printed next to the verdict: **"Source changed, no tests changed"**, and **"the issue names
a file or function this PR never touches"** (the reverse of the usual scope check: the fix may be incomplete).
Limits: static text patterns only, so multi-line signatures and indirect calls are not seen. These rules are covered by unit tests
but have not been measured on ScopeBench.

### GitHub Action

`action/action.yml` runs the analysis on every PR in your repo and keeps one comment up to date.
See `examples/surgeon.yml`. Without a `base-url` it runs the heuristics and import graph only (no model);
point `base-url` at any OpenAI-compatible endpoint to get the full labels. It only ever comments on the PR it runs for.
The comment has a summary table (verdict, score, hunk counts), the warnings above and the suggested split in a collapsed section
(`surgeon split owner/repo#N` writes the patches). It is a suggestion by default; set the `fail-under` input (0-100) to fail the job below a score.

### Any open model

The judge speaks the OpenAI chat-completions API, so anything that serves it works: Ollama (default), llama.cpp,
vLLM, LM Studio, OpenRouter.

```bash
surgeon analyze owner/repo#123 --model qwen3:8b
surgeon analyze owner/repo#123 --base-url http://localhost:8080/v1 --model my-model
surgeon analyze owner/repo#123 --base-url https://openrouter.ai/api/v1 --model <id> --api-key-env OPENROUTER_API_KEY
```

Defaults can also come from `SURGEON_MODEL`, `SURGEON_BASE_URL` and `SURGEON_API_KEY_ENV`. Keys are read from the environment, never stored.
With the default local model your code never leaves your machine.

## Evaluation (ScopeBench)

`bench/` holds real PRs where a maintainer asked for a split or called a change out of scope, with the file and
line they pointed at. Each PR is analyzed *as the maintainer saw it*, at the commit they commented on, because
authors often remove the flagged code later. Collection is scripted (`bench/collect.py`), curation is by hand
(`bench/curate.py` records every decision, and the PRs where a maintainer merely deferred a contributor's idea were left out).

**Where it stands today** (19 PRs, small open models that fit a 4 GB GPU; details and caveats in [`docs/ACCURACY.md`](docs/ACCURACY.md)):

| | F1 on hunks maintainers objected to |
|---|---|
| `gemma3:4b` and `gemma3:1b` (tied) | 0.19 |
| `llama3.2:3b` (flags nearly everything) | 0.13 |
| heuristics only, no model | 0.17 |
| flag every hunk (baseline) | 0.12 |

The facts it reports (who imports what, which function a hunk is in, the split patches) are checked against `grep`, Python's
`ast` and `git apply`. The model's judgement is the weak part: small models are only modestly better than the baselines, and
the sample is too small to rank them. Treat labels as a starting point for a reviewer, not a verdict.

- [`bench/LEADERBOARD.md`](bench/LEADERBOARD.md): models ranked on the same PRs, with the best model named and a flag-everything baseline.
- [`bench/RESULTS.md`](bench/RESULTS.md): per-PR results for every model, including the misses.
- Add your model: `bench/leaderboard.sh <ollama-model>` or `bench/run_eval.py --model <name> --base-url <endpoint>`, then open a PR with the new results file.
- `SURGEON_PROMPT=v2` (or `bench/run_eval.py --prompt v2`) switches the judge to an experimental prompt that also shows the model a map of
  the PR's files. It is implemented but **not yet measured**: the test run was cancelled, so v1 stays the default.
- `scripts/modal_bench.py` runs the bench on a rented GPU on [Modal](https://modal.com) (`modal run scripts/modal_bench.py --help`).

## AI tools used

- Claude Code (Sonnet 5.5, Opus 5.5): planning, pair-programming the code
- Gemma 3 4B, run locally through Ollama: the hunk judge

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Licence: [Apache-2.0](LICENSE).
