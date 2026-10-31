# Run the ScopeBench model evals on Modal (a GPU container with Ollama) instead of this machine.
#   speed check:  modal run scripts/modal_bench.py --smoke --models gemma3:4b
#   full run:     modal run scripts/modal_bench.py --models gemma3:4b,gemma3:1b,llama3.2:3b --max-hunks 40 --use-gh-token
# --use-gh-token sends `gh auth token` to the container for this call only (GitHub API reads need it; nothing is stored as a Modal secret).
# The local bench/results are copied in, so finished PRs are skipped; the results come back as a tarball and replace bench/results
# (the old ones are kept in .surgeon-cache/). SURGEON_MODAL_GPU=cpu runs on CPU only; the default is a T4 with 4 cores and 16 GB (about $0.9 an hour at list price, billed per second; the 3 h timeout caps one call at about $2.7).
import io
import os
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1] if modal.is_local() else Path("/app")
GPU = os.environ.get("SURGEON_MODAL_GPU", "T4")
SKIP = ["**/.git", "**/.venv", "**/__pycache__", "**/.surgeon-cache", "**/.pytest_cache", "**/.ruff_cache", "PLAN.md"]

image = (
    modal.Image.from_registry("ollama/ollama:latest", add_python="3.12")
    .entrypoint([])
    .apt_install("git", "ca-certificates")
    .pip_install(
        "typer>=0.12",
        "rich>=13",
        "unidiff>=0.7.5",
        "httpx>=0.27",
        "tree-sitter>=0.23",
        "tree-sitter-python>=0.23",
        "tree-sitter-javascript>=0.23",
        "tree-sitter-typescript>=0.23",
        "tree-sitter-java>=0.23.5",
        "tree-sitter-go>=0.25.0",
        "tree-sitter-rust>=0.24.2",
    )
    .env({"PYTHONPATH": "/app", "SURGEON_CACHE_DIR": "/tmp/surgeon-bench-cache", "OLLAMA_MAX_LOADED_MODELS": "1"})
    .add_local_dir(ROOT, "/app", ignore=SKIP)
)
app = modal.App("commit-surgeon-bench", image=image)


def _sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd="/app", **kw)


@app.function(gpu=None if GPU == "cpu" else GPU, cpu=4.0, memory=16384, timeout=3 * 3600)
def bench(models: list[str], max_hunks: int, smoke: bool, token: str, prompt: str = "v1", only_from: str = "") -> dict:
    ollama = subprocess.Popen(["ollama", "serve"], stdout=open("/tmp/ollama.log", "w"), stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=2)
            break
        except OSError:
            time.sleep(1)
    gpu = _sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]).stdout.strip() or "none (CPU)"
    log = [f"gpu: {gpu}"]
    try:
        for m in models:
            log.append(f"pull {m}: {_sh(['ollama', 'pull', m]).returncode}")
            if smoke:
                r = _sh(["ollama", "run", m, "--verbose", "Explain in two sentences what a git rebase does."])
                log += [f"{m}: {line.strip()}" for line in (r.stdout + r.stderr).splitlines() if "eval rate" in line]
                continue
            env = {**os.environ, "GITHUB_TOKEN": token} if token else None
            r = subprocess.run(
                ["python", "bench/run_eval.py", "--model", m, "--max-hunks", str(max_hunks), "--prompt", prompt]
                + (["--only-from", only_from] if only_from else []),
                cwd="/app",
                env=env,
                capture_output=True,
                text=True,
            )
            log.append(f"=== {m} (exit {r.returncode})\n" + "\n".join((r.stdout + r.stderr).splitlines()[-40:]))
        if not smoke:
            _sh(["python", "bench/run_eval.py", "--report-only"])
    finally:
        ollama.terminate()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name in ("results", "RESULTS.md", "LEADERBOARD.md", "leaderboard.json"):
            p = Path("/app/bench") / name
            if p.exists() and not smoke:
                t.add(p, arcname=name)
    return {"log": "\n".join(log), "tar": buf.getvalue()}


@app.local_entrypoint()
def main(
    models: str = "gemma3:4b,gemma3:1b,llama3.2:3b",
    max_hunks: int = 40,
    smoke: bool = False,
    use_gh_token: bool = False,
    prompt: str = "v1",
    only_from: str = "",
):
    token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip() if use_gh_token else ""
    out = bench.remote(models.split(","), max_hunks, smoke, token, prompt, only_from)
    print(out["log"])
    if smoke or not out["tar"]:
        return
    bench_dir = ROOT / "bench"
    bak = ROOT / ".surgeon-cache" / f"results-before-modal-{int(time.time())}"
    bak.mkdir(parents=True)
    if (bench_dir / "results").exists():
        (bench_dir / "results").rename(bak / "results")
    with tarfile.open(fileobj=io.BytesIO(out["tar"]), mode="r:gz") as t:
        t.extractall(bench_dir, filter="data")
    print(f"results written to bench/ (old ones in {bak})")
