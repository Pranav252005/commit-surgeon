import subprocess
from pathlib import Path

from surgeon import split
from surgeon.analyze import Analysis
from surgeon.diff import parse_patch
from surgeon.repo import RevReader


def git(d: Path, *a: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True, env=env).stdout


def make_repo(tmp_path: Path):
    body = [f"line {i}\n" for i in range(1, 61)]
    (tmp_path / "a.py").write_text("".join(body))
    (tmp_path / "b.py").write_text("x = 1\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    body.insert(5, "line 5b added by the fix\n")  # hunk 0: the fix, adds a line so later hunks shift
    body[30] = "line 31 tidied\n"  # hunk 1: cleanup
    body.insert(50, "brand new feature\n")  # hunk 2: unrelated, shifts later lines
    (tmp_path / "a.py").write_text("".join(body))
    (tmp_path / "c.py").write_text("print('new')\n")  # a whole new file, unrelated
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "head")
    head = git(tmp_path, "rev-parse", "HEAD").strip()
    diff = git(tmp_path, "diff", base, head)
    return RevReader(tmp_path / ".git", base, head), diff


def test_split_is_lossless_and_each_patch_applies(tmp_path):
    reader, diff = make_repo(tmp_path)
    files = parse_patch(diff)
    a = Analysis(pr=None, issue=None, files=files)
    hunks = {h.id: h for h in a.hunks}
    assert len(hunks) == 4
    hunks["a.py#0"].label = "needed"
    hunks["a.py#1"].label = "cleanup"
    hunks["a.py#2"].label = "unrelated"
    hunks["c.py#0"].label = "unrelated"
    p = split.plan(a)
    assert [g.slug for g in p.groups] == ["fix", "cleanup", "unrelated"]
    split.verify(p, reader)
    assert all(g.applies for g in p.groups), [g.note for g in p.groups]
    assert p.lossless, p.note
    # the unrelated patch leaves out the fix's inserted line, so its new-side start must drop back to the base position
    import re

    unrelated = next(g for g in p.groups if g.slug == "unrelated").patch
    a_hdr = re.search(r"^@@ -(\d+),\d+ \+(\d+),\d+ @@", unrelated.split("diff --git a/c.py")[0], re.M)
    assert a_hdr and a_hdr[1] == a_hdr[2], unrelated
    orig = re.search(r"^@@ -(\d+),\d+ \+(\d+),\d+ @@", hunks["a.py#2"].text, re.M)
    assert orig[1] != orig[2]  # in the full PR the same hunk is shifted by the fix


def test_unplaced_hunks_make_the_series_incomplete(tmp_path):
    reader, diff = make_repo(tmp_path)
    a = Analysis(pr=None, issue=None, files=parse_patch(diff))
    for h in a.hunks:
        h.label = "needed"
    a.hunks[0].label = None  # unjudged
    p = split.plan(a)
    split.verify(p, reader)
    assert p.skipped and p.lossless is False


def test_binary_files_are_listed_not_patched_and_the_rest_is_still_lossless(tmp_path):
    reader, diff = make_repo(tmp_path)
    git(tmp_path, "checkout", "-q", reader.head)
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "add binary")
    head2 = git(tmp_path, "rev-parse", "HEAD").strip()
    reader2 = RevReader(tmp_path / ".git", reader.base, head2)
    text_diff = git(tmp_path, "diff", reader.base, head2)  # no --binary: what GitHub's .diff gives us
    a = Analysis(pr=None, issue=None, files=parse_patch(text_diff))
    for h in a.hunks:
        h.label = "needed"
    p = split.plan(a)
    assert p.binary == ["logo.png"]
    split.verify(p, reader2)
    assert all(g.applies for g in p.groups)
    assert p.lossless and "binary" in p.note
