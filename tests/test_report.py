from surgeon import report
from surgeon.analyze import Analysis
from surgeon.diff import Hunk


def hunk(id, label, added=10, removed=0, kind="code", tags=None, blast=None, pseudo=False):
    h = Hunk(id, id.split("#")[0], None, "modified", 0, 1, 1, added, removed, [], [], [], [], "", kind=kind, tags=tags or [kind], label=label, blast=blast, pseudo=pseudo)
    return h


def analysis(hunks):
    from surgeon.diff import FileChange

    return Analysis(pr=None, issue=None, files=[FileChange("x", None, "modified", hunks)])


SHARED = {"direct": 9, "direct_non_test": 8, "symbol_importers": 5, "evidence": "imported by 9"}


def test_risky_only_for_stray_changes_in_shared_code():
    hs = [
        hunk("a.py#0", "unrelated", blast=SHARED),
        hunk("b.py#0", "needed", blast=SHARED),  # needed stays needed however shared it is
        hunk("c.py#0", "cleanup", blast={**SHARED, "symbol_importers": 0}),  # private symbol: nobody outside uses it
        hunk("d.py#0", "cleanup", blast={"direct_non_test": 2, "direct": 2}),  # few importers
        hunk("e.py#0", "cleanup", tags=["code", "whitespace_only"], blast=SHARED),  # reformatting cannot break importers
        hunk("f.py#0", "cleanup", kind="docs", tags=["docs"], blast=SHARED),
    ]
    report.apply_risky(hs)
    assert [h.label for h in hs] == ["risky", "needed", "cleanup", "cleanup", "cleanup", "cleanup"]
    assert "was:unrelated" in hs[0].tags and "imported by 9" in hs[0].reason


def test_score_and_verdict_thresholds():
    s = report.summarize(analysis([hunk("a#0", "needed", 95), hunk("b#0", "cleanup", 5)]))
    assert (s.score, s.verdict) == (95, "FOCUSED")
    s = report.summarize(analysis([hunk("a#0", "needed", 70), hunk("b#0", "unrelated", 30)]))
    assert (s.score, s.verdict) == (70, "SPLIT SUGGESTED")
    s = report.summarize(analysis([hunk("a#0", "needed", 10), hunk("b#0", "unrelated", 90)]))
    assert (s.score, s.verdict) == (10, "MOSTLY OUT OF SCOPE")


def test_ancillary_and_unjudged_do_not_count_and_partial_is_flagged():
    s = report.summarize(analysis([hunk("a#0", "needed", 10), hunk("lock#0", "ancillary", 500, kind="lockfile"), hunk("c#0", None, 40)]))
    assert s.score == 100 and s.judged_lines == 10 and s.partial


def test_nothing_judged_is_unscored_not_a_crash():
    s = report.summarize(analysis([hunk("a#0", None, 5)]))
    assert s.verdict == "UNSCORED" and s.score is None


def test_markdown_has_verdict_groups_and_footer():
    a = analysis([hunk("a.py#0", "needed", 9), hunk("b.py#0", "cleanup", 1)])
    from surgeon.github import PRInfo

    a.pr = PRInfo("o/r#1", "Fix it", "", "u", "open", "main", "b", "h", 2, 10, 0, "")
    md = report.render_markdown(a, report.summarize(a), "gemma3:4b")
    assert "## Commit Surgeon: FOCUSED" in md and "### Needed for the issue (1)" in md and "### Cleanup" in md and "never blocks" in md
