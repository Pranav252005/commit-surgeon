"""Turn labelled hunks into a series of small patches and the git commands that apply them.

Each patch applies on its own to the base branch (independent PRs). We also prove the split is lossless:
applying every patch in order to a scratch index must reproduce the PR's head tree.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .analyze import Analysis
from .diff import FileChange, Hunk
from .repo import RevReader

ORDER = [
    ("needed", "fix", "the change the issue asks for"),
    ("cleanup", "cleanup", "cleanup the issue did not ask for"),
    ("unrelated", "unrelated", "changes unrelated to the issue"),
    ("risky", "risky", "changes to widely imported code, review on their own"),
]
_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass
class Group:
    number: int
    slug: str
    blurb: str
    labels: set[str]
    hunks: list[Hunk] = field(default_factory=list)
    patch: str = ""
    applies: bool | None = None  # git apply --check on the base
    note: str = ""

    @property
    def filename(self) -> str:
        return f"{self.number:02d}-{self.slug}.patch"


@dataclass
class SplitPlan:
    groups: list[Group]
    skipped: list[Hunk]  # unjudged hunks and the like, not in any patch
    lossless: bool | None = None
    note: str = ""


def _fix_header(text: str, offset: int) -> tuple[str, int]:
    """Rewrite a hunk header so its new-side start accounts for earlier hunks left out. Returns (text, new offset)."""
    first, _, rest = text.partition("\n")
    m = _HDR.match(first)
    if not m:
        return text, offset
    os_, tail = int(m[1]), m[5]
    old_len = 1 if m[2] is None else int(m[2])
    new_len = 1 if m[4] is None else int(m[4])
    before_old = os_ - 1 if old_len > 0 else os_
    before_new = before_old + offset
    new_start = before_new + 1 if new_len > 0 else before_new
    header = f"@@ -{m[1]}{'' if m[2] is None else ',' + m[2]} +{new_start}{'' if m[4] is None else ',' + m[4]} @@{tail}"
    return header + "\n" + rest, offset + (new_len - old_len)


def build_patch(files: list[FileChange], hunk_ids: set[str]) -> str:
    out: list[str] = []
    for fc in files:
        chosen = [h for h in fc.hunks if h.id in hunk_ids]
        if not chosen:
            continue
        out.append(fc.header if fc.header.endswith("\n") or not fc.header else fc.header + "\n")
        offset = 0
        for h in chosen:
            if h.pseudo:
                continue
            text, offset = _fix_header(h.text, offset)
            out.append(text if text.endswith("\n") else text + "\n")
    return "".join(out)


def plan(a: Analysis) -> SplitPlan:
    groups: list[Group] = []
    placed: set[str] = set()
    for label, slug, blurb in ORDER:
        labels = {label} | ({"ancillary"} if label == "needed" else set())
        hs = [h for h in a.hunks if h.label in labels]
        if not hs:
            continue
        g = Group(len(groups) + 1, slug, blurb, labels, hs)
        g.patch = build_patch(a.files, {h.id for h in hs})
        groups.append(g)
        placed |= {h.id for h in hs}
    skipped = [h for h in a.hunks if h.id not in placed]
    return SplitPlan(groups, skipped)


def _git(reader: RevReader, *args: str, env: dict | None = None, input: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(reader.git_dir), *args], capture_output=True, env=env, input=input)


def verify(p: SplitPlan, reader: RevReader) -> None:
    """git apply --check each patch on the base; then apply them all in sequence and compare the tree with head."""
    with tempfile.TemporaryDirectory() as tmp:
        base_index = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "base")}
        r = _git(reader, "read-tree", reader.base, env=base_index)
        if r.returncode != 0:
            p.note = "could not verify: " + r.stderr.decode()[:200]
            return
        for g in p.groups:
            res = _git(reader, "apply", "--cached", "--check", "-", env=base_index, input=g.patch.encode())
            g.applies = res.returncode == 0
            if not g.applies:
                g.note = res.stderr.decode().strip().splitlines()[0][:200] if res.stderr else "does not apply"
        seq_index = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "seq")}
        _git(reader, "read-tree", reader.base, env=seq_index)
        ok = True
        for g in p.groups:
            res = _git(reader, "apply", "--cached", "-", env=seq_index, input=g.patch.encode())
            if res.returncode != 0:
                ok = False
                p.note = f"patches applied in order stop at {g.filename}: {res.stderr.decode().strip()[:160]}"
                break
        if ok:
            tree = _git(reader, "write-tree", env=seq_index).stdout.decode().strip()
            head_tree = _git(reader, "rev-parse", f"{reader.head}^{{tree}}").stdout.decode().strip()
            p.lossless = (tree == head_tree) and not p.skipped
            if tree != head_tree and not p.skipped:
                p.note = "patches applied but the result differs from the PR head (binary files or modes?)"
            elif p.skipped:
                p.note = f"{len(p.skipped)} hunk(s) were not placed in any patch, so the series is incomplete"
        else:
            p.lossless = False


def write(p: SplitPlan, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for g in p.groups:
        (out_dir / g.filename).write_text(g.patch)


def commands(p: SplitPlan, a: Analysis, out_dir: Path, base_branch: str | None = None) -> list[str]:
    base = base_branch or a.pr.base_ref
    lines = [f"# Run in a clone of {a.pr.ref.split('#')[0]}, each branch starts from {base}:"]
    for g in p.groups:
        branch = f"pr-{g.number}-{g.slug}"
        msg = f"{g.slug.capitalize()}: {a.pr.title}".replace('"', "'")
        lines.append(f'git switch -c {branch} origin/{base} && git apply {out_dir / g.filename} && git add -A && git commit -m "{msg}"')
    return lines
