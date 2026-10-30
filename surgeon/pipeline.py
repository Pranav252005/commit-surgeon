"""One call that does the whole job: analyze, judge, summarize. Shared by the CLI, the Action and the eval."""
from __future__ import annotations

import time

from . import report
from .analyze import Analysis, analyze_pr
from .github import GitHub, parse_ref
from .judge import Judge, ModelConfig, judge_hunks


def run(
    pr: str,
    *,
    no_model: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    risky_importers: int = report.RISKY_IMPORTERS,
    progress=lambda msg: None,
    gh: GitHub | None = None,
) -> tuple[Analysis, report.Summary, str | None]:
    """Returns (analysis, summary, model name or None when no model answered)."""
    a = analyze_pr(parse_ref(pr), gh=gh, progress=progress)
    used_model = None
    if not no_model:
        j = Judge(ModelConfig.from_env(model=model, base_url=base_url, api_key_env=api_key_env))
        if j.available():
            title, body = (a.issue.title, a.issue.body) if a.issue else (a.pr.title, a.pr.body)
            t0 = time.perf_counter()
            answered = judge_hunks(a.hunks, j, a.pr.title, title, body, lambda i, n: progress(f"asking {j.cfg.model} ({i}/{n})"))
            a.timings["model"] = round(time.perf_counter() - t0, 2)
            used_model = j.cfg.model if answered else None
            if not answered and any(h.label is None and not h.pseudo for h in a.hunks):
                a.notes.append(f"{j.error or 'the model gave no usable answer'}: showing heuristics only.")
        else:
            a.notes.append(f"{j.error or 'model unavailable'}: showing heuristics only. Start `ollama serve` or pass --base-url.")
    return a, report.summarize(a, risky_importers), used_model
