"""Unified diff -> files and hunks, with the enclosing symbol of each hunk."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from unidiff import PatchSet

from . import langs


@dataclass
class Hunk:
    id: str  # "path#index"
    path: str  # path on the new side (old path for deleted files)
    old_path: str | None
    status: str  # added | deleted | modified | renamed
    index: int
    old_start: int
    new_start: int
    added: int
    removed: int
    added_lines: list[str]
    removed_lines: list[str]
    changed_new: list[int]  # new-side line numbers of added lines
    changed_old: list[int]  # old-side line numbers of removed lines
    text: str
    symbol: str | None = None
    top_symbol: str | None = None
    kind: str = "code"
    tags: list[str] = field(default_factory=list)
    label: str | None = None  # needed | cleanup | unrelated | risky | ancillary | None = unsettled
    reason: str = ""
    blast: dict | None = None
    pseudo: bool = False  # no textual hunk (rename-only, binary, mode change)

    @property
    def lines_changed(self) -> int:
        return self.added + self.removed


@dataclass
class FileChange:
    path: str
    old_path: str | None
    status: str
    hunks: list[Hunk]
    binary: bool = False
    header: str = ""  # the raw `diff --git` block up to the first hunk, kept so split patches stay faithful


def _status(pf) -> str:
    if pf.is_added_file:
        return "added"
    if pf.is_removed_file:
        return "deleted"
    if pf.source_file != pf.target_file and pf.path != pf.source_file.removeprefix("a/"):
        return "renamed"
    return "modified"


def _headers(diff_text: str) -> list[str]:
    segs = [s for s in re.split(r"(?m)^(?=diff --git )", diff_text) if s.strip()]
    out = []
    for seg in segs:
        m = re.search(r"(?m)^@@ ", seg)
        out.append(seg[: m.start()] if m else seg)
    return out


def parse_patch(diff_text: str) -> list[FileChange]:
    files: list[FileChange] = []
    headers = _headers(diff_text)
    patchset = PatchSet(diff_text)
    if len(headers) != len(patchset):
        headers = [""] * len(patchset)
    for pf, header in zip(patchset, headers):
        status = _status(pf)
        path = pf.path
        old_path = pf.source_file.removeprefix("a/") if pf.source_file != "/dev/null" else None
        if status == "deleted":
            path = old_path or path
        if status != "renamed":
            old_path = path if status != "added" else None
        hunks: list[Hunk] = []
        for i, h in enumerate(pf):
            added = [ln for ln in h if ln.is_added]
            removed = [ln for ln in h if ln.is_removed]
            hunks.append(
                Hunk(
                    id=f"{path}#{i}",
                    path=path,
                    old_path=old_path,
                    status=status,
                    index=i,
                    old_start=h.source_start,
                    new_start=h.target_start,
                    added=len(added),
                    removed=len(removed),
                    added_lines=[ln.value.rstrip("\n") for ln in added],
                    removed_lines=[ln.value.rstrip("\n") for ln in removed],
                    changed_new=[ln.target_line_no for ln in added],
                    changed_old=[ln.source_line_no for ln in removed],
                    text=str(h),
                )
            )
        binary = bool(getattr(pf, "is_binary_file", False))
        if not hunks:
            note = "binary file changed" if binary else ("renamed without content change" if status == "renamed" else "metadata-only change")
            hunks.append(
                Hunk(f"{path}#0", path, old_path, status, 0, 0, 0, 0, 0, [], [], [], [], note, pseudo=True)
            )
        files.append(FileChange(path, old_path, status, hunks, binary, header))
    return files


def attach_symbols(files: list[FileChange], read_head, read_base) -> None:
    """Fill hunk.symbol using tree-sitter. read_head/read_base(path) -> bytes | None."""
    for fc in files:
        if langs.language_of(fc.path) is None:
            continue
        deleted = fc.status == "deleted"
        src = read_base(fc.old_path or fc.path) if deleted else read_head(fc.path)
        if src is None:
            continue
        syms = langs.symbols(fc.path, src)
        if not syms:
            continue
        for h in fc.hunks:
            if h.pseudo:
                continue
            lines = h.changed_old if deleted else h.changed_new
            if lines:
                first, last = min(lines), max(lines)
            else:  # pure removal: the removal sits between the surrounding new-side lines
                first = last = max(h.new_start, 1)
            sym = langs.enclosing_symbol(syms, first, last)
            if sym is not None:
                h.symbol, h.top_symbol = sym.name, sym.top
