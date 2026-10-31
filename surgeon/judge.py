"""Ask an LLM one narrow question per hunk: is this change needed for the issue?

Model-agnostic: any server that speaks the OpenAI chat-completions API works (Ollama, llama.cpp, vLLM,
LM Studio, OpenRouter, ...). The default is a local Gemma through Ollama, so code stays on the machine.
Results are cached by (model, prompt). If the model is unreachable, callers get None and fall back to
heuristics-only output; this module never raises on a model failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .diff import Hunk
from .repo import cache_root

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_BASE_URL = "http://localhost:11434/v1"
LABELS = {"needed", "cleanup", "unrelated"}

SYSTEM = """You review the SHAPE of a pull request, not its code quality.
For one hunk of the diff, decide how it relates to the linked issue.

Labels:
- needed: the hunk is required to resolve the issue (the fix itself, or a test/doc for that fix).
- cleanup: a tidy-up the issue did not ask for (formatting, renames, refactors, dead code, typo fixes elsewhere).
- unrelated: a different feature or fix that the issue did not ask for.

Be skeptical. A hunk is "needed" only if the issue could not be resolved without it. New examples, tutorials,
extra options, drive-by refactors and style changes are not needed unless the issue asks for them.

Reply with JSON only: {"label": "needed|cleanup|unrelated", "confidence": 0.0-1.0, "reason": "max 15 words"}."""


SYSTEM_V2 = """You help a maintainer review the SHAPE of a pull request. For one hunk, answer one question:
would a careful maintainer ask the author to move this hunk into a separate PR?

You are given what the PR is meant to do (the linked issue, or the PR's own description when there is none), a map of
the files the PR touches, where this hunk sits in that map, and the hunk.

Labels:
- needed: the PR's purpose cannot be met without this hunk. The fix or feature itself, the call sites it forces to
  change, and tests or docs for that same behaviour.
- cleanup: a tidy-up the purpose does not require. Reformatting, renames, moved code, refactors of code the fix does
  not need, typo fixes elsewhere, dependency or config bumps.
- unrelated: it adds or changes behaviour the purpose never mentions. A second feature, a second bug fix, a new option,
  a new example, a change in a different module or product area.

How to decide:
- Find the PR's centre of gravity in the file map: the area holding most of the changes. A hunk in a different area
  that the purpose does not mention is the likeliest to need splitting.
- Tests and docs are needed only when they cover the behaviour this PR changes. A test or doc for something else is not.
- Small edits count too. A one-line drive-by change is as separable as a large one.
- If the purpose is vague, judge by how the hunk relates to the centre of gravity, not by whether the change looks fine.

Examples (purpose: "parse() crashes on empty input"):
- adds `if not s: return None` at the top of parse() -> {"reason": "this guard is the fix for the crash", "label": "needed", "confidence": 0.9}
- renames the variable `x` to `value` inside an unrelated helper -> {"reason": "rename that the crash fix does not need", "label": "cleanup", "confidence": 0.8}
- adds a new `--verbose` command-line option -> {"reason": "new option, the issue never asks for it", "label": "unrelated", "confidence": 0.85}

Reply with JSON only, reason first: {"reason": "max 20 words naming the link to the purpose, or the lack of it", "label": "needed|cleanup|unrelated", "confidence": 0.0-1.0}"""


def prompt_version() -> str:
    """v1 is the original single-hunk prompt (kept so old results stay reproducible); v2 adds the PR file map."""
    return "v2" if os.environ.get("SURGEON_PROMPT", "v1") == "v2" else "v1"


def _system() -> str:
    return SYSTEM_V2 if prompt_version() == "v2" else SYSTEM


def _area(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def pr_map(hunks: list[Hunk], max_files: int = 25) -> tuple[str, dict[str, int], int]:
    """The shape of the whole PR, computed once: changed lines per file, and per directory. Returns (text, per-area lines, total)."""
    per_file: dict[str, int] = {}
    per_area: dict[str, int] = {}
    for h in hunks:
        n = max(h.lines_changed, 1)
        per_file[h.path] = per_file.get(h.path, 0) + n
        per_area[_area(h.path)] = per_area.get(_area(h.path), 0) + n
    total = sum(per_area.values()) or 1
    files = sorted(per_file.items(), key=lambda kv: -kv[1])
    lines = [f"- {p} ({n} lines)" for p, n in files[:max_files]]
    if len(files) > max_files:
        lines.append(f"- ... and {len(files) - max_files} more files")
    return "\n".join(lines), per_area, total


def hunk_position(hunk: Hunk, per_area: dict[str, int], total: int) -> str:
    here = _area(hunk.path)
    top, top_n = max(per_area.items(), key=lambda kv: kv[1])
    share = round(100 * per_area.get(here, 0) / total)
    where = "the PR's largest area" if here == top else f"not the PR's largest area ({top}/ holds {round(100 * top_n / total)}%)"
    return f"This hunk is in {here}/, which holds {share}% of the changed lines: {where}."


@dataclass
class ModelConfig:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key_env: str | None = None  # name of an env var holding the key; never a key itself
    timeout: float = 180.0
    cache: bool = True

    @classmethod
    def from_env(cls, **overrides) -> ModelConfig:
        cfg = cls(
            model=os.environ.get("SURGEON_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("SURGEON_BASE_URL", DEFAULT_BASE_URL),
            api_key_env=os.environ.get("SURGEON_API_KEY_ENV"),
        )
        for k, v in overrides.items():
            if v is not None:
                setattr(cfg, k, v)
        return cfg


@dataclass
class Verdict:
    label: str
    confidence: float
    reason: str
    cached: bool = False


def build_prompt(
    hunk: Hunk, pr_title: str, issue_title: str, issue_body: str, max_hunk: int = 2500, max_issue: int = 1200, context: str = ""
) -> str:
    body = re.sub(r"\s+\n", "\n", issue_body.strip())[:max_issue]
    text = hunk.text if len(hunk.text) <= max_hunk else hunk.text[:max_hunk] + "\n[... hunk truncated ...]"
    where = f"{hunk.path}" + (f" in `{hunk.symbol}`" if hunk.symbol else "")
    signals = ", ".join(t for t in hunk.tags if t != hunk.kind) or "none"
    text = text.encode("utf-8", "replace").decode("utf-8")  # raw bytes from non-UTF-8 files cannot go into a JSON request
    if prompt_version() == "v2":
        # shared PR context first, the hunk last: the server can reuse the cached prefix for every hunk of the same PR
        return (
            f"PR title: {pr_title}\n"
            f"Purpose (issue title): {issue_title}\n"
            f"Purpose (issue body):\n{body or '(empty)'}\n\n"
            f"{context}\n"
            f"Hunk location: {where} (kind: {hunk.kind}; heuristic signals: {signals})\n"
            f"Hunk:\n{text}\n"
        )
    return (
        f"PR title: {pr_title}\n"
        f"Issue title: {issue_title}\n"
        f"Issue body:\n{body or '(empty)'}\n\n"
        f"Hunk location: {where} (kind: {hunk.kind}; heuristic signals: {signals})\n"
        f"Hunk:\n{text}\n"
    )


def _parse(raw: str) -> Verdict | None:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    label = str(d.get("label", "")).strip().lower()
    if label not in LABELS:
        return None
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return Verdict(label, conf, str(d.get("reason", "")).strip()[:300])


class Judge:
    def __init__(self, cfg: ModelConfig | None = None, cache_dir: Path | None = None, client: httpx.Client | None = None):
        self.cfg = cfg or ModelConfig.from_env()
        self.cache_dir = cache_dir or cache_root() / "judge"
        headers = {}
        if self.cfg.api_key_env and os.environ.get(self.cfg.api_key_env):
            headers["Authorization"] = f"Bearer {os.environ[self.cfg.api_key_env]}"
        self.http = client or httpx.Client(base_url=self.cfg.base_url.rstrip("/"), headers=headers, timeout=self.cfg.timeout)
        self.error: str | None = None  # last failure, for the report footnote

    def available(self) -> bool:
        try:
            r = self.http.get("/models", timeout=5)
            return r.status_code == 200
        except httpx.HTTPError as e:
            self.error = f"model server unreachable ({type(e).__name__})"
            return False

    def _key(self, prompt: str) -> Path:
        h = hashlib.sha256(f"{self.cfg.model}\0{self.cfg.base_url}\0{_system()}\0{prompt}".encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def judge(self, hunk: Hunk, pr_title: str, issue_title: str, issue_body: str, context: str = "") -> Verdict | None:
        prompt = build_prompt(hunk, pr_title, issue_title, issue_body, context=context)
        path = self._key(prompt)
        if self.cfg.cache and path.exists():
            try:
                return Verdict(**{**json.loads(path.read_text()), "cached": True})
            except (OSError, ValueError, TypeError):
                pass
        body = {
            "model": self.cfg.model,
            "temperature": 0,
            "stream": False,
            "max_tokens": 120 if prompt_version() == "v2" else 80,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": _system()}, {"role": "user", "content": prompt}],
        }
        try:
            r = self.http.post("/chat/completions", json=body)
            r.raise_for_status()
            verdict = _parse(r.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            self.error = f"model call failed ({type(e).__name__})"
            return None
        if verdict is None:
            self.error = "model returned an unusable answer"
            return None
        if self.cfg.cache:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"label": verdict.label, "confidence": verdict.confidence, "reason": verdict.reason}))
            except OSError:
                pass
        return verdict


def judge_hunks(hunks: list[Hunk], judge: Judge, pr_title: str, issue_title: str, issue_body: str, progress=lambda i, n: None) -> int:
    """Fill label/reason on hunks the heuristics left unsettled. Returns how many the model answered."""
    todo = [h for h in hunks if h.label is None and not h.pseudo]
    shared, per_area, total = pr_map(hunks) if prompt_version() == "v2" else ("", {}, 1)
    answered = 0
    for i, h in enumerate(todo, 1):
        progress(i, len(todo))
        ctx = f"Files in this PR, by changed lines:\n{shared}\n{hunk_position(h, per_area, total)}\n" if shared else ""
        v = judge.judge(h, pr_title, issue_title, issue_body, ctx)
        if v is None:
            if judge.error and "unreachable" in judge.error:
                break  # no point trying the rest
            continue
        h.label = v.label
        h.reason = v.reason
        h.tags.append(f"model:{judge.cfg.model}")
        h.blast = {**(h.blast or {}), "confidence": v.confidence}
        answered += 1
    return answered
