"""Robustness sweep over the bench PRs, no model needed.

For every PR: run the heuristics + import graph pipeline, then split the hunks with random labels and check the
split is lossless (patches apply, and applying them all reproduces the PR head). Random labels exercise every
way hunks can be separated, so any offset or header bug shows up on real diffs.

    uv run python bench/stress.py [--seed 1] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import random
import time
import traceback
from pathlib import Path

from surgeon import pipeline, repo, split
from surgeon.github import GitHub, parse_ref

HERE = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    prs = [json.loads(x) for x in (HERE / "prs.jsonl").read_text().splitlines()]
    if args.limit:
        prs = prs[: args.limit]
    gh = GitHub()
    rng = random.Random(args.seed)
    bad = 0
    for pr in prs:
        t0 = time.perf_counter()
        try:
            a, summary, _ = pipeline.run(pr["ref"], no_model=True, gh=gh)
            for h in a.hunks:
                if h.label is None:
                    h.label = rng.choice(["needed", "cleanup", "unrelated", "needed"])
            plan = split.plan(a)
            ref = parse_ref(pr["ref"])
            reader = repo.fetch_pr(ref.owner, ref.repo, ref.number, a.pr.base_sha, a.pr.head_sha, gh.token)
            split.verify(plan, reader)
            groups = ",".join(f"{g.slug}:{len(g.hunks)}{'' if g.applies else '!'}" for g in plan.groups)
            ok = plan.lossless and all(g.applies for g in plan.groups)
            status = "ok " if ok else "BAD"
            bad += not ok
            print(f"{status} {pr['ref']:42} hunks={len(a.hunks):4} {groups} {round(time.perf_counter() - t0, 1)}s {'' if ok else plan.note}", flush=True)
        except Exception as e:
            bad += 1
            print(f"ERR {pr['ref']:42} {type(e).__name__}: {str(e)[:150]}", flush=True)
            traceback.print_exc(limit=3)
    print(f"\n{len(prs) - bad}/{len(prs)} clean")


if __name__ == "__main__":
    main()
