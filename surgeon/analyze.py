"""Orchestrates one PR analysis: GitHub -> hunks -> symbols -> import graph -> heuristics."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from . import diff as diffmod
from . import heuristics, repo
from .github import GitHub, IssueInfo, PRInfo, PRRef
from .graph import SOURCE_EXTS, ImportGraph


@dataclass
class Analysis:
    pr: PRInfo
    issue: IssueInfo | None
    files: list[diffmod.FileChange]
    timings: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def hunks(self) -> list[diffmod.Hunk]:
        return [h for f in self.files for h in f.hunks]

    def as_dict(self, include_text: bool = True) -> dict:
        hunks = []
        for h in self.hunks:
            d = asdict(h)
            if not include_text:
                d.pop("text", None)
            for k in ("added_lines", "removed_lines", "changed_new", "changed_old"):
                d.pop(k, None)
            hunks.append(d)
        return {
            "pr": asdict(self.pr),
            "issue": self.issue.as_dict() if self.issue else None,
            "hunks": hunks,
            "timings": self.timings,
            "notes": self.notes,
        }


def analyze_pr(ref: PRRef, gh: GitHub | None = None, progress=lambda msg: None) -> Analysis:
    gh = gh or GitHub()
    t = {}
    tick = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal tick
        now = time.perf_counter()
        t[name] = round(now - tick, 2)
        tick = now

    progress(f"fetching {ref}")
    pr = gh.pr(ref)
    diff_text = gh.diff(ref)
    issue = gh.linked_issue(ref, pr)
    lap("github")
    files = diffmod.parse_patch(diff_text)
    notes: list[str] = []
    if issue is None:
        notes.append("no linked issue found: relevance signals use the PR title/body only")

    progress("fetching git objects (shallow)")
    reader = repo.fetch_pr(ref.owner, ref.repo, ref.number, pr.base_sha, pr.head_sha, gh.token)
    lap("git_fetch")

    progress("mapping hunks to symbols")
    diffmod.attach_symbols(files, reader.read_head, reader.read_base)
    lap("symbols")

    progress("building import graph")
    graph = ImportGraph(reader.tree(pr.base_sha, SOURCE_EXTS))
    lap("graph")
    for fc in files:
        base_path = fc.old_path or fc.path
        for h in fc.hunks:
            if fc.status == "added":
                continue
            h.blast = graph.blast(base_path, h.top_symbol).as_dict()

    title, body = (issue.title, issue.body) if issue else (pr.title, pr.body)
    heuristics.apply(files, graph, title, body, "issue" if issue else "pr")
    lap("heuristics")
    return Analysis(pr, issue, files, t, notes)
