"""Check your own change before you push: staged changes, or HEAD against a base ref. Never touches the network
unless you ask it to fetch the linked issue."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from . import diff as diffmod
from .analyze import Analysis, enrich
from .github import GitHub, IssueInfo, PRInfo
from .repo import GitError, RevReader

_ISSUE_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?|for)\b[:\s]+#(\d+)", re.I)


DIFF_ARGS = [
    "-c",
    "core.quotePath=false",
    "diff",
    "--no-color",
    "--no-ext-diff",
    "--src-prefix=a/",
    "--dst-prefix=b/",
]  # user config (mnemonicPrefix, noprefix) must not change the paths


def _git(repo_dir: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, encoding="utf-8", errors="surrogateescape")
    if p.returncode != 0:
        raise GitError(p.stderr.strip() or f"git {' '.join(args)} failed")
    return p.stdout


def _origin_slug(repo_dir: Path) -> str | None:
    try:
        url = _git(repo_dir, "remote", "get-url", "origin").strip()
    except GitError:
        return None
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def analyze_local(
    repo_dir: Path = Path("."),
    *,
    against: str | None = None,
    issue_title: str | None = None,
    issue_body: str = "",
    issue_number: int | None = None,
    progress=lambda m: None,
) -> Analysis:
    """Staged changes (default) or `against...HEAD`. The issue comes from --issue-title/--issue N, else from a
    `fixes #N` in the latest commit message when GitHub is reachable, else the commit subject stands in."""
    repo_dir = Path(repo_dir)
    root = Path(_git(repo_dir, "rev-parse", "--show-toplevel").strip())
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir").strip())
    t0 = time.perf_counter()
    if against:
        base = _git(root, "merge-base", against, "HEAD").strip()
        head = _git(root, "rev-parse", "HEAD").strip()
        diff_text = _git(root, *DIFF_ARGS, base, head)
        label = f"{against}...HEAD"
        subject = _git(root, "log", "-1", "--format=%s").strip()
        body = _git(root, "log", "-1", "--format=%b").strip()
    else:
        base = _git(root, "rev-parse", "HEAD").strip()
        head = _git(root, "write-tree").strip()  # a tree-ish: the repo reader can read blobs from it
        diff_text = _git(root, *DIFF_ARGS, "--cached")
        label = "staged"
        subject, body = "staged changes", ""
    if not diff_text.strip():
        raise ValueError("nothing to check: no changes " + ("between the base and HEAD" if against else "staged (git add first)"))

    notes: list[str] = []
    issue: IssueInfo | None = None
    if issue_title is not None:
        issue = IssueInfo("local", issue_number or 0, issue_title, issue_body, "flag", "")
    else:
        n = issue_number
        if n is None:
            m = _ISSUE_RE.search(f"{subject}\n{body}")
            n = int(m[1]) if m else None
        slug = _origin_slug(root)
        if n is not None and slug:
            try:
                issue = GitHub().issue(slug, n, "commit-message")
            except Exception as e:  # offline or private repo: carry on without the issue
                notes.append(f"could not fetch issue #{n} ({type(e).__name__})")
        if issue is None:
            notes.append("no issue given: pass --issue-title/--issue-body or --issue N. The commit subject stands in")

    files = diffmod.parse_patch(diff_text)
    pr = PRInfo(
        ref=f"local:{label}",
        title=subject,
        body=body,
        author="",
        state="local",
        base_ref=against or "HEAD",
        base_sha=base,
        head_sha=head,
        changed_files=len(files),
        additions=sum(h.added for f in files for h in f.hunks),
        deletions=sum(h.removed for f in files for h in f.hunks),
        url="",
    )
    return enrich(files, RevReader(git_dir, base, head), pr, issue, {"diff": round(time.perf_counter() - t0, 2)}, notes, progress)
