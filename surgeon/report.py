"""Verdict, scope score and the grouped report (terminal and Markdown)."""

from __future__ import annotations

from dataclasses import dataclass

from . import risk
from .analyze import Analysis
from .diff import Hunk

RISKY_IMPORTERS = 5  # non-test files importing the touched module before we call a stray change risky
GROUPS = [
    ("needed", "Needed for the issue", "green"),
    ("risky", "Risky: shared or sensitive code the issue did not ask about", "bold red"),
    ("unrelated", "Unrelated to the issue", "red"),
    ("cleanup", "Cleanup the issue did not ask for", "yellow"),
    ("ancillary", "Generated or lockfile changes (follow their source change)", "dim"),
    (None, "Not judged (no model answer)", "white"),
]


@dataclass
class Summary:
    verdict: str
    score: int | None  # share of judged changed lines that are needed, 0-100
    judged_lines: int
    total_lines: int
    counts: dict
    partial: bool  # some hunks have no label (model unavailable)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def apply_risky(hunks: list[Hunk], threshold: int = RISKY_IMPORTERS) -> None:
    """A stray change (cleanup/unrelated) inside a module many files import is risky, not merely noisy."""
    for h in hunks:
        b = h.blast or {}
        if "whitespace_only" in h.tags:  # reformatting cannot break an importer
            continue
        why = risk.explain(h.tags)
        if why:  # rule-based signal (CI, crypto, dependency, shell/network, removed tests, changed signature)
            asked_for = any(t.startswith("mentioned_by_") for t in h.tags)
            if h.label == "needed" or (h.label is None and asked_for):
                h.reason = (h.reason + " " if h.reason else "") + f"Review carefully: {why}."
            elif h.label in {"cleanup", "unrelated", None}:
                h.tags.append(f"was:{h.label}")
                h.label = "risky"
                h.reason = (h.reason + " " if h.reason else "") + f"{why[0].upper()}{why[1:]}."
                continue
        if h.label in {"cleanup", "unrelated"} and h.kind == "code" and b.get("direct_non_test", 0) >= threshold:
            used = b.get("symbol_importers")
            if used == 0:  # private symbol nobody outside the module uses: not risky for importers
                continue
            h.tags.append(f"was:{h.label}")
            h.label = "risky"
            h.reason = (h.reason + " " if h.reason else "") + (b.get("evidence") or "")


def summarize(a: Analysis, threshold: int = RISKY_IMPORTERS) -> Summary:
    apply_risky(a.hunks, threshold)
    counts: dict = {}
    judged = needed = total = 0
    for h in a.hunks:
        lines = max(h.lines_changed, 1) if not h.pseudo else 0
        counts[h.label] = counts.get(h.label, 0) + 1
        total += lines
        if h.label is None or h.label == "ancillary":
            continue
        judged += lines
        if h.label == "needed":
            needed += lines
    partial = counts.get(None, 0) > 0
    if judged == 0:
        return Summary("UNSCORED", None, 0, total, counts, partial)
    score = round(100 * needed / judged)
    verdict = "FOCUSED" if score >= 90 else "SPLIT SUGGESTED" if score >= 60 else "MOSTLY OUT OF SCOPE"
    return Summary(verdict, score, judged, total, counts, partial)


def _short(sym: str | None) -> str:
    return ".".join(sym.split(".")[-2:]) if sym else ""


def _merge(hunks: list[Hunk]) -> list[list[Hunk]]:
    """Consecutive hunks in the same file and symbol read as one item."""
    out: list[list[Hunk]] = []
    for h in hunks:
        if out and out[-1][0].path == h.path and out[-1][0].symbol == h.symbol:
            out[-1].append(h)
        else:
            out.append([h])
    return out


def _item(group: list[Hunk]) -> tuple[str, str, str]:
    h = group[0]
    where = h.path + (f"::{_short(h.symbol)}" if h.symbol else "")
    n = f" ({len(group)} hunks)" if len(group) > 1 else ""
    size = f"+{sum(g.added for g in group)}/-{sum(g.removed for g in group)}"
    reason = next((g.reason for g in group if g.reason), "")
    if h.label is None:  # no model answer: show what the heuristics did find
        sig = [t.replace("_", " ") for t in dict.fromkeys(t for g in group for t in g.tags if t != h.kind and not t.startswith("model:"))]
        b = max((g.blast for g in group if g.blast), key=lambda b: b.get("direct_non_test", 0), default=None)
        ev = b["evidence"] if b and b.get("direct_non_test") else ""
        reason = "; ".join(x for x in [", ".join(sig), ev] if x)
    return f"{where}{n}", size, reason


def verdict_line(a: Analysis, s: Summary) -> str:
    if s.score is None:
        return "UNSCORED: no hunk could be judged"
    return f"{s.verdict}: scope score {s.score}/100 ({s.judged_lines} judged changed lines)"


def friendly(a: Analysis, s: Summary) -> str:
    """One kind sentence for first-time contributors; says what to do, never blocks."""
    n_off = sum(s.counts.get(k, 0) for k in ("cleanup", "unrelated", "risky"))
    if s.score is None:
        return "Could not judge the hunks. Run with a local model for the full report."
    if n_off == 0:
        return "Every judged hunk looks needed for the issue. Nice and focused."
    return f"This PR does what the issue asks. {n_off} hunk(s) would merge faster as separate, smaller PRs."


def render_terminal(a: Analysis, s: Summary, console, model: str | None, per_hunk: bool = False) -> None:
    from rich.panel import Panel

    pr = a.pr
    console.print(f"[bold]{pr.ref}[/bold]  {pr.title}  [dim]({pr.state}, {pr.changed_files} files, +{pr.additions}/-{pr.deletions})[/dim]")
    if a.issue:
        console.print(f"issue #{a.issue.number}: {a.issue.title}  [dim](linked via {a.issue.source})[/dim]")
    style = {"FOCUSED": "green", "SPLIT SUGGESTED": "yellow", "MOSTLY OUT OF SCOPE": "red"}.get(s.verdict, "white")
    console.print(Panel(f"[bold {style}]{verdict_line(a, s)}[/]\n{friendly(a, s)}", expand=False))
    for w in a.warnings:
        console.print(f"[yellow]warning: {w}[/yellow]")
    for label, title, color in GROUPS:
        hs = [h for h in a.hunks if h.label == label]
        if not hs:
            continue
        console.print(f"\n[{color}]{title}[/]  [dim]{len(hs)} hunk(s)[/dim]")
        for group in _merge(hs):
            name, size, reason = _item(group)
            console.print(f"  {name}  [dim]{size}[/dim]")
            if reason:
                console.print(f"    [dim]{reason}[/dim]")
    for n in a.notes:
        console.print(f"[dim]note: {n}[/dim]")
    if s.partial:
        console.print("[yellow]heuristics only for some hunks: the model was unavailable or did not answer.[/yellow]")
    console.print(f"[dim]model: {model or 'none'}   timings (s): {a.timings}[/dim]")


def _split_section(a: Analysis, s: Summary) -> list[str]:
    """The suggested series, collapsed. The patches themselves come from `surgeon split` (the comment cannot attach files)."""
    from . import split as splitmod

    plan = splitmod.plan(a)
    if len(plan.groups) < 2:
        return []
    out = ["", "<details><summary>Suggested split into smaller PRs</summary>", ""]
    out += [f"{g.number}. {g.blurb}: {len(g.hunks)} hunk(s)" for g in plan.groups]
    out += ["", "Get the patches and the git commands:", "", "```", f"surgeon split {a.pr.ref}", "```", "", "</details>"]
    return out


def render_markdown(a: Analysis, s: Summary, model: str | None) -> str:
    pr = a.pr
    off = sum(s.counts.get(k, 0) for k in ("cleanup", "unrelated", "risky"))
    out = ["<!-- commit-surgeon -->", f"## Commit Surgeon: {s.verdict}", "", friendly(a, s), ""]
    out += [
        "| Verdict | Scope score | Hunks | Needed | Off-scope | Risky |",
        "|---|---|---|---|---|---|",
        f"| {s.verdict} | {'n/a' if s.score is None else f'{s.score}/100'} | {sum(s.counts.values())} "
        f"| {s.counts.get('needed', 0)} | {off} | {s.counts.get('risky', 0)} |",
        "",
    ]
    out += [f"> **Warning:** {w}" for w in a.warnings] + ([""] if a.warnings else [])
    out.append(f"PR: `{pr.ref}` {pr.title}  ")
    if a.issue:
        out.append(f"Issue: #{a.issue.number} {a.issue.title}")
    for label, title, _ in GROUPS:
        hs = [h for h in a.hunks if h.label == label]
        if not hs:
            continue
        out += ["", f"### {title} ({len(hs)})", ""]
        for group in _merge(hs):
            name, size, reason = _item(group)
            out.append(f"- `{name}` {size}" + (f": {reason}" if reason else ""))
    out += _split_section(a, s)
    out += ["", f"<sub>model: {model or 'none'}. Suggestions only: this never blocks a PR unless the workflow sets a minimum score.</sub>"]
    return "\n".join(out) + "\n"
