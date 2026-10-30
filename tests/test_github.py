import httpx
import pytest

from surgeon.github import GitHub, PRRef, parse_ref


def client(routes: dict):
    def handler(req: httpx.Request) -> httpx.Response:
        for key, resp in routes.items():
            if req.url.path == key or req.url.path.startswith(key):
                return resp(req) if callable(resp) else resp
        return httpx.Response(404, json={"message": "Not Found"})

    return GitHub(token="x", client=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)))


PULL = {
    "title": "Fix crash",
    "body": "Fixes #5",
    "user": {"login": "u"},
    "state": "closed",
    "merged": True,
    "base": {"ref": "main", "sha": "TIP"},
    "head": {"sha": "HEAD"},
    "changed_files": 1,
    "additions": 2,
    "deletions": 1,
    "html_url": "https://github.com/o/r/pull/9",
}
ISSUE = {"title": "Crash", "body": "it crashes", "html_url": "https://github.com/o/r/issues/5"}


@pytest.mark.parametrize(
    "text",
    ["o/r#9", "https://github.com/o/r/pull/9", "https://github.com/o/r/pull/9/files", "  o/r#9  "],
)
def test_parse_ref_accepts_common_forms(text):
    assert parse_ref(text) == PRRef("o", "r", 9)


@pytest.mark.parametrize("text", ["o/r", "#9", "https://github.com/o/r/issues/9", "o/r#x", ""])
def test_parse_ref_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_ref(text)


def test_pr_diff_base_is_the_merge_base_not_the_branch_tip():
    gh = client(
        {
            "/repos/o/r/pulls/9": httpx.Response(200, json=PULL),
            "/repos/o/r/compare/": httpx.Response(200, json={"merge_base_commit": {"sha": "MB"}}),
        }
    )
    pr = gh.pr(PRRef("o", "r", 9))
    assert pr.base_sha == "MB" and pr.base_tip_sha == "TIP" and pr.head_sha == "HEAD" and pr.state == "merged"


def test_falls_back_to_the_tip_when_compare_fails():
    gh = client({"/repos/o/r/pulls/9": httpx.Response(200, json=PULL), "/repos/o/r/compare/": httpx.Response(500)})
    assert gh.pr(PRRef("o", "r", 9)).base_sha == "TIP"


@pytest.mark.parametrize(
    "body, repo, number",
    [
        ("Fixes #5", "o/r", 5),
        ("closes: #5", "o/r", 5),
        ("This resolves #5.", "o/r", 5),
        ("Fixes other/repo#7", "other/repo", 7),
        ("Fixes https://github.com/x/y/issues/12", "x/y", 12),
    ],
)
def test_linked_issue_closing_keywords(body, repo, number):
    seen = []

    def issue(req):
        seen.append(req.url.path)
        return httpx.Response(200, json=ISSUE)

    gh = client({"/repos/": issue})
    from surgeon.github import PRInfo

    info = PRInfo("o/r#9", "t", body, "u", "open", "main", "b", "h", 1, 1, 1, "")
    got = gh.linked_issue(PRRef("o", "r", 9), info)
    assert got and got.source == "closing-keyword" and seen == [f"/repos/{repo}/issues/{number}"]


def test_issue_that_is_really_a_pr_is_ignored_and_mention_is_the_last_resort():
    from surgeon.github import PRInfo

    def route(req):
        n = req.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={**ISSUE, "pull_request": {}} if n == "5" else ISSUE)

    gh = GitHub(token=None, client=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(route)))
    info = PRInfo("o/r#9", "t", "Fixes #5, see also #6 and #9", "u", "open", "main", "b", "h", 1, 1, 1, "")
    got = gh.linked_issue(PRRef("o", "r", 9), info)
    assert got and got.number == 6 and got.source == "mention"  # #5 is a PR, #9 is the PR itself


def test_no_issue_at_all_returns_none():
    from surgeon.github import PRInfo

    gh = client({})
    info = PRInfo("o/r#9", "Refactor", "no links here", "u", "open", "main", "b", "h", 1, 1, 1, "")
    assert gh.linked_issue(PRRef("o", "r", 9), info) is None


def test_errors_are_readable():
    gh = client({"/repos/o/r/pulls/1": httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={})})
    with pytest.raises(RuntimeError, match="rate limit"):
        gh.pr(PRRef("o", "r", 1))
    with pytest.raises(LookupError, match="not found"):
        gh.pr(PRRef("o", "r", 2))
