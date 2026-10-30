"""Awkward real-world diffs, produced by real git, pushed through the whole local pipeline."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from surgeon import report
from surgeon.diff import parse_patch
from surgeon.judge import Judge, ModelConfig, judge_hunks
from surgeon.local import analyze_local

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
}


def git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True, env=ENV).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "keep.py").write_text("def a():\n    return 1\n")
    (tmp_path / "old_name.py").write_text("".join(f"line {i}\n" for i in range(30)))
    (tmp_path / "gone.py").write_text("x = 1\n")
    (tmp_path / "run.sh").write_text("echo hi\n")
    (tmp_path / "noeol.txt").write_bytes(b"no newline at end")
    (tmp_path / "crlf.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    (tmp_path / "img.bin").write_bytes(b"\x00\x01\x02")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_every_kind_of_change_survives_the_pipeline(repo):
    (repo / "new_pkg").mkdir()
    (repo / "new_pkg/fresh.py").write_text("def fresh():\n    pass\n")  # added
    (repo / "gone.py").unlink()  # deleted
    (repo / "old_name.py").rename(repo / "new_name.py")  # renamed ...
    (repo / "new_name.py").write_text("".join(f"line {i}\n" for i in range(30)).replace("line 15", "line fifteen"))  # ... and edited
    os.chmod(repo / "run.sh", os.stat(repo / "run.sh").st_mode | stat.S_IXUSR)  # mode change only
    (repo / "noeol.txt").write_bytes(b"no newline at end, changed")  # no trailing newline before and after
    (repo / "crlf.py").write_bytes(b"a = 1\r\nb = 3\r\n")  # CRLF
    (repo / "img.bin").write_bytes(b"\x00\x01\x02\x03\xff")  # binary
    (repo / "café ☕.py").write_text("x = 'ünï'\n")  # unicode name and content
    git(repo, "add", "-A")
    a = analyze_local(repo, issue_title="rename things", issue_body="")
    by_path = {f.path: f for f in a.files}
    assert by_path["new_pkg/fresh.py"].status == "added"
    assert by_path["gone.py"].status == "deleted"
    assert by_path["new_name.py"].status == "renamed" and by_path["new_name.py"].old_path == "old_name.py"
    assert by_path["img.bin"].binary and by_path["img.bin"].hunks[0].pseudo
    assert "café ☕.py" in by_path
    assert by_path["run.sh"].hunks[0].pseudo  # mode-only: a pseudo hunk, not a crash
    for h in a.hunks:  # every hunk got a kind and tags; nothing is left half-initialised
        assert h.kind and h.tags
    # judge nothing, but the report must still render and score without a model
    s = report.summarize(a)
    assert s.verdict in {"UNSCORED", "FOCUSED", "SPLIT SUGGESTED", "MOSTLY OUT OF SCOPE"}
    assert report.render_markdown(a, s, None).startswith("<!-- commit-surgeon -->")


def test_pure_rename_is_cleanup_without_a_model(repo):
    (repo / "old_name.py").rename(repo / "renamed.py")
    git(repo, "add", "-A")
    a = analyze_local(repo, issue_title="x")
    h = a.hunks[0]
    assert h.label == "cleanup" and "rename_only" in h.tags


def test_deleting_a_file_attributes_the_hunk_to_the_old_symbols(repo):
    (repo / "keep.py").unlink()
    git(repo, "add", "-A")
    a = analyze_local(repo, issue_title="remove keep.py")
    assert a.files[0].status == "deleted" and a.hunks[0].symbol == "a"


def test_syntax_errors_and_garbage_sources_do_not_break_the_graph(repo):
    (repo / "broken.py").write_text("def (:\n  import\nfrom . import\nclass\n")
    (repo / "binaryish.py").write_bytes(b"\xff\xfe\x00\x00 not utf8 \x80")
    (repo / "weird.ts").write_text("export {{{ from 'x'; import(")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "garbage")
    (repo / "keep.py").write_text("def a():\n    return 2\n")
    git(repo, "add", "-A")
    a = analyze_local(repo, issue_title="x")
    assert a.hunks[0].blast is not None


def test_circular_imports_terminate(repo):
    (repo / "p.py").write_text("import q\n")
    (repo / "q.py").write_text("import p\nimport keep\n")
    (repo / "keep.py").write_text("import p\ndef a():\n    return 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "cycle")
    (repo / "keep.py").write_text("import p\ndef a():\n    return 5\n")
    git(repo, "add", "-A")
    h = analyze_local(repo, issue_title="x").hunks[0]
    assert h.blast["direct"] == 1 and h.blast["transitive"] >= 2


def test_huge_hunk_is_truncated_in_the_prompt():
    from surgeon.judge import build_prompt

    files = parse_patch(
        "diff --git a/big.py b/big.py\nnew file mode 100644\n--- /dev/null\n+++ b/big.py\n@@ -0,0 +1,3000 @@\n"
        + "".join(f"+x{i} = {i}\n" for i in range(3000))
    )
    p = build_prompt(files[0].hunks[0], "pr", "issue", "body " * 5000)
    assert len(p) < 5000 and "hunk truncated" in p


@pytest.mark.parametrize(
    "content", ["", "not json", '{"label": 5}', '{"label": "needed"', "[1,2]", '{"label":"NEEDED ","confidence":"high"}']
)
def test_judge_survives_bad_model_output(tmp_path, content):
    import httpx

    from surgeon.diff import Hunk

    def handler(req):
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    j = Judge(ModelConfig(), tmp_path, httpx.Client(base_url="http://x/v1", transport=httpx.MockTransport(handler)))
    h = Hunk("a#0", "a.py", None, "modified", 0, 1, 1, 1, 0, ["x"], [], [1], [], "@@\n+x\n")
    n = judge_hunks([h], j, "p", "i", "b")
    if content.startswith('{"label":"NEEDED'):  # case and a junk confidence are tolerated
        assert n == 1 and h.label == "needed"
    else:
        assert n == 0 and h.label is None


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
def test_judge_survives_http_errors(tmp_path, status):
    import httpx

    from surgeon.diff import Hunk

    j = Judge(
        ModelConfig(),
        tmp_path,
        httpx.Client(base_url="http://x/v1", transport=httpx.MockTransport(lambda r: httpx.Response(status, json={}))),
    )
    h = Hunk("a#0", "a.py", None, "modified", 0, 1, 1, 1, 0, ["x"], [], [1], [], "@@\n+x\n")
    assert judge_hunks([h], j, "p", "i", "b") == 0 and j.error
