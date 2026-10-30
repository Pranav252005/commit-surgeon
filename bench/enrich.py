"""Add the commit and original line a maintainer commented on to bench/labels.jsonl.

A reviewer comments on the PR as it was at one commit; the author may change or remove that code later. The eval
therefore analyzes the PR at the commented commit. This matches each stored objection back to its review comment.

    uv run python bench/enrich.py
"""
from __future__ import annotations

import json
from pathlib import Path

from surgeon.github import GitHub

HERE = Path(__file__).parent


def main() -> None:
    gh = GitHub()
    labels = [json.loads(x) for x in (HERE / "labels.jsonl").read_text().splitlines()]
    changed = 0
    for lab in labels:
        todo = [o for o in lab["objected"] if not o.get("commit")]
        if not todo:
            continue
        owner_repo, n = lab["ref"].split("#")
        r = gh.http.get(f"/repos/{owner_repo}/pulls/{n}/comments", params={"per_page": 100})
        if r.status_code != 200:
            continue
        for o in todo:
            for c in r.json():
                if c.get("path") == o["path"] and (c.get("body") or "").strip().startswith(o["quote"][:60]):
                    o.update(commit=c.get("original_commit_id"), line=c.get("original_line") or c.get("line"), side=c.get("side"))
                    changed += 1
                    break
    (HERE / "labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    missing = sum(1 for lab in labels for o in lab["objected"] if not o.get("commit"))
    print(f"enriched {changed} objections; {missing} still without a commit")


if __name__ == "__main__":
    main()
