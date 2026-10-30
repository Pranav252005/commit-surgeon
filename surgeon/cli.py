from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import report
from .analyze import Analysis, analyze_pr
from .github import parse_ref
from .judge import Judge, ModelConfig, judge_hunks

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
    md: Optional[Path] = typer.Option(None, "--md", help="write the Markdown report to this path ('-' for stdout)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="no terminal report"),
    hunks: bool = typer.Option(False, "--hunks", help="heuristics table with one row per hunk (debug view)"),
    no_model: bool = typer.Option(False, "--no-model", help="heuristics and import graph only"),
    model: Optional[str] = typer.Option(None, "--model", help="model name (default: $SURGEON_MODEL or gemma3:4b)"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="OpenAI-compatible endpoint (default: local Ollama)"),
    api_key_env: Optional[str] = typer.Option(None, "--api-key-env", help="name of the env var holding an API key, if the endpoint needs one"),
    risky_importers: int = typer.Option(report.RISKY_IMPORTERS, "--risky-importers", help="non-test importers that make a stray change risky"),
) -> None:
    """Analyze a PR (read-only against GitHub)."""
    try:
        ref = parse_ref(pr)
        with console.status("analyzing…") as st:
            a = analyze_pr(ref, progress=lambda m: st.update(f"{m}…"))
            used_model = None
            if not no_model:
                j = Judge(ModelConfig.from_env(model=model, base_url=base_url, api_key_env=api_key_env))
                if j.available():
                    title, body = (a.issue.title, a.issue.body) if a.issue else (a.pr.title, a.pr.body)
                    t0 = time.perf_counter()
                    judge_hunks(a.hunks, j, a.pr.title, title, body, lambda i, n: st.update(f"asking {j.cfg.model} ({i}/{n})…"))
                    a.timings["model"] = round(time.perf_counter() - t0, 2)
                    used_model = j.cfg.model
                else:
                    a.notes.append(f"{j.error or 'model unavailable'}: showing heuristics only. Start `ollama serve` or pass --base-url.")
            summary = report.summarize(a, risky_importers)
    except (ValueError, LookupError, RuntimeError) as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1)
    if json_out is not None:
        payload = json.dumps({**a.as_dict(), "summary": summary.as_dict(), "model": used_model}, indent=2)
        if str(json_out) == "-":
            print(payload)
        else:
            json_out.write_text(payload)
    if md is not None:
        text = report.render_markdown(a, summary, used_model)
        print(text) if str(md) == "-" else md.write_text(text)
    if not quiet and "-" not in {str(json_out), str(md)}:
        if hunks or no_model and not any(h.label for h in a.hunks):
            render_table(a, hunks)
        else:
            report.render_terminal(a, summary, console, used_model)


if __name__ == "__main__":
    app()
