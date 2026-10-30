import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from surgeon.cli import app
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
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/dates.py").write_text("def parse(x):\n    return x+1\n\n\ndef fmt(x):\n    return str(x)\n")
    for i in range(6):
        (tmp_path / f"user{i}.py").write_text("from pkg.dates import parse\nprint(parse(1))\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_staged_whitespace_and_real_change(repo):
    (repo / "pkg/dates.py").write_text("def parse(x):\n    return x + 1\n\n\ndef fmt(x):\n    return str(x) + '!'\n")
    git(repo, "add", "-A")
    a = analyze_local(repo, issue_title="fmt should append a bang", issue_body="`fmt` in pkg/dates.py")
    assert a.pr.ref == "local:staged" and len(a.hunks) == 1  # both edits land in one 3-line-context hunk
    h = a.hunks[0]
    assert h.blast["direct_non_test"] == 6  # six files import pkg.dates
    assert "mentioned_by_issue" in h.tags


def test_user_git_config_cannot_change_paths(repo):
    git(repo, "config", "diff.mnemonicPrefix", "true")  # makes `git diff --cached` print c/ and w/ prefixes
    (repo / "pkg/dates.py").write_text("def parse(x):\n    return x + 3\n\n\ndef fmt(x):\n    return str(x)\n")
    git(repo, "add", "-A")
    a = analyze_local(repo, issue_title="x")
    assert a.hunks[0].path == "pkg/dates.py" and a.hunks[0].blast["direct"] == 6


def test_non_ascii_path(repo):
    (repo / "café.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    assert [h.path for h in analyze_local(repo, issue_title="x").hunks] == ["café.py"]


def test_nothing_staged_is_an_error(repo):
    with pytest.raises(ValueError, match="nothing to check"):
        analyze_local(repo)


def test_against_base_ref(repo):
    git(repo, "switch", "-qc", "feature")
    (repo / "user0.py").write_text("from pkg.dates import parse\nprint(parse(2))\n")
    git(repo, "commit", "-qam", "tweak user0")
    a = analyze_local(repo, against="main", issue_title="user0 prints 2")
    assert a.pr.ref == "local:main...HEAD" and [h.path for h in a.hunks] == ["user0.py"]


def test_cli_json_for_agents_and_fail_under(repo):
    (repo / "pkg/dates.py").write_text("def parse(x):\n    return x + 1\n\n\ndef fmt(x):\n    return str(x)\n")  # whitespace-only
    git(repo, "add", "-A")
    r = CliRunner().invoke(app, ["check", "--repo", str(repo), "--no-model", "--json", "-", "--issue-title", "x"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert data["summary"]["verdict"] == "UNSCORED" or data["summary"]["score"] is not None
    assert data["hunks"][0]["label"] == "cleanup" and "whitespace_only" in data["hunks"][0]["tags"]


def test_cli_nothing_staged_exits_2(repo):
    r = CliRunner().invoke(app, ["check", "--repo", str(repo), "--no-model"])
    assert r.exit_code == 2 and "nothing to check" in r.output
