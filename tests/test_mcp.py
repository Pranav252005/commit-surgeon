import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
}


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True, env=ENV).stdout


def test_server_lists_and_runs_the_tool_over_stdio(tmp_path: Path):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "m.py").write_text("def f():\n    return 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "m.py").write_text("def f():\n    return 2\n")
    git(tmp_path, "add", "-A")

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "surgeon.cli", "mcp"])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert [t.name for t in tools.tools] == ["check_scope"]
            res = await session.call_tool("check_scope", {"repo_dir": str(tmp_path), "issue_title": "f returns 2", "use_model": False})
            return res

    res = asyncio.run(go())
    assert not res.is_error
    data = json.loads(res.content[0].text) if res.content else res.structured_content
    assert data["verdict"] == "UNSCORED" and data["hunks"][0]["path"] == "m.py"
