# Commit Surgeon

Reviews the *shape* of a pull request, not its code quality. Give it a PR and its linked issue:
it labels every hunk as needed for the issue, unrelated cleanup, or risky (touches shared code),
shows the blast radius of each change, and prints the git commands that split the PR into
small, focused PRs.

Status: work in progress.

## AI tools used

- Claude Code (planning and code)
- Gemma (local, via Ollama) for judging hunk relevance

## Licence

Apache-2.0. See [LICENSE](LICENSE).
