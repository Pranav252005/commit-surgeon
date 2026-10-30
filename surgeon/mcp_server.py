"""An MCP server so coding agents (Claude Code, Codex, Cursor) can check scope before they open a PR.

    surgeon mcp            # stdio; add it to your agent's MCP config

Nothing here talks to stdout except the protocol itself.
"""

from __future__ import annotations

from pathlib import Path

from . import report
from .local import analyze_local
from .pipeline import judge_analysis


def check_scope(
    repo_dir: str = ".",
    against: str | None = None,
    issue_title: str | None = None,
    issue_body: str = "",
    use_model: bool = True,
    model: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Check whether your change does only what the issue asks, before you push or open a PR.

    Checks the staged changes, or HEAD against `against` (for example "origin/main") when given.
    Pass `issue_title` (and `issue_body`) so relevance is judged against what was asked for.
    Returns a verdict (FOCUSED / SPLIT SUGGESTED / MOSTLY OUT OF SCOPE), a 0-100 scope score and every hunk with
    its label (needed / cleanup / unrelated / risky), a reason and its blast radius. Trim the hunks labelled
    cleanup, unrelated or risky out of the change, or split them into their own PR, then check again.
    """
    a = analyze_local(Path(repo_dir), against=against, issue_title=issue_title, issue_body=issue_body)
    a, summary, used_model = judge_analysis(a, no_model=not use_model, model=model, base_url=base_url)
    out = a.as_dict(include_text=False)
    return {
        "verdict": summary.verdict,
        "score": summary.score,
        "advice": report.friendly(a, summary),
        "model": used_model,
        "counts": {str(k): v for k, v in summary.counts.items()},
        "hunks": [
            {k: h[k] for k in ("id", "path", "symbol", "kind", "label", "reason", "added", "removed")}
            | {"importers": (h["blast"] or {}).get("direct_non_test")}
            for h in out["hunks"]
        ],
        "notes": out["notes"],
    }


def serve() -> None:
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as e:
        raise SystemExit("the MCP server needs the extra: pip install 'commit-surgeon[mcp]'") from e
    server = MCPServer(
        "commit-surgeon", instructions="Check that a change stays within the scope of its issue before pushing or opening a PR."
    )
    server.tool()(check_scope)
    server.run()
