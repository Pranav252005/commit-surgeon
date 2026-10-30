"""Hand curation of bench/labels.jsonl. Auto-collected candidates are noisy ("split" often means "split this long line").

A PR is kept only if a maintainer says the PR (or a specific change in it) belongs in a separate PR / is unrelated /
out of scope. `keep_paths` narrows a PR to the file-anchored comments that really are scope objections.
`pr_level` PRs have no file anchor, so they are scored on the verdict only.

    uv run python bench/curate.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

# ref -> substrings of the comment path that are real scope objections (all other anchored comments are dropped)
ANCHORED = {
    "home-assistant/core#175076": ["config_flow.py"],  # "split this off in a dedicated PR"
    "python/cpython#139123": ["Lib/uuid.py"],  # "let's do it in a separate PR"
    "pandas-dev/pandas#28373": ["whatsnew"],  # "avoid this unrelated change"
    "cockpit-project/cockpit#19024": ["interfaces.js"],  # "split this out into a separate commit"
    "cockpit-project/cockpit#11150": ["po/Makefile.am"],  # "different commit or even a different PR"
    "louislam/uptime-kuma#5916": ["StatusPage.vue"],  # "move unrelated changes to a different PR"
    "sindresorhus/execa#208": ["readme.md"],  # "Don't do unrelated changes."
    "ampproject/amphtml#26085": ["release-schedule.md"],  # "should be in a separate doc"
    "mozilla/pdf.js#9417": ["annotation.js"],  # "free of unrelated changes"
    "vllm-project/vllm#27772": ["config.py"],  # "this PR should focus on loading GGUF mm projector"
    "sympy/sympy#21590": ["rv.py"],  # "Please make a separate PR for these kind of changes"
    "home-assistant/core#80797": ["manifest.json"],  # "I'd prefer to leave that for another PR"
    "home-assistant/core#150886": ["quality_scale.py"],  # "make those changes in a separate PR"
    "home-assistant/core#116267": [".gitignore"],  # "Please don't change this file in this PR"
    "sgl-project/sglang#18306": ["http_server.py"],  # "please detach this API in a separate PR"
    "home-assistant/core#18758": ["tellduslive/__init__.py", "tellduslive/entry.py"],  # "break out device registry support"
    "home-assistant/core#170893": ["manifest.json"],  # "separate PR with the library bump"
    "home-assistant/core#20197": ["tox.ini"],  # "Please make a separate PR for this"
    "home-assistant/core#44091": ["api.py"],  # "Please make a separate PR for these changes"
    "home-assistant/core#50653": ["cover.py"],  # "adding a new platform, out of scope for this PR"
    "ibis-project/ibis#9096": ["generic.py"],  # "validation changes need to go in separately"
    "apache/airflow#21877": ["docker_tests", "taskinstance.py"],  # "make a separate PR ... seems unrelated"
    "home-assistant/core#139857": ["quality_scale.yaml"],  # "separate PR with the quality scale addition"
    "huggingface/transformers#29921": ["configuration_auto.py"],  # "revert unrelated changes"
    "NVIDIA/TensorRT-LLM#13864": ["test_chunked_logits.py"],  # "could revert since it's unrelated"
    "osandov/drgn#129": ["scripts/iwyu.py"],  # "This should be a separate PR"
    "python/cpython#135057": ["http.server.rst"],  # "unrelated change, please revert"
    "home-assistant/core#175902": ["binary_sensor.py", "bosch_shc/__init__.py"],  # "Out of scope" / "not needed for a bump"
    "vllm-project/vllm#7049": ["executor_base.py"],  # "revert if the change is unrelated"
    "sympy/sympy#16890": ["test_solvers.py"],  # "rearrangement should be done in a separate PR"
}
# Maintainer objects at PR level (no file anchor): scored on whether the verdict is not FOCUSED.
PR_LEVEL = {
    "scikit-learn/scikit-learn#522",  # "change to plural form ... in a separate PR"
    "cockpit-project/cockpit#7820",  # "feature creep ... not part of the agreed-upon design"
    "nodejs/node#44710",  # "land most of them as their own PR to keep the changes here minimal"
    "CircuitVerse/CircuitVerse#726",  # "Remove unrelated changes from PR"
    "GoogleChrome/lighthouse#5846",  # "easier to get reviews if we have some smaller chunks"
    "systemd/mkosi#594",  # "splitting the first two commits out into a separate PR"
    "apache/tvm#5812",  # "Please do a separate PR to Docker cpu"
    "matplotlib/matplotlib#3060",  # "Please make a separate PR for that bug"
    "scikit-learn/scikit-learn#1776",  # "make it a separate PR" (the parallel version)
    "pytorch/vision#6269",  # "wonder if it would make sense to split it into smaller ones"
}
# Deliberately not kept: comments where a maintainer agrees to *defer a contributor's idea* ("leave that for
# another PR"). They say nothing about a hunk that is in the PR, so they are not scope objections to evaluate.


def main() -> None:
    labels = [json.loads(x) for x in (HERE / "labels.jsonl").read_text().splitlines()]
    for lab in labels:
        ref = lab["ref"]
        if lab.get("reviewed"):
            continue
        if ref in ANCHORED:
            lab["objected"] = [o for o in lab["objected"] if any(k in (o["path"] or "") for k in ANCHORED[ref])]
            lab["reviewed"] = bool(lab["objected"])
        elif ref in PR_LEVEL:
            lab["objected"] = []
            lab["reviewed"] = True
    (HERE / "labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    kept = [x for x in labels if x["reviewed"]]
    print(f"{len(kept)} reviewed ({sum(1 for x in kept if x['objected'])} anchored, {sum(1 for x in kept if not x['objected'])} PR-level)")


if __name__ == "__main__":
    main()
