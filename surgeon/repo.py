"""Read file contents at a revision straight from git objects. No working-tree checkout, nothing written to the repo."""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

MAX_BLOB = 1_000_000


class GitError(RuntimeError):
    pass


class RevReader:
    """Reads files at two revisions (base, head) of a git directory."""

    def __init__(self, git_dir: Path, base: str, head: str):
        self.git_dir, self.base, self.head = Path(git_dir), base, head

    def _git(self, *args: str, input: bytes | None = None) -> bytes:
        p = subprocess.run(["git", "-C", str(self.git_dir), *args], input=input, capture_output=True)
        if p.returncode != 0:
            raise GitError(p.stderr.decode("utf-8", "replace").strip())
        return p.stdout

    def _show(self, rev: str, path: str) -> bytes | None:
        p = subprocess.run(["git", "-C", str(self.git_dir), "cat-file", "blob", f"{rev}:{path}"], capture_output=True)
        return p.stdout if p.returncode == 0 else None

    def read_base(self, path: str) -> bytes | None:
        return self._show(self.base, path)

    def read_head(self, path: str) -> bytes | None:
        return self._show(self.head, path)

    def tree(self, rev: str, exts: set[str]) -> dict[str, bytes]:
        """All files at rev whose extension is in exts (small blobs only), in one batch."""
        listing = self._git("ls-tree", "-r", "-z", "-l", rev).split(b"\0")
        wanted: list[tuple[str, str]] = []
        for entry in listing:
            if not entry:
                continue
            meta, _, path_b = entry.partition(b"\t")
            parts = meta.split()
            if len(parts) < 4 or parts[1] != b"blob":
                continue
            path = path_b.decode("utf-8", "replace")
            size = int(parts[3]) if parts[3].isdigit() else 0
            if size <= MAX_BLOB and os.path.splitext(path)[1].lower() in exts:
                wanted.append((parts[2].decode(), path))
        if not wanted:
            return {}
        out = self._git("cat-file", "--batch", input="".join(f"{oid}\n" for oid, _ in wanted).encode())
        files: dict[str, bytes] = {}
        pos = 0
        for _, path in wanted:
            nl = out.index(b"\n", pos)
            header = out[pos:nl].split()
            size = int(header[2])
            files[path] = out[nl + 1 : nl + 1 + size]
            pos = nl + 1 + size + 1
        return files


def cache_root() -> Path:
    """Where shallow clones live. SURGEON_CACHE_DIR wins; otherwise the XDG cache directory."""
    if os.environ.get("SURGEON_CACHE_DIR"):
        return Path(os.environ["SURGEON_CACHE_DIR"])
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "surgeon"


def _auth_env(token: str | None) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
            GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}",
        )
    return env


def fetch_pr(owner: str, repo: str, number: int, base_sha: str, head_sha: str, token: str | None, cache: Path | None = None) -> RevReader:
    """Shallow-fetch the base commit and the PR head into a cached bare repo. Read-only against GitHub."""
    cache = cache or cache_root()
    git_dir = cache / f"{owner}__{repo}.git"
    env = _auth_env(token)

    def run(*args: str) -> None:
        p = subprocess.run(["git", "-C", str(git_dir), *args], capture_output=True, env=env)
        if p.returncode != 0:
            raise GitError(f"git {' '.join(args[:2])} failed: {p.stderr.decode('utf-8', 'replace').strip()}")

    if not git_dir.exists():
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", str(git_dir)], check=True)
        run("remote", "add", "origin", f"https://github.com/{owner}/{repo}.git")

    def has(sha: str) -> bool:
        return subprocess.run(["git", "-C", str(git_dir), "cat-file", "-e", f"{sha}^{{tree}}"], capture_output=True).returncode == 0

    if not has(base_sha):
        run("fetch", "-q", "--depth=1", "--no-tags", "origin", base_sha)
    if not has(head_sha):
        try:
            run("fetch", "-q", "--depth=1", "--no-tags", "origin", head_sha)
        except GitError:  # not fetchable by sha: the PR ref always has its latest head
            run("fetch", "-q", "--depth=1", "--no-tags", "origin", f"pull/{number}/head")
        if not has(head_sha):
            raise GitError(f"commit {head_sha[:10]} of {owner}/{repo}#{number} is no longer fetchable")
    return RevReader(git_dir, base_sha, head_sha)
