# Contributing

Small, focused PRs are the whole point of this project, so please keep yours that way.

## Set up

```bash
uv sync
uv run pytest -q
```

Tests do not need the network or a model: GitHub and the model are faked, and the split tests build a real temporary git repo.

## Layout

```
surgeon/  github.py   read-only GitHub access
          diff.py     unified diff -> hunks, symbols
          langs.py    tree-sitter symbols and imports
          repo.py     read files from git objects, shallow fetch
          graph.py    reverse-import graph, blast radius
          heuristics.py   checks that need no model
          judge.py    model-agnostic hunk judge (OpenAI-compatible)
          report.py   verdict, scope score, reports
          split.py    patches and git commands
          pipeline.py, analyze.py, cli.py
bench/    ScopeBench collector, eval runner, results
tests/
```

## Ground rules

- GitHub access stays read-only. The tool must never write to someone else's repo.
- No secrets in the repo. API keys come from environment variables.
- Report real numbers. If you change the prompt or heuristics, re-run `bench/run_eval.py` and commit the new `RESULTS.md`, misses included.
- Adding a language: add its tree-sitter grammar in `langs.py` (symbols and imports) and import resolution in `graph.py`.
