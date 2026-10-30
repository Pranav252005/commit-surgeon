# Commit Surgeon

Reviews the *shape* of a pull request, not its code quality.

Give it a PR and its linked issue. It labels every hunk as **needed for the issue**, **cleanup the issue
did not ask for**, **unrelated**, or **risky** (touches code many files import), shows the blast radius of
each change, and writes the patches that split the PR into small, focused ones. It never comments on, blocks
or closes anything: it only reads a PR and tells the reviewer what they are looking at.

It works on a PR from any author: a person, Copilot, Claude Code, Devin or a spam bot.

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
git clone <this repo> && cd commit-surgeon
uv sync
ollama pull gemma3:4b          # any OpenAI-compatible model works, see below

uv run surgeon analyze owner/repo#123              # terminal report
uv run surgeon analyze owner/repo#123 --md out.md --json out.json
uv run surgeon analyze owner/repo#123 --no-model   # heuristics and import graph only
uv run surgeon split owner/repo#123 --out patches  # patches + the git commands to apply them
```

GitHub access is read-only. The token comes from `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`; without one you hit the unauthenticated rate limit.

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
line they pointed at. `bench/run_eval.py` runs the tool on them and `bench/RESULTS.md` has the measured numbers,
including the misses. Run it with any model to compare models.

## AI tools used

- Claude Code (Sonnet 5.5, Opus 5.5): planning, pair-programming the code
- Gemma 3 4B, run locally through Ollama: the hunk judge

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Licence: [Apache-2.0](LICENSE).
