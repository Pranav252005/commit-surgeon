from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import repo, report
from . import split as splitmod
from .analyze import Analysis
from .github import GitHub, parse_ref
from .local import analyze_local
from .pipeline import judge_analysis
from .pipeline import run as run_pipeline

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


MODEL_OPTS = dict(
    no_model=typer.Option(False, "--no-model", help="heuristics and import graph only"),
    model=typer.Option(None, "--model", help="model name (default: $SURGEON_MODEL or gemma3:4b)"),
    base_url=typer.Option(None, "--base-url", help="OpenAI-compatible endpoint (default: local Ollama)"),
    api_key_env=typer.Option(None, "--api-key-env", help="name of the env var holding an API key, if the endpoint needs one"),
    risky_importers=typer.Option(report.RISKY_IMPORTERS, "--risky-importers", help="non-test importers that make a stray change risky"),
)


@app.command()
def analyze(
    pr: str = typer.Argument(..., help="owner/repo#123 or a PR URL"),
    json_out: Optional[Path] = typer.Option(None, "--json", help="write the full analysis as JSON to this path ('-' for stdout)"),
    md: Optional[Path] = typer.Option(None, "--md", help="write the Markdown report to this path ('-' for stdout)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="no terminal report"),
    hunks: bool = typer.Option(False, "--hunks", help="heuristics table with one row per hunk (debug view)"),
    no_model: bool = MODEL_OPTS["no_model"],
    model: Optional[str] = MODEL_OPTS["model"],
    base_url: Optional[str] = MODEL_OPTS["base_url"],
    api_key_env: Optional[str] = MODEL_OPTS["api_key_env"],
    risky_importers: int = MODEL_OPTS["risky_importers"],
) -> None:
    """Analyze a PR (read-only against GitHub)."""
    try:
        with console.status("analyzing…") as st:
            a, summary, used_model = run_pipeline(pr, no_model=no_model, model=model, base_url=base_url, api_key_env=api_key_env, risky_importers=risky_importers, progress=lambda m: st.update(f"{m}…"))
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


@app.command()
def split(
    pr: str = typer.Argument(..., help="owner/repo#123 or a PR URL"),
    out: Path = typer.Option(Path("surgeon-split"), "--out", help="directory for the .patch files"),
    no_model: bool = MODEL_OPTS["no_model"],
    model: Optional[str] = MODEL_OPTS["model"],
    base_url: Optional[str] = MODEL_OPTS["base_url"],
    api_key_env: Optional[str] = MODEL_OPTS["api_key_env"],
    risky_importers: int = MODEL_OPTS["risky_importers"],
    no_verify: bool = typer.Option(False, "--no-verify", help="skip the git apply checks"),
) -> None:
    """Write one patch per group (fix / cleanup / unrelated / risky) and print the commands to apply them."""
    try:
        with console.status("analyzing…") as st:
            a, summary, used_model = run_pipeline(pr, no_model=no_model, model=model, base_url=base_url, api_key_env=api_key_env, risky_importers=risky_importers, progress=lambda m: st.update(f"{m}…"))
            plan = splitmod.plan(a)
            if not no_verify and plan.groups:
                st.update("checking that the patches apply…")
                reader = repo.fetch_pr(*_owner_repo_number(pr), a.pr.base_sha, a.pr.head_sha, GitHub().token)
                splitmod.verify(plan, reader)
    except (ValueError, LookupError, RuntimeError, repo.GitError) as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[bold]{report.verdict_line(a, summary)}[/bold]")
    if not plan.groups:
        console.print("Nothing to split: no hunk was labelled. Run with a model.")
        raise typer.Exit(0)
    if len(plan.groups) == 1:
        console.print("[green]One focused group: nothing to split.[/green]")
    splitmod.write(plan, out)
    for g in plan.groups:
        status = {True: "[green]applies[/green]", False: f"[red]does not apply[/red] {g.note}", None: "[dim]unchecked[/dim]"}[g.applies]
        console.print(f"{g.number}. {g.filename}: {len(g.hunks)} hunk(s), {g.blurb}  {status}")
    if plan.skipped:
        console.print(f"[yellow]{len(plan.skipped)} hunk(s) not placed in any patch (unjudged).[/yellow]")
    if plan.lossless is True:
        console.print("[green]Verified: applying all patches in order reproduces the PR head exactly.[/green]")
    elif plan.note:
        console.print(f"[yellow]{plan.note}[/yellow]")
    console.print()
    for line in splitmod.commands(plan, a, out):
        console.print(line, markup=False, highlight=False)


@app.command()
def check(
    staged: bool = typer.Option(True, "--staged/--no-staged", help="check what is staged (default)"),
    against: Optional[str] = typer.Option(None, "--against", help="check HEAD against this base ref instead, e.g. origin/main"),
    issue_title: Optional[str] = typer.Option(None, "--issue-title", help="what the change is supposed to do"),
    issue_body: str = typer.Option("", "--issue-body"),
    issue: Optional[int] = typer.Option(None, "--issue", help="GitHub issue number to fetch from origin"),
    json_out: Optional[Path] = typer.Option(None, "--json", help="machine-readable result ('-' for stdout), for coding agents"),
    fail_under: Optional[int] = typer.Option(None, "--fail-under", help="exit 1 if the scope score is below this (for a pre-push hook)"),
    repo_dir: Path = typer.Option(Path("."), "--repo", help="the git repository to check"),
    no_model: bool = MODEL_OPTS["no_model"],
    model: Optional[str] = MODEL_OPTS["model"],
    base_url: Optional[str] = MODEL_OPTS["base_url"],
    api_key_env: Optional[str] = MODEL_OPTS["api_key_env"],
    risky_importers: int = MODEL_OPTS["risky_importers"],
) -> None:
    """Check your own change before you push it. Local diff, local model: nothing leaves your machine."""
    try:
        with console.status("checking…") as st:
            a = analyze_local(repo_dir, against=against, issue_title=issue_title, issue_body=issue_body, issue_number=issue, progress=lambda m: st.update(f"{m}…"))
            a, summary, used_model = judge_analysis(a, no_model=no_model, model=model, base_url=base_url, api_key_env=api_key_env, risky_importers=risky_importers, progress=lambda m: st.update(f"{m}…"))
    except (ValueError, LookupError, RuntimeError, repo.GitError) as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(2)
    if json_out is not None:
        payload = json.dumps({**a.as_dict(), "summary": summary.as_dict(), "model": used_model}, indent=2)
        print(payload) if str(json_out) == "-" else json_out.write_text(payload)
    if str(json_out) != "-":
        report.render_terminal(a, summary, console, used_model)
    if fail_under is not None and summary.score is not None and summary.score < fail_under:
        console.print(f"[red]scope score {summary.score} is below --fail-under {fail_under}[/red]")
        raise typer.Exit(1)


def _owner_repo_number(pr: str) -> tuple[str, str, int]:
    r = parse_ref(pr)
    return r.owner, r.repo, r.number


if __name__ == "__main__":
    app()
