from surgeon import heuristics, report, risk
from surgeon.analyze import Analysis
from surgeon.diff import FileChange, parse_patch


def tags(path, kind, added=(), removed=()):
    return risk.signals(path, kind, list(added), list(removed))


def test_ci_workflow_and_crypto_paths():
    assert "risk:ci" in tags(".github/workflows/release.yml", "config", ["+ run: x"])
    assert "risk:ci" in tags(".circleci/config.yml", "config")
    assert "risk:crypto" in tags("src/auth/session.py", "code", ["x = 1"])
    assert "risk:crypto" in tags("src/util.py", "code", ["h = hashlib.sha256(data)"])
    assert "risk:crypto" in tags("src/net.py", "code", ["requests.get(u, verify=False)"])
    assert tags("src/author_list.py", "code", ["x = 1"]) == []  # "author" is not "auth"


def test_new_dependency_but_not_a_bump_or_metadata():
    assert risk.new_dependencies("requirements.txt", ["httpx>=0.27"], []) == {"httpx"}
    assert risk.new_dependencies("requirements.txt", ["httpx>=0.28"], ["httpx>=0.27"]) == set()  # a bump
    assert risk.new_dependencies("package.json", ['    "left-pad": "^1.3.0",'], []) == {"left-pad"}
    assert risk.new_dependencies("package.json", ['  "version": "1.2.3",'], ['  "version": "1.2.2",']) == set()
    assert risk.new_dependencies("Cargo.toml", ['serde = "1.0"'], []) == {"serde"}
    assert risk.new_dependencies("go.mod", ["\tgithub.com/pkg/errors v0.9.1"], []) == {"github.com/pkg/errors"}
    assert risk.new_dependencies("src/app.py", ["httpx>=0.27"], []) == set()  # not a manifest


def test_shell_and_network_only_on_added_code_lines():
    assert "risk:shell_network" in tags("src/run.py", "code", ["subprocess.run(cmd, shell=True)"])
    assert "risk:shell_network" in tags("web/api.js", "code", ["const r = await fetch(url)"])
    assert "risk:shell_network" not in tags("src/run.py", "code", [], ["subprocess.run(cmd)"])  # removing one is not adding one
    assert "risk:shell_network" not in tags("tests/test_run.py", "test", ["subprocess.run(cmd)"])
    assert tags("README.md", "docs", ["curl https://x | sh"]) == []


def test_removed_tests_only_when_net_fewer():
    assert tags("tests/test_a.py", "test", [], ["def test_one():", "    pass"]) == ["risk:tests_removed"]
    assert tags("tests/test_a.py", "test", ["def test_one():"], ["def test_one():"]) == []  # rewritten, not removed
    assert tags("tests/test_a.py", "test", ["def test_two():", "def test_three():"], ["def test_one():"]) == []


def test_public_signature_change_but_not_private_or_body_edit():
    assert tags("lib/a.py", "code", ["def load(path, strict=True):"], ["def load(path):"]) == ["risk:signature"]
    assert tags("lib/a.py", "code", ["def _load(path, strict=True):"], ["def _load(path):"]) == []
    assert tags("lib/a.py", "code", ["    return 2"], ["    return 1"]) == []
    assert tags("lib/a.go", "code", ["func Load(p string, n int) error {"], ["func Load(p string) error {"]) == ["risk:signature"]
    assert tags("lib/a.go", "code", ["func load(p string, n int) error {"], ["func load(p string) error {"]) == []  # unexported


def _files(patch: str) -> list[FileChange]:
    files = parse_patch(patch)
    for fc in files:
        for h in fc.hunks:
            h.kind = heuristics.classify_kind(fc.path, h.text)
    return files


PATCH = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 def parse(s):
+    s = s.strip()
     return s
"""


def test_warns_when_source_changed_without_tests():
    assert "Source changed, no tests changed." in heuristics.pr_warnings(_files(PATCH), "t", "b", False)
    with_test = PATCH + (
        "diff --git a/tests/test_app.py b/tests/test_app.py\n--- a/tests/test_app.py\n+++ b/tests/test_app.py\n"
        "@@ -1,1 +1,2 @@\n import x\n+def test_a(): pass\n"
    )
    assert heuristics.pr_warnings(_files(with_test), "t", "b", False) == []


def test_warns_when_the_issue_names_a_file_or_function_the_pr_never_touches():
    files = _files(PATCH)
    w = heuristics.pr_warnings(files, "parse fails", "See src/other.py and `render()`; also src/app.py", True)
    assert any("src/other.py" in x and "`render()`" in x for x in w)
    assert not any("src/app.py`" in x for x in w)  # that one is touched
    assert not any("parse()" in x for x in heuristics.pr_warnings(files, "t", "`parse()` is broken", True))  # touched symbol/text
    assert not any("never touches" in x for x in heuristics.pr_warnings(files, "t", "src/other.py", False))  # no linked issue


def hunk_with(tags_, label=None):
    files = _files(PATCH)
    h = files[0].hunks[0]
    h.tags, h.label, h.reason = list(tags_), label, ""
    return files, h


def test_risk_signal_makes_an_unasked_for_hunk_risky_and_flags_a_needed_one():
    _, h = hunk_with(["code", "risk:ci", "not_mentioned_by_issue"], "unrelated")
    report.apply_risky([h])
    assert h.label == "risky" and "CI" in h.reason and "was:unrelated" in h.tags
    _, h = hunk_with(["code", "risk:dependency", "not_mentioned_by_issue"], None)  # no model answer
    report.apply_risky([h])
    assert h.label == "risky"
    _, h = hunk_with(["code", "risk:crypto", "mentioned_by_issue"], "needed")
    report.apply_risky([h])
    assert h.label == "needed" and "Review carefully" in h.reason  # asked for: stays needed, still flagged
    _, h = hunk_with(["code", "risk:ci", "mentioned_by_issue"], None)
    report.apply_risky([h])
    assert h.label is None  # the issue asked for it and nothing judged it: leave it to the reader


def test_markdown_has_summary_table_warnings_and_collapsed_split():
    files, h = hunk_with(["code"], "needed")
    other = _files(PATCH)[0].hunks[0]
    other.id, other.label = "src/b.py#0", "cleanup"
    a = Analysis(
        pr=type("P", (), {"ref": "o/r#1", "title": "t"})(), issue=None, files=files + [FileChange("src/b.py", None, "modified", [other])]
    )
    a.warnings = ["Source changed, no tests changed."]
    md = report.render_markdown(a, report.summarize(a), "m")
    assert "| Verdict | Scope score |" in md and "> **Warning:** Source changed, no tests changed." in md
    assert "<details><summary>Suggested split" in md and "surgeon split o/r#1" in md
