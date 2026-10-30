"""Read-only GitHub access. Only GET requests and one GraphQL query; never writes to other people's repos."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass

import httpx

API = "https://api.github.com"
_REF_RE = re.compile(r"^(?P<o>[\w.-]+)/(?P<r>[\w.-]+)#(?P<n>\d+)$")
_URL_RE = re.compile(r"github\.com/(?P<o>[\w.-]+)/(?P<r>[\w.-]+)/pull/(?P<n>\d+)")
_CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+"
    r"(?:(?P<repo>[\w.-]+/[\w.-]+)#|https://github\.com/(?P<urepo>[\w.-]+/[\w.-]+)/issues/|#)(?P<n>\d+)",
    re.I,
)
_MENTION_RE = re.compile(r"(?<![\w/])#(\d+)\b")


@dataclass
class PRRef:
    owner: str
    repo: str
    number: int

    def __str__(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


@dataclass
class PRInfo:
    ref: str
    title: str
    body: str
    author: str
    state: str
    base_ref: str
    base_sha: str  # the commit the PR diff is against: the merge base, falling back to the base branch tip
    head_sha: str
    changed_files: int
    additions: int
    deletions: int
    url: str
    base_tip_sha: str = ""  # where the base branch pointed when the PR was last updated


@dataclass
class IssueInfo:
    repo: str
    number: int
    title: str
    body: str
    source: str  # closing-keyword | graphql | mention
    url: str

    def as_dict(self) -> dict:
        return asdict(self)


def parse_ref(text: str) -> PRRef:
    text = text.strip()
    m = _REF_RE.match(text) or _URL_RE.search(text)
    if not m:
        raise ValueError(f"not a PR reference: {text!r} (use owner/repo#123 or a PR URL)")
    return PRRef(m["o"], m["r"], int(m["n"]))


def get_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


class GitHub:
    def __init__(self, token: str | None = None, client: httpx.Client | None = None):
        self.token = token if token is not None else get_token()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "commit-surgeon"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.http = client or httpx.Client(base_url=API, headers=headers, timeout=30, follow_redirects=True)

    def _get(self, path: str, **kw) -> httpx.Response:
        r = self.http.get(path, **kw)
        if r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0":
            raise RuntimeError("GitHub rate limit hit; set GITHUB_TOKEN or run `gh auth login`")
        if r.status_code == 404:
            raise LookupError(f"not found: {path} (private repo or wrong reference?)")
        r.raise_for_status()
        return r

    def pr(self, ref: PRRef) -> PRInfo:
        d = self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}").json()
        tip, head = d["base"]["sha"], d["head"]["sha"]
        return PRInfo(
            ref=str(ref),
            title=d["title"],
            body=d.get("body") or "",
            author=(d.get("user") or {}).get("login", ""),
            state="merged" if d.get("merged") else d["state"],
            base_ref=d["base"]["ref"],
            base_sha=self._merge_base(ref, tip, head) or tip,
            head_sha=head,
            changed_files=d["changed_files"],
            additions=d["additions"],
            deletions=d["deletions"],
            url=d["html_url"],
            base_tip_sha=tip,
        )

    def _merge_base(self, ref: PRRef, tip: str, head: str) -> str | None:
        """GitHub's PR diff is against the merge base, which differs from the base tip once the base branch moved on."""
        try:
            r = self.http.get(f"/repos/{ref.owner}/{ref.repo}/compare/{tip}...{head}", params={"per_page": 1})
            r.raise_for_status()
            return r.json()["merge_base_commit"]["sha"]
        except (httpx.HTTPError, KeyError, ValueError):
            return None

    def diff(self, ref: PRRef) -> str:
        r = self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}", headers={"Accept": "application/vnd.github.v3.diff"})
        return r.text

    def issue(self, repo: str, number: int, source: str) -> IssueInfo | None:
        try:
            d = self._get(f"/repos/{repo}/issues/{number}").json()
        except LookupError:
            return None
        if "pull_request" in d:  # a PR number, not an issue
            return None
        return IssueInfo(repo, number, d["title"], (d.get("body") or "")[:6000], source, d["html_url"])

    def linked_issue(self, ref: PRRef, pr: PRInfo) -> IssueInfo | None:
        """Closing keyword in title/body, then GitHub's own closing references, then a plain #N mention."""
        text = f"{pr.title}\n{pr.body}"
        m = _CLOSING_RE.search(text)
        if m:
            repo = m["repo"] or m["urepo"] or f"{ref.owner}/{ref.repo}"
            found = self.issue(repo, int(m["n"]), "closing-keyword")
            if found:
                return found
        if self.token:
            found = self._graphql_closing(ref)
            if found:
                return found
        for n in _MENTION_RE.findall(text):
            if int(n) == ref.number:
                continue
            found = self.issue(f"{ref.owner}/{ref.repo}", int(n), "mention")
            if found:
                return found
        return None

    def _graphql_closing(self, ref: PRRef) -> IssueInfo | None:
        q = (
            "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n)"
            "{closingIssuesReferences(first:1){nodes{number title body url repository{nameWithOwner}}}}}}"
        )
        try:
            r = self.http.post("/graphql", json={"query": q, "variables": {"o": ref.owner, "r": ref.repo, "n": ref.number}})
            nodes = r.json()["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None
        if not nodes:
            return None
        n = nodes[0]
        return IssueInfo(n["repository"]["nameWithOwner"], n["number"], n["title"], (n.get("body") or "")[:6000], "graphql", n["url"])
