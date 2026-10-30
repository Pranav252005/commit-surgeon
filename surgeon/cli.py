from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .analyze import Analysis, analyze_pr
from .github import parse_ref

app = typer.Typer(add_completion=False, help="Review the shape of a pull request: what it changes, beyond what the issue asked for.")
console = Console()

@app.callback()
def main() -> None:
    """Commit Surgeon."""


LABEL_STYLE = {"needed": "green", "cleanup": "yellow", "unrelated": "red", "risky": "bold red", "ancillary": "dim", None: "white"}


def _short(sym: str | None) -> str:
    return ".".join(sym.split(".")[-2:]) if sym else ""


def render_table(a: Analysis, per_hunk: bool = False) -> None:
    pr = a.pr
    console.print(f"[bold]{pr.ref}[/bold]  {pr.title}  [dim]({pr.state}, {pr.changed_files} files, +{pr.additions}/-{pr.deletions})[/dim]")
    if a.issue:
        console.print(f"issue #{a.issue.number}: {a.issue.title}  [dim](linked via {a.issue.source})[/dim]")
    for n in a.notes:
        console.print(f"[dim]note: {n}[/dim]")
    table = Table(show_lines=False, pad_edge=False)
    for col in ("hunk" if per_hunk else "file", "symbol(s)", "kind", "+/-", "importers", "signals"):
        table.add_column(col, overflow="fold")
    rows = [[h] for h in a.hunks] if per_hunk else [f.hunks for f in a.files]
    for group in rows:
        first = group[0]
        syms = list(dict.fromkeys(_short(h.symbol) for h in group if h.symbol))
        sym = ", ".join(syms[:3]) + (f" +{len(syms) - 3}" if len(syms) > 3 else "")
        blasts = [h.blast for h in group if h.blast]
        top = max(blasts, key=lambda b: b["direct"], default=None)
        imp = "-" if not top else f"{top['direct_non_test']} (+{top['direct'] - top['direct_non_test']} test)"
        tags = dict.fromkeys(t for h in group for t in h.tags if t != first.kind)
        labels = {h.label for h in group if h.label}
        label = "".join(f"[{LABEL_STYLE.get(l, 'white')}]{l}[/] " for l in sorted(labels))
        name = first.id if per_hunk else f"{first.path} [dim]({len(group)})[/dim]"
        table.add_row(name, sym, first.kind, f"+{sum(h.added for h in group)}/-{sum(h.removed for h in group)}", imp, label + ", ".join(tags))
    console.print(table)
    console.print(f"[dim]timings (s): {a.timings}[/dim]")


@app.command()
def analyze(
    pr: str = typer.Argument(..., help="owner/repo#123 or a PR URL"),
    json_out: Optional[Path] = typer.Option(None, "--json", help="write the full analysis as JSON to this path ('-' for stdout)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="no table, only write --json"),
    hunks: bool = typer.Option(False, "--hunks", help="one row per hunk instead of per file"),
) -> None:
    """Analyze a PR (read-only against GitHub)."""
    try:
        ref = parse_ref(pr)
        with console.status("analyzing…") as st:
            a = analyze_pr(ref, progress=lambda m: st.update(f"{m}…"))
    except (ValueError, LookupError, RuntimeError) as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1)
    if json_out is not None:
        payload = json.dumps(a.as_dict(), indent=2)
        if str(json_out) == "-":
            print(payload)
        else:
            json_out.write_text(payload)
    if not quiet and str(json_out) != "-":
        render_table(a, hunks)


if __name__ == "__main__":
    app()
