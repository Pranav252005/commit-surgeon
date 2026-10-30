"""Collect candidate ScopeBench PRs: closed/merged PRs where a maintainer said the PR does too much.

Read-only against GitHub (search + GET). Output: bench/prs.jsonl (candidates with the maintainer's own words)
and bench/labels.jsonl (objected file/line anchors taken from review comments). Candidates need a human glance
before they count: run `python bench/collect.py --review` to print them.

    uv run python bench/collect.py --min-stars 1000 --target 40
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from surgeon.github import GitHub

HERE = Path(__file__).parent
PHRASES = ['"please split"', '"separate PR"', '"out of scope"', '"unrelated changes"', '"split this up"']
TRIGGER = re.compile(
    r"(please split|split (this|it) (up|into)|separate (PR|pull request)|different PR|own PR|out of scope|"
    r"unrelated (change|fix|refactor|to this)|not part of this|should be (done )?in a (separate|different|new))",
    re.I,
)
MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
LANGS = ["python", "javascript", "typescript"]


def search(gh: GitHub, q: str, pages: int) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        r = gh.http.get("/search/issues", params={"q": q, "per_page": 50, "page": page, "sort": "comments"})
        if r.status_code in (403, 422):
            break
        r.raise_for_status()
        items = r.json().get("items", [])
        out += items
        time.sleep(2.2)  # search API: 30 requests/minute
        if len(items) < 50:
            break
    return out


def objections(gh: GitHub, owner: str, repo: str, n: int, author: str) -> list[dict]:
    found: list[dict] = []
    sources = [
        (f"/repos/{owner}/{repo}/pulls/{n}/comments", "review"),
        (f"/repos/{owner}/{repo}/issues/{n}/comments", "issue"),
        (f"/repos/{owner}/{repo}/pulls/{n}/reviews", "review_body"),
    ]
    for url, kind in sources:
        r = gh.http.get(url, params={"per_page": 100})
        if r.status_code != 200:
            continue
        for c in r.json():
            user = c.get("user") or {}
            body = c.get("body") or ""
            if user.get("login") == author or user.get("type") == "Bot" or not TRIGGER.search(body):
                continue
            if c.get("author_association") not in MAINTAINER:
                continue
            found.append(
                {
                    "kind": kind,
                    "by": user.get("login"),
                    "path": c.get("path"),
                    "line": c.get("line") or c.get("original_line"),
                    "side": c.get("side"),
                    "quote": body.strip()[:400],
                    "url": c.get("html_url"),
                }
            )
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-stars", type=int, default=1000)
    ap.add_argument("--target", type=int, default=40)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--max-files", type=int, default=40)
    ap.add_argument("--review", action="store_true", help="print the collected candidates and exit")
    args = ap.parse_args()

    prs_path, labels_path = HERE / "prs.jsonl", HERE / "labels.jsonl"
    if args.review:
        for line in prs_path.read_text().splitlines():
            p = json.loads(line)
            print(f"\n{p['ref']}  {p['title'][:70]}  ({p['files']} files, +{p['additions']}/-{p['deletions']}, {p['state']})")
            for o in p["objections"][:2]:
                print(f"   [{o['kind']}] {o['by']} {o['path'] or ''}:{o['line'] or ''}  {o['quote'][:160]!r}")
        return

    gh = GitHub()
    seen: set[str] = set()
    stars: dict[str, int] = {}
    kept: list[dict] = []
    for lang in LANGS:
        for phrase in PHRASES:
            if len(kept) >= args.target:
                break
            q = f"{phrase} in:comments is:pr is:closed language:{lang} comments:>=2"
            for it in search(gh, q, args.pages):
                if len(kept) >= args.target:
                    break
                owner, repo = it["repository_url"].rsplit("/", 2)[-2:]
                ref = f"{owner}/{repo}#{it['number']}"
                if ref in seen:
                    continue
                seen.add(ref)
                if f"{owner}/{repo}" not in stars:
                    rr = gh.http.get(f"/repos/{owner}/{repo}")
                    stars[f"{owner}/{repo}"] = rr.json().get("stargazers_count", 0) if rr.status_code == 200 else 0
                if stars[f"{owner}/{repo}"] < args.min_stars:
                    continue
                pr = gh.http.get(f"/repos/{owner}/{repo}/pulls/{it['number']}").json()
                if not (2 <= pr.get("changed_files", 0) <= args.max_files) or pr["additions"] + pr["deletions"] > 3000:
                    continue
                objs = objections(gh, owner, repo, it["number"], (pr.get("user") or {}).get("login", ""))
                if not objs:
                    continue
                kept.append(
                    {
                        "ref": ref,
                        "url": pr["html_url"],
                        "title": pr["title"],
                        "state": "merged" if pr.get("merged") else pr["state"],
                        "author": (pr.get("user") or {}).get("login"),
                        "files": pr["changed_files"],
                        "additions": pr["additions"],
                        "deletions": pr["deletions"],
                        "stars": stars[f"{owner}/{repo}"],
                        "objections": objs,
                    }
                )
                print(f"+ {ref} ({len(objs)} objections) [{len(kept)}/{args.target}]", flush=True)

    prs_path.write_text("".join(json.dumps(p) + "\n" for p in kept))
    labels = [
        {
            "ref": p["ref"],
            "reviewed": False,
            "objected": [{"path": o["path"], "line": o["line"], "side": o["side"], "quote": o["quote"][:200]} for o in p["objections"] if o["path"]],
            "pr_level_objection": any(not o["path"] for o in p["objections"]),
        }
        for p in kept
    ]
    labels_path.write_text("".join(json.dumps(x) + "\n" for x in labels))
    print(f"wrote {len(kept)} PRs -> {prs_path.name}, {labels_path.name}")


if __name__ == "__main__":
    main()
