"""Run Commit Surgeon on the bench PRs and compare with what the maintainers objected to.

    uv run python bench/run_eval.py --model gemma3:4b
    uv run python bench/run_eval.py --no-model          # heuristics-only baseline
    uv run python bench/run_eval.py --report-only       # rebuild RESULTS.md from bench/results/*.json

Ground truth is a maintainer comment asking for a split / saying a change is out of scope, anchored to a file
and line. We map each anchor to the hunk containing that line (or to every hunk of the file when the line is
outdated). A hunk the maintainer did not mention is NOT assumed to be in scope, so precision is a lower bound.
Runs one PR at a time on purpose (one model, one GPU).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import time
from pathlib import Path

# Shallow clones of ~35 repos (cpython, pytorch, home-assistant, ...) add up to GBs. Keep them in RAM-backed /tmp and
# prune each repo once its PRs are done, so the bench never fills the real disk. Override with SURGEON_CACHE_DIR.
os.environ.setdefault("SURGEON_CACHE_DIR", "/tmp/surgeon-bench-cache")

from surgeon import pipeline, repo  # noqa: E402
from surgeon.judge import ModelConfig

HERE = Path(__file__).parent
RESULTS = HERE / "results"
FLAGGED = {"cleanup", "unrelated", "risky"}
TIE_MARGIN = 0.02  # F1 differences below this are noise at this sample size
_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)


def wait_for_memory(min_mb: int = 800, max_wait: int = 900) -> None:
    """This machine runs many other sessions: do not push it into swap or OOM. Wait for RAM, up to max_wait seconds."""
    waited = 0
    while waited < max_wait:
        try:
            avail = next(int(line.split()[1]) for line in open("/proc/meminfo") if line.startswith("MemAvailable")) // 1024
        except (OSError, StopIteration, ValueError):
            return
        if avail >= min_mb:
            return
        print(f"  (waiting for memory: {avail} MB available)", flush=True)
        time.sleep(30)
        waited += 30


def hunk_ranges(h) -> tuple[range, range]:
    m = _HDR.search(h.text)
    if not m:
        return range(0), range(0)
    o, ol, n, nl = int(m[1]), int(m[2] or 1) if m[2] != "0" else 0, int(m[3]), int(m[4] or 1) if m[4] != "0" else 0
    return range(o, o + ol), range(n, n + nl)


def objected_hunk_ids(a, objected: list[dict]) -> set[str]:
    ids: set[str] = set()
    for o in objected:
        path = o["path"]
        file_hunks = [h for h in a.hunks if path in {h.path, h.old_path}]
        hit = []
        if o.get("line"):
            for h in file_hunks:
                old_r, new_r = hunk_ranges(h)
                if o["line"] in (old_r if o.get("side") == "LEFT" else new_r):
                    hit.append(h)
        ids |= {h.id for h in (hit or file_hunks)}  # outdated anchor: the whole file counts
    return ids


def evaluate_pr(pr: dict, label: dict, args) -> dict:
    t0 = time.perf_counter()
    rec = {"ref": pr["ref"], "title": pr["title"], "url": pr["url"]}
    # the PR as the maintainer saw it: at the commit they commented on (the author may have changed the code since)
    commits = [o["commit"] for o in label["objected"] if o.get("commit")]
    at = max(set(commits), key=commits.count) if commits else None
    if at:
        label = {**label, "objected": [o for o in label["objected"] if o.get("commit") == at]}
    rec["at_commit"] = at
    try:
        a, summary, used = pipeline.run(
            pr["ref"], no_model=args.no_model, model=args.model, base_url=args.base_url, max_hunks=args.max_hunks, head_sha=at
        )
    except pipeline.TooLarge as e:
        return {**rec, "error": str(e), "skipped": True}
    except LookupError as e:  # GitHub has no such commit any more (force-pushed away or deleted): permanent
        return {**rec, "error": f"commit unavailable: {e}"[:200], "skipped": True}
    except repo.GitError as e:  # only "no longer fetchable" is permanent; a failed fetch is transient and gets retried
        permanent = "no longer fetchable" in str(e)
        return {
            **rec,
            "error": f"{'commit unavailable' if permanent else 'git error'}: {e}"[:200],
            **({"skipped": True} if permanent else {}),
        }
    except Exception as e:  # keep going: one bad PR must not sink the run
        return {**rec, "error": f"{type(e).__name__}: {e}"[:200]}
    objected = objected_hunk_ids(a, label["objected"]) if label["objected"] else set()
    judged = [h for h in a.hunks if not h.pseudo]
    flagged = {h.id for h in judged if h.label in FLAGGED}
    rec.update(
        hunks=len(judged),
        unjudged=sum(1 for h in judged if h.label is None),
        objected=sorted(objected),
        flagged=sorted(flagged),
        pr_level_only=not label["objected"],
        verdict=summary.verdict,
        score=summary.score,
        seconds=round(time.perf_counter() - t0, 1),
        model_seconds=a.timings.get("model", 0),
        model=used,
        labels={h.id: h.label for h in judged},
    )
    return rec


def aggregate(recs: list[dict]) -> dict:
    ok = [r for r in recs if "error" not in r]
    anchored = [r for r in ok if r["objected"]]
    pr_level = [r for r in ok if r["pr_level_only"]]
    tp = sum(len(set(r["objected"]) & set(r["flagged"])) for r in anchored)
    fn = sum(len(set(r["objected"]) - set(r["flagged"])) for r in anchored)
    fp = sum(len(set(r["flagged"]) - set(r["objected"])) for r in anchored)
    all_hunks = sum(r["hunks"] for r in anchored)
    pos = tp + fn
    agreed = sum(1 for r in anchored if set(r["objected"]) & set(r["flagged"]))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec_ = tp / pos if pos else 0.0
    return {
        "prs_total": len(recs),
        "prs_errored": sum(1 for r in recs if "error" in r and not r.get("skipped")),
        "prs_skipped_large": sum(1 for r in recs if r.get("skipped")),
        "anchored_prs": len(anchored),
        "agreed": agreed,
        "precision": round(prec, 3),
        "recall": round(rec_, 3),
        "f1": round(2 * prec * rec_ / (prec + rec_), 3) if prec + rec_ else 0.0,
        "flag_all_precision": round(pos / all_hunks, 3) if all_hunks else 0.0,
        "pr_level_prs": len(pr_level),
        "pr_level_not_focused": sum(1 for r in pr_level if r["verdict"] not in {"FOCUSED", "UNSCORED"}),
        "median_seconds": round(statistics.median([r["seconds"] for r in ok]), 1) if ok else None,
        "median_hunks": statistics.median([r["hunks"] for r in ok]) if ok else None,
        "unjudged_hunks": sum(r["unjudged"] for r in ok),
    }


def write_report() -> None:
    lines = [
        "# ScopeBench results",
        "",
        "Real PRs where a maintainer (owner/member/collaborator) asked for a split or called a change out of scope.",
        "A hit means the tool flagged (cleanup / unrelated / risky) a hunk the maintainer pointed at. Numbers are measured, not tuned on this set.",
        "",
        "| model | PRs | agreed (>=1 objected hunk flagged) | hunk recall | hunk precision (lower bound) | F1 | flag-everything precision | median s/PR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    per_model = {}
    for f in sorted(RESULTS.glob("*.json")):
        data = json.loads(f.read_text())
        agg = aggregate(data["results"])
        per_model[data["name"]] = (data, agg)
        lines.append(
            f"| {data['name']} | {agg['anchored_prs']} | **{agg['agreed']} of {agg['anchored_prs']}** | {agg['recall']:.0%} | {agg['precision']:.0%} | {agg['f1']:.2f} | {agg['flag_all_precision']:.0%} | {agg['median_seconds']} |"
        )
    lines += [
        "",
        "How to read it: *agreed* is the headline (did it point at what the maintainer pointed at). *Precision* counts any flagged hunk the maintainer",
        "did not mention as a miss, so it understates quality. *flag-everything precision* is the dumb baseline: the share of hunks the maintainers objected to.",
    ]
    for name, (data, agg) in per_model.items():
        lines += [
            "",
            f"## {name}",
            "",
            f"PRs without a file-anchored objection (verdict-only check): {agg['pr_level_not_focused']} of {agg['pr_level_prs']} not FOCUSED. "
            f"Skipped as too large: {agg['prs_skipped_large']}. Errored PRs: {agg['prs_errored']}. Unjudged hunks: {agg['unjudged_hunks']}.",
            "",
            "| PR | hunks | objected | flagged | hit | verdict | s |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in data["results"]:
            if "error" in r:
                lines.append(f"| [{r['ref']}]({r['url']}) | error: {r['error'][:60]} | | | | | |")
                continue
            hit = "yes" if set(r["objected"]) & set(r["flagged"]) else ("n/a" if not r["objected"] else "MISS")
            lines.append(
                f"| [{r['ref']}]({r['url']}) | {r['hunks']} | {len(r['objected'])} | {len(r['flagged'])} | {hit} | {r['verdict']} | {r['seconds']} |"
            )
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {HERE / 'RESULTS.md'}")
    write_leaderboard()


def baseline_row(recs: list[dict]) -> dict:
    """The dumb baseline: flag every hunk. Perfect recall, precision equal to the base rate of objected hunks."""
    anchored = [r for r in recs if "error" not in r and r["objected"]]
    pos = sum(len(r["objected"]) for r in anchored)
    total = sum(r["hunks"] for r in anchored)
    prec = pos / total if total else 0.0
    return {
        "name": "flag everything (baseline)",
        "anchored_prs": len(anchored),
        "agreed": len(anchored),
        "recall": 1.0,
        "precision": round(prec, 3),
        "f1": round(2 * prec / (prec + 1), 3) if total else 0.0,
        "median_seconds": 0,
        "pr_level": "-",
    }


def write_leaderboard() -> None:
    """Rank every model that has results on the PRs all of them completed. Ranked by hunk-level F1."""
    all_results = {}
    for f in sorted(RESULTS.glob("*.json")):
        data = json.loads(f.read_text())
        all_results[data["name"]] = data["results"]
    models = {n: r for n, r in all_results.items() if n != "heuristics-only"}
    if not models:
        return
    ok_sets = [{r["ref"] for r in recs if "error" not in r} for recs in models.values()]
    common = set.intersection(*ok_sets) if ok_sets else set()
    rows = []
    for name, recs in {
        **models,
        **({"heuristics-only": all_results["heuristics-only"]} if "heuristics-only" in all_results else {}),
    }.items():
        sub = [r for r in recs if r["ref"] in common]
        agg = aggregate(sub)
        rows.append(
            {
                "name": name,
                "anchored_prs": agg["anchored_prs"],
                "agreed": agg["agreed"],
                "recall": agg["recall"],
                "precision": agg["precision"],
                "f1": agg["f1"],
                "median_seconds": agg["median_seconds"],
                "pr_level": f"{agg['pr_level_not_focused']}/{agg['pr_level_prs']}",
                "model_based": name != "heuristics-only",
            }
        )
    first = next(iter(models.values()))
    base = baseline_row([r for r in first if r["ref"] in common])
    ranked = sorted([r for r in rows if r["model_based"]], key=lambda r: (-r["f1"], -r["agreed"], r["median_seconds"] or 0))
    others = [r for r in rows if not r["model_based"]] + [base]
    L = [
        "# ScopeBench leaderboard",
        "",
        f"Models ranked by hunk-level F1 on the {len(common)} bench PRs every listed model completed (PRs the tool skipped as too large or that errored are excluded for all).",
        "Each PR is analyzed as the maintainer saw it, at the commit they commented on. Same prompt, same settings, temperature 0, one run per model.",
        "",
    ]
    if ranked:
        b = ranked[0]
        tied = [r for r in ranked if b["f1"] - r["f1"] < TIE_MARGIN]
        for r in ranked:
            r["tied_for_best"] = len(tied) > 1 and r in tied
        if len(tied) > 1:
            names = ", ".join(f"`{r['name']}`" for r in tied)
            L += [f"**Best models, tied: {names}** (F1 {b['f1']:.2f}; {b['anchored_prs']} PRs is too few to separate them).", ""]
        else:
            L += [
                f"**Best model: `{b['name']}`** (F1 {b['f1']:.2f}, recall {b['recall']:.0%}, agreed on {b['agreed']} of {b['anchored_prs']} PRs).",
                "",
            ]
    L += [
        "| # | model | agreed (>=1 objected hunk flagged) | hunk recall | hunk precision (lower bound) | F1 | PR-level not-FOCUSED | median s/PR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranked, 1):
        L.append(
            f"| {i} | `{r['name']}` | {r['agreed']} of {r['anchored_prs']} | {r['recall']:.0%} | {r['precision']:.0%} | {r['f1']:.2f} | {r['pr_level']} | {r['median_seconds']} |"
        )
    L += ["", "Baselines (no model):", "", "| | agreed | recall | precision | F1 |", "|---|---|---|---|---|"]
    for r in others:
        L.append(f"| {r['name']} | {r['agreed']} of {r['anchored_prs']} | {r['recall']:.0%} | {r['precision']:.0%} | {r['f1']:.2f} |")
    L += [
        "",
        "Precision is a lower bound: a hunk the maintainer did not mention is counted as a miss even if it is out of scope too.",
        "A model that beats `flag everything` on F1 is doing more than guessing.",
        "",
        "## Add your model",
        "",
        "```bash",
        "uv run python bench/run_eval.py --model <name> --base-url <openai-compatible endpoint>/v1",
        "```",
        "Then commit the new `bench/results/<name>.json` and the regenerated `LEADERBOARD.md` in a PR. Same bench, same prompt.",
        "",
    ]
    (HERE / "leaderboard.json").write_text(json.dumps({"common_prs": sorted(common), "ranked": ranked, "baselines": others}, indent=1))
    (HERE / "LEADERBOARD.md").write_text("\n".join(L))
    print(f"wrote {HERE / 'LEADERBOARD.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--max-hunks", type=int, default=30, help="skip PRs with more hunks than this (model time)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--include-unreviewed", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    if args.report_only:
        write_report()
        return
    prs = [json.loads(x) for x in (HERE / "prs.jsonl").read_text().splitlines()]
    labels = {json.loads(x)["ref"]: json.loads(x) for x in (HERE / "labels.jsonl").read_text().splitlines()}
    todo = [p for p in prs if labels[p["ref"]].get("reviewed") or args.include_unreviewed]
    todo.sort(key=lambda p: p["ref"].split("#")[0])  # same repo together, so its clone can be pruned as soon as it is done
    if args.limit:
        todo = todo[: args.limit]
    name = "heuristics-only" if args.no_model else (args.model or ModelConfig.from_env().model)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}.json"
    prior = json.loads(out.read_text())["results"] if out.exists() else []

    def final(r: dict) -> bool:
        """Finished results stay. A permanent skip stays too, except a 'too large' one that now fits under a raised --max-hunks."""
        if "error" not in r:
            return True
        m = re.match(r"too large: (\d+) hunks", r["error"])
        transient = "fetch -q failed" in r["error"] or "shallow file" in r["error"] or r["error"].startswith("git error")
        return bool(r.get("skipped")) and not transient and not (m and int(m[1]) <= args.max_hunks)  # transient errors are retried

    done = {r["ref"]: r for r in prior if final(r)}
    recs = list(done.values())
    for i, pr in enumerate(todo, 1):
        if pr["ref"] in done:
            continue
        wait_for_memory()
        print(f"[{i}/{len(todo)}] {pr['ref']} ", end="", flush=True)
        rec = evaluate_pr(pr, labels[pr["ref"]], args)
        recs.append(rec)
        print(
            rec.get("error")
            or f"hunks={rec['hunks']} hit={'yes' if set(rec['objected']) & set(rec['flagged']) else 'no'} {rec['seconds']}s",
            flush=True,
        )
        out.write_text(json.dumps({"name": name, "results": recs}, indent=1))  # resumable
        nxt = todo[i]["ref"].split("#")[0] if i < len(todo) else None
        if nxt != pr["ref"].split("#")[0]:
            owner, repo = pr["ref"].split("#")[0].split("/")
            shutil.rmtree(Path(os.environ["SURGEON_CACHE_DIR"]) / f"{owner}__{repo}.git", ignore_errors=True)
    write_report()


if __name__ == "__main__":
    main()
