# ScopeBench results

Real PRs where a maintainer (owner/member/collaborator) asked for a split or called a change out of scope.
A hit means the tool flagged (cleanup / unrelated / risky) a hunk the maintainer pointed at. Numbers are measured, not tuned on this set.

| model | PRs | agreed (>=1 objected hunk flagged) | hunk recall | hunk precision (lower bound) | F1 | flag-everything precision | median s/PR |
|---|---|---|---|---|---|---|---|
| gemma3:1b | 15 | **7 of 15** | 39% | 14% | 0.21 | 7% | 111.5 |
| gemma3:4b | 14 | **5 of 14** | 35% | 13% | 0.19 | 7% | 134.0 |
| heuristics-only | 22 | **2 of 22** | 7% | 4% | 0.05 | 4% | 22.9 |
| llama3.2:3b | 15 | **13 of 15** | 89% | 7% | 0.14 | 7% | 47.8 |

How to read it: *agreed* is the headline (did it point at what the maintainer pointed at). *Precision* counts any flagged hunk the maintainer
did not mention as a miss, so it understates quality. *flag-everything precision* is the dumb baseline: the share of hunks the maintainers objected to.

## gemma3:1b

PRs without a file-anchored objection (verdict-only check): 5 of 5 not FOCUSED. Skipped as too large: 20. Errored PRs: 0. Unjudged hunks: 200.

| PR | hunks | objected | flagged | hit | verdict | s |
|---|---|---|---|---|---|---|
| [CircuitVerse/CircuitVerse#726](https://github.com/CircuitVerse/CircuitVerse/pull/726) | 10 | 0 | 1 | n/a | MOSTLY OUT OF SCOPE | 104.0 |
| [GoogleChrome/lighthouse#5846](https://github.com/GoogleChrome/lighthouse/pull/5846) | 25 | 0 | 7 | n/a | MOSTLY OUT OF SCOPE | 216.4 |
| [home-assistant/core#139857](https://github.com/home-assistant/core/pull/139857) | 14 | 1 | 3 | yes | MOSTLY OUT OF SCOPE | 266.8 |
| [huggingface/transformers#29921](https://github.com/huggingface/transformers/pull/29921) | error: too large: 49 hunks to judge (limit 40) | | | | | |
| [louislam/uptime-kuma#5916](https://github.com/louislam/uptime-kuma/pull/5916) | 25 | 1 | 0 | MISS | FOCUSED | 35.1 |
| [matplotlib/matplotlib#3060](https://github.com/matplotlib/matplotlib/pull/3060) | error: too large: 84 hunks to judge (limit 40) | | | | | |
| [mozilla/pdf.js#9417](https://github.com/mozilla/pdf.js/pull/9417) | error: too large: 54 hunks to judge (limit 40) | | | | | |
| [nodejs/node#44710](https://github.com/nodejs/node/pull/44710) | error: too large: 92 hunks to judge (limit 40) | | | | | |
| [osandov/drgn#129](https://github.com/osandov/drgn/pull/129) | error: too large: 46 hunks to judge (limit 40) | | | | | |
| [pandas-dev/pandas#28373](https://github.com/pandas-dev/pandas/pull/28373) | 19 | 1 | 7 | MISS | MOSTLY OUT OF SCOPE | 43.3 |
| [python/cpython#139123](https://github.com/python/cpython/pull/139123) | 28 | 1 | 7 | MISS | MOSTLY OUT OF SCOPE | 88.9 |
| [python/cpython#135057](https://github.com/python/cpython/pull/135057) | 17 | 1 | 2 | yes | MOSTLY OUT OF SCOPE | 81.3 |
| [pytorch/vision#6269](https://github.com/pytorch/vision/pull/6269) | 12 | 0 | 3 | n/a | MOSTLY OUT OF SCOPE | 39.4 |
| [scikit-learn/scikit-learn#522](https://github.com/scikit-learn/scikit-learn/pull/522) | 7 | 0 | 2 | n/a | MOSTLY OUT OF SCOPE | 25.4 |
| [scikit-learn/scikit-learn#1776](https://github.com/scikit-learn/scikit-learn/pull/1776) | 16 | 0 | 3 | n/a | MOSTLY OUT OF SCOPE | 52.9 |
| [sgl-project/sglang#18306](https://github.com/sgl-project/sglang/pull/18306) | error: commit unavailable: not found: /repos/sgl-project/sglang/com | | | | | |
| [sindresorhus/execa#208](https://github.com/sindresorhus/execa/pull/208) | 9 | 3 | 3 | yes | MOSTLY OUT OF SCOPE | 24.7 |
| [sympy/sympy#21590](https://github.com/sympy/sympy/pull/21590) | error: too large: 41 hunks to judge (limit 40) | | | | | |
| [sympy/sympy#16890](https://github.com/sympy/sympy/pull/16890) | error: commit unavailable: not found: /repos/sympy/sympy/compare/8a | | | | | |
| [systemd/mkosi#594](https://github.com/systemd/mkosi/pull/594) | error: too large: 52 hunks to judge (limit 40) | | | | | |
| [vllm-project/vllm#27772](https://github.com/vllm-project/vllm/pull/27772) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
| [vllm-project/vllm#7049](https://github.com/vllm-project/vllm/pull/7049) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
| [NVIDIA/TensorRT-LLM#13864](https://github.com/NVIDIA/TensorRT-LLM/pull/13864) | error: too large: 144 hunks to judge (limit 40) | | | | | |
| [ampproject/amphtml#26085](https://github.com/ampproject/amphtml/pull/26085) | 2 | 1 | 0 | MISS | UNSCORED | 90.0 |
| [apache/airflow#21877](https://github.com/apache/airflow/pull/21877) | error: commit unavailable: not found: /repos/apache/airflow/compare | | | | | |
| [apache/tvm#5812](https://github.com/apache/tvm/pull/5812) | error: too large: 43 hunks to judge (limit 40) | | | | | |
| [cockpit-project/cockpit#19024](https://github.com/cockpit-project/cockpit/pull/19024) | 18 | 1 | 1 | MISS | SPLIT SUGGESTED | 156.5 |
| [cockpit-project/cockpit#11150](https://github.com/cockpit-project/cockpit/pull/11150) | error: commit unavailable: not found: /repos/cockpit-project/cockpi | | | | | |
| [cockpit-project/cockpit#7820](https://github.com/cockpit-project/cockpit/pull/7820) | error: too large: 76 hunks to judge (limit 40) | | | | | |
| [home-assistant/core#175076](https://github.com/home-assistant/core/pull/175076) | 20 | 1 | 1 | yes | MOSTLY OUT OF SCOPE | 224.2 |
| [home-assistant/core#80797](https://github.com/home-assistant/core/pull/80797) | error: too large: 51 hunks to judge (limit 40) | | | | | |
| [home-assistant/core#150886](https://github.com/home-assistant/core/pull/150886) | 20 | 1 | 1 | MISS | MOSTLY OUT OF SCOPE | 228.4 |
| [home-assistant/core#116267](https://github.com/home-assistant/core/pull/116267) | 18 | 1 | 4 | MISS | MOSTLY OUT OF SCOPE | 173.0 |
| [home-assistant/core#18758](https://github.com/home-assistant/core/pull/18758) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#170893](https://github.com/home-assistant/core/pull/170893) | 24 | 1 | 11 | yes | MOSTLY OUT OF SCOPE | 252.3 |
| [home-assistant/core#20197](https://github.com/home-assistant/core/pull/20197) | 8 | 1 | 0 | MISS | FOCUSED | 119.1 |
| [home-assistant/core#44091](https://github.com/home-assistant/core/pull/44091) | 15 | 1 | 4 | yes | MOSTLY OUT OF SCOPE | 159.5 |
| [home-assistant/core#50653](https://github.com/home-assistant/core/pull/50653) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#175902](https://github.com/home-assistant/core/pull/175902) | 35 | 2 | 5 | yes | MOSTLY OUT OF SCOPE | 440.4 |
| [ibis-project/ibis#9096](https://github.com/ibis-project/ibis/pull/9096) | error: too large: 51 hunks to judge (limit 40) | | | | | |

## gemma3:4b

PRs without a file-anchored objection (verdict-only check): 4 of 5 not FOCUSED. Skipped as too large: 21. Errored PRs: 0. Unjudged hunks: 0.

| PR | hunks | objected | flagged | hit | verdict | s |
|---|---|---|---|---|---|---|
| [CircuitVerse/CircuitVerse#726](https://github.com/CircuitVerse/CircuitVerse/pull/726) | 10 | 0 | 6 | n/a | MOSTLY OUT OF SCOPE | 49.2 |
| [NVIDIA/TensorRT-LLM#13864](https://github.com/NVIDIA/TensorRT-LLM/pull/13864) | error: too large: 144 hunks to judge (limit 20) | | | | | |
| [ampproject/amphtml#26085](https://github.com/ampproject/amphtml/pull/26085) | 2 | 1 | 0 | MISS | FOCUSED | 70.2 |
| [apache/airflow#21877](https://github.com/apache/airflow/pull/21877) | error: commit unavailable: not found: /repos/apache/airflow/compare | | | | | |
| [apache/tvm#5812](https://github.com/apache/tvm/pull/5812) | error: too large: 43 hunks to judge (limit 20) | | | | | |
| [cockpit-project/cockpit#19024](https://github.com/cockpit-project/cockpit/pull/19024) | 18 | 1 | 7 | yes | SPLIT SUGGESTED | 111.6 |
| [cockpit-project/cockpit#11150](https://github.com/cockpit-project/cockpit/pull/11150) | error: commit unavailable: not found: /repos/cockpit-project/cockpi | | | | | |
| [cockpit-project/cockpit#7820](https://github.com/cockpit-project/cockpit/pull/7820) | error: too large: 76 hunks to judge (limit 20) | | | | | |
| [GoogleChrome/lighthouse#5846](https://github.com/GoogleChrome/lighthouse/pull/5846) | 25 | 0 | 6 | n/a | FOCUSED | 149.1 |
| [home-assistant/core#175076](https://github.com/home-assistant/core/pull/175076) | 20 | 1 | 2 | MISS | FOCUSED | 84.9 |
| [home-assistant/core#80797](https://github.com/home-assistant/core/pull/80797) | error: too large: 51 hunks to judge (limit 40) | | | | | |
| [home-assistant/core#150886](https://github.com/home-assistant/core/pull/150886) | 20 | 1 | 1 | MISS | FOCUSED | 164.8 |
| [home-assistant/core#116267](https://github.com/home-assistant/core/pull/116267) | 18 | 1 | 1 | yes | FOCUSED | 144.9 |
| [home-assistant/core#18758](https://github.com/home-assistant/core/pull/18758) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#170893](https://github.com/home-assistant/core/pull/170893) | 24 | 1 | 5 | yes | FOCUSED | 326.7 |
| [home-assistant/core#44091](https://github.com/home-assistant/core/pull/44091) | 15 | 1 | 7 | MISS | FOCUSED | 134.0 |
| [home-assistant/core#50653](https://github.com/home-assistant/core/pull/50653) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#139857](https://github.com/home-assistant/core/pull/139857) | error: commit unavailable: commit ee1b308c33 of home-assistant/core | | | | | |
| [huggingface/transformers#29921](https://github.com/huggingface/transformers/pull/29921) | error: too large: 49 hunks to judge (limit 40) | | | | | |
| [ibis-project/ibis#9096](https://github.com/ibis-project/ibis/pull/9096) | error: too large: 51 hunks to judge (limit 40) | | | | | |
| [louislam/uptime-kuma#5916](https://github.com/louislam/uptime-kuma/pull/5916) | 25 | 1 | 4 | MISS | SPLIT SUGGESTED | 157.9 |
| [matplotlib/matplotlib#3060](https://github.com/matplotlib/matplotlib/pull/3060) | error: too large: 84 hunks to judge (limit 40) | | | | | |
| [mozilla/pdf.js#9417](https://github.com/mozilla/pdf.js/pull/9417) | error: too large: 54 hunks to judge (limit 40) | | | | | |
| [nodejs/node#44710](https://github.com/nodejs/node/pull/44710) | error: too large: 92 hunks to judge (limit 40) | | | | | |
| [osandov/drgn#129](https://github.com/osandov/drgn/pull/129) | error: too large: 46 hunks to judge (limit 40) | | | | | |
| [pandas-dev/pandas#28373](https://github.com/pandas-dev/pandas/pull/28373) | 19 | 1 | 0 | MISS | FOCUSED | 176.1 |
| [python/cpython#139123](https://github.com/python/cpython/pull/139123) | 28 | 1 | 7 | MISS | FOCUSED | 221.0 |
| [python/cpython#135057](https://github.com/python/cpython/pull/135057) | 17 | 1 | 7 | yes | MOSTLY OUT OF SCOPE | 163.8 |
| [pytorch/vision#6269](https://github.com/pytorch/vision/pull/6269) | 12 | 0 | 9 | n/a | MOSTLY OUT OF SCOPE | 104.0 |
| [scikit-learn/scikit-learn#522](https://github.com/scikit-learn/scikit-learn/pull/522) | 7 | 0 | 5 | n/a | MOSTLY OUT OF SCOPE | 45.7 |
| [scikit-learn/scikit-learn#1776](https://github.com/scikit-learn/scikit-learn/pull/1776) | 16 | 0 | 6 | n/a | MOSTLY OUT OF SCOPE | 117.2 |
| [sgl-project/sglang#18306](https://github.com/sgl-project/sglang/pull/18306) | error: commit unavailable: not found: /repos/sgl-project/sglang/com | | | | | |
| [sindresorhus/execa#208](https://github.com/sindresorhus/execa/pull/208) | 9 | 3 | 4 | yes | SPLIT SUGGESTED | 51.2 |
| [sympy/sympy#21590](https://github.com/sympy/sympy/pull/21590) | error: too large: 41 hunks to judge (limit 40) | | | | | |
| [sympy/sympy#16890](https://github.com/sympy/sympy/pull/16890) | error: commit unavailable: not found: /repos/sympy/sympy/compare/8a | | | | | |
| [systemd/mkosi#594](https://github.com/systemd/mkosi/pull/594) | error: too large: 52 hunks to judge (limit 40) | | | | | |
| [vllm-project/vllm#27772](https://github.com/vllm-project/vllm/pull/27772) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
| [vllm-project/vllm#7049](https://github.com/vllm-project/vllm/pull/7049) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
| [home-assistant/core#20197](https://github.com/home-assistant/core/pull/20197) | 8 | 1 | 0 | MISS | FOCUSED | 72.0 |
| [home-assistant/core#175902](https://github.com/home-assistant/core/pull/175902) | 35 | 2 | 0 | MISS | FOCUSED | 317.5 |

## heuristics-only

PRs without a file-anchored objection (verdict-only check): 4 of 10 not FOCUSED. Skipped as too large: 8. Errored PRs: 0. Unjudged hunks: 1104.

| PR | hunks | objected | flagged | hit | verdict | s |
|---|---|---|---|---|---|---|
| [CircuitVerse/CircuitVerse#726](https://github.com/CircuitVerse/CircuitVerse/pull/726) | 10 | 0 | 0 | n/a | UNSCORED | 6.3 |
| [GoogleChrome/lighthouse#5846](https://github.com/GoogleChrome/lighthouse/pull/5846) | 25 | 0 | 0 | n/a | UNSCORED | 17.6 |
| [NVIDIA/TensorRT-LLM#13864](https://github.com/NVIDIA/TensorRT-LLM/pull/13864) | 144 | 1 | 0 | MISS | UNSCORED | 87.5 |
| [ampproject/amphtml#26085](https://github.com/ampproject/amphtml/pull/26085) | 2 | 1 | 0 | MISS | UNSCORED | 54.2 |
| [apache/tvm#5812](https://github.com/apache/tvm/pull/5812) | 44 | 0 | 0 | n/a | UNSCORED | 13.7 |
| [cockpit-project/cockpit#19024](https://github.com/cockpit-project/cockpit/pull/19024) | 18 | 1 | 0 | MISS | UNSCORED | 9.3 |
| [cockpit-project/cockpit#7820](https://github.com/cockpit-project/cockpit/pull/7820) | 85 | 0 | 9 | n/a | MOSTLY OUT OF SCOPE | 8.4 |
| [home-assistant/core#175076](https://github.com/home-assistant/core/pull/175076) | 20 | 1 | 0 | MISS | UNSCORED | 101.0 |
| [home-assistant/core#80797](https://github.com/home-assistant/core/pull/80797) | 51 | 1 | 0 | MISS | UNSCORED | 65.9 |
| [home-assistant/core#150886](https://github.com/home-assistant/core/pull/150886) | 20 | 1 | 0 | MISS | UNSCORED | 79.7 |
| [home-assistant/core#116267](https://github.com/home-assistant/core/pull/116267) | 18 | 1 | 0 | MISS | UNSCORED | 75.3 |
| [home-assistant/core#170893](https://github.com/home-assistant/core/pull/170893) | 24 | 1 | 0 | MISS | UNSCORED | 101.8 |
| [home-assistant/core#20197](https://github.com/home-assistant/core/pull/20197) | 8 | 1 | 0 | MISS | UNSCORED | 23.1 |
| [home-assistant/core#44091](https://github.com/home-assistant/core/pull/44091) | 15 | 1 | 0 | MISS | UNSCORED | 26.0 |
| [home-assistant/core#139857](https://github.com/home-assistant/core/pull/139857) | 14 | 1 | 0 | MISS | UNSCORED | 106.9 |
| [home-assistant/core#175902](https://github.com/home-assistant/core/pull/175902) | 35 | 2 | 0 | MISS | UNSCORED | 93.9 |
| [huggingface/transformers#29921](https://github.com/huggingface/transformers/pull/29921) | 85 | 3 | 36 | MISS | MOSTLY OUT OF SCOPE | 29.8 |
| [ibis-project/ibis#9096](https://github.com/ibis-project/ibis/pull/9096) | 51 | 2 | 0 | MISS | UNSCORED | 13.2 |
| [louislam/uptime-kuma#5916](https://github.com/louislam/uptime-kuma/pull/5916) | 25 | 1 | 0 | MISS | UNSCORED | 5.3 |
| [matplotlib/matplotlib#3060](https://github.com/matplotlib/matplotlib/pull/3060) | 85 | 0 | 1 | n/a | MOSTLY OUT OF SCOPE | 22.6 |
| [mozilla/pdf.js#9417](https://github.com/mozilla/pdf.js/pull/9417) | 55 | 1 | 1 | MISS | MOSTLY OUT OF SCOPE | 13.4 |
| [nodejs/node#44710](https://github.com/nodejs/node/pull/44710) | 92 | 0 | 0 | n/a | UNSCORED | 68.2 |
| [osandov/drgn#129](https://github.com/osandov/drgn/pull/129) | 46 | 1 | 0 | MISS | UNSCORED | 5.5 |
| [pandas-dev/pandas#28373](https://github.com/pandas-dev/pandas/pull/28373) | 19 | 1 | 0 | MISS | UNSCORED | 15.8 |
| [python/cpython#139123](https://github.com/python/cpython/pull/139123) | 28 | 1 | 3 | MISS | MOSTLY OUT OF SCOPE | 32.5 |
| [python/cpython#135057](https://github.com/python/cpython/pull/135057) | 17 | 1 | 1 | yes | MOSTLY OUT OF SCOPE | 55.1 |
| [pytorch/vision#6269](https://github.com/pytorch/vision/pull/6269) | 12 | 0 | 0 | n/a | UNSCORED | 11.1 |
| [scikit-learn/scikit-learn#522](https://github.com/scikit-learn/scikit-learn/pull/522) | 7 | 0 | 2 | n/a | MOSTLY OUT OF SCOPE | 7.4 |
| [scikit-learn/scikit-learn#1776](https://github.com/scikit-learn/scikit-learn/pull/1776) | 16 | 0 | 1 | n/a | MOSTLY OUT OF SCOPE | 7.4 |
| [sindresorhus/execa#208](https://github.com/sindresorhus/execa/pull/208) | 9 | 3 | 2 | yes | MOSTLY OUT OF SCOPE | 3.6 |
| [sympy/sympy#21590](https://github.com/sympy/sympy/pull/21590) | 44 | 2 | 3 | MISS | MOSTLY OUT OF SCOPE | 27.6 |
| [systemd/mkosi#594](https://github.com/systemd/mkosi/pull/594) | 52 | 0 | 0 | n/a | UNSCORED | 4.2 |
| [apache/airflow#21877](https://github.com/apache/airflow/pull/21877) | error: commit unavailable: not found: /repos/apache/airflow/compare | | | | | |
| [cockpit-project/cockpit#11150](https://github.com/cockpit-project/cockpit/pull/11150) | error: commit unavailable: not found: /repos/cockpit-project/cockpi | | | | | |
| [home-assistant/core#18758](https://github.com/home-assistant/core/pull/18758) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#50653](https://github.com/home-assistant/core/pull/50653) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [sgl-project/sglang#18306](https://github.com/sgl-project/sglang/pull/18306) | error: commit unavailable: not found: /repos/sgl-project/sglang/com | | | | | |
| [sympy/sympy#16890](https://github.com/sympy/sympy/pull/16890) | error: commit unavailable: not found: /repos/sympy/sympy/compare/8a | | | | | |
| [vllm-project/vllm#27772](https://github.com/vllm-project/vllm/pull/27772) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
| [vllm-project/vllm#7049](https://github.com/vllm-project/vllm/pull/7049) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |

## llama3.2:3b

PRs without a file-anchored objection (verdict-only check): 5 of 5 not FOCUSED. Skipped as too large: 20. Errored PRs: 0. Unjudged hunks: 0.

| PR | hunks | objected | flagged | hit | verdict | s |
|---|---|---|---|---|---|---|
| [CircuitVerse/CircuitVerse#726](https://github.com/CircuitVerse/CircuitVerse/pull/726) | 10 | 0 | 10 | n/a | MOSTLY OUT OF SCOPE | 22.7 |
| [GoogleChrome/lighthouse#5846](https://github.com/GoogleChrome/lighthouse/pull/5846) | 25 | 0 | 24 | n/a | MOSTLY OUT OF SCOPE | 60.6 |
| [NVIDIA/TensorRT-LLM#13864](https://github.com/NVIDIA/TensorRT-LLM/pull/13864) | error: too large: 144 hunks to judge (limit 40) | | | | | |
| [ampproject/amphtml#26085](https://github.com/ampproject/amphtml/pull/26085) | 2 | 1 | 2 | yes | MOSTLY OUT OF SCOPE | 36.3 |
| [apache/airflow#21877](https://github.com/apache/airflow/pull/21877) | error: commit unavailable: not found: /repos/apache/airflow/compare | | | | | |
| [apache/tvm#5812](https://github.com/apache/tvm/pull/5812) | error: too large: 43 hunks to judge (limit 40) | | | | | |
| [cockpit-project/cockpit#19024](https://github.com/cockpit-project/cockpit/pull/19024) | 18 | 1 | 18 | yes | MOSTLY OUT OF SCOPE | 33.1 |
| [cockpit-project/cockpit#11150](https://github.com/cockpit-project/cockpit/pull/11150) | error: commit unavailable: not found: /repos/cockpit-project/cockpi | | | | | |
| [cockpit-project/cockpit#7820](https://github.com/cockpit-project/cockpit/pull/7820) | error: too large: 76 hunks to judge (limit 40) | | | | | |
| [home-assistant/core#175076](https://github.com/home-assistant/core/pull/175076) | 20 | 1 | 17 | yes | MOSTLY OUT OF SCOPE | 94.5 |
| [home-assistant/core#80797](https://github.com/home-assistant/core/pull/80797) | error: too large: 51 hunks to judge (limit 40) | | | | | |
| [home-assistant/core#150886](https://github.com/home-assistant/core/pull/150886) | 20 | 1 | 13 | yes | MOSTLY OUT OF SCOPE | 104.3 |
| [home-assistant/core#116267](https://github.com/home-assistant/core/pull/116267) | 18 | 1 | 13 | yes | MOSTLY OUT OF SCOPE | 76.2 |
| [home-assistant/core#18758](https://github.com/home-assistant/core/pull/18758) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#170893](https://github.com/home-assistant/core/pull/170893) | 24 | 1 | 16 | yes | MOSTLY OUT OF SCOPE | 119.4 |
| [home-assistant/core#20197](https://github.com/home-assistant/core/pull/20197) | 8 | 1 | 0 | MISS | FOCUSED | 28.4 |
| [home-assistant/core#44091](https://github.com/home-assistant/core/pull/44091) | 15 | 1 | 14 | yes | MOSTLY OUT OF SCOPE | 51.3 |
| [home-assistant/core#50653](https://github.com/home-assistant/core/pull/50653) | error: commit unavailable: not found: /repos/home-assistant/core/co | | | | | |
| [home-assistant/core#139857](https://github.com/home-assistant/core/pull/139857) | 14 | 1 | 8 | yes | SPLIT SUGGESTED | 80.7 |
| [home-assistant/core#175902](https://github.com/home-assistant/core/pull/175902) | 35 | 2 | 33 | yes | MOSTLY OUT OF SCOPE | 136.9 |
| [huggingface/transformers#29921](https://github.com/huggingface/transformers/pull/29921) | error: too large: 49 hunks to judge (limit 40) | | | | | |
| [ibis-project/ibis#9096](https://github.com/ibis-project/ibis/pull/9096) | error: too large: 51 hunks to judge (limit 40) | | | | | |
| [louislam/uptime-kuma#5916](https://github.com/louislam/uptime-kuma/pull/5916) | 25 | 1 | 25 | yes | MOSTLY OUT OF SCOPE | 41.3 |
| [matplotlib/matplotlib#3060](https://github.com/matplotlib/matplotlib/pull/3060) | error: too large: 84 hunks to judge (limit 40) | | | | | |
| [mozilla/pdf.js#9417](https://github.com/mozilla/pdf.js/pull/9417) | error: too large: 54 hunks to judge (limit 40) | | | | | |
| [nodejs/node#44710](https://github.com/nodejs/node/pull/44710) | error: too large: 92 hunks to judge (limit 40) | | | | | |
| [osandov/drgn#129](https://github.com/osandov/drgn/pull/129) | error: too large: 46 hunks to judge (limit 40) | | | | | |
| [pandas-dev/pandas#28373](https://github.com/pandas-dev/pandas/pull/28373) | 19 | 1 | 2 | MISS | SPLIT SUGGESTED | 32.6 |
| [python/cpython#139123](https://github.com/python/cpython/pull/139123) | 28 | 1 | 28 | yes | MOSTLY OUT OF SCOPE | 70.8 |
| [python/cpython#135057](https://github.com/python/cpython/pull/135057) | 17 | 1 | 17 | yes | MOSTLY OUT OF SCOPE | 56.3 |
| [pytorch/vision#6269](https://github.com/pytorch/vision/pull/6269) | 12 | 0 | 12 | n/a | MOSTLY OUT OF SCOPE | 36.3 |
| [scikit-learn/scikit-learn#522](https://github.com/scikit-learn/scikit-learn/pull/522) | 7 | 0 | 7 | n/a | MOSTLY OUT OF SCOPE | 19.6 |
| [scikit-learn/scikit-learn#1776](https://github.com/scikit-learn/scikit-learn/pull/1776) | 16 | 0 | 16 | n/a | MOSTLY OUT OF SCOPE | 44.2 |
| [sgl-project/sglang#18306](https://github.com/sgl-project/sglang/pull/18306) | error: commit unavailable: not found: /repos/sgl-project/sglang/com | | | | | |
| [sindresorhus/execa#208](https://github.com/sindresorhus/execa/pull/208) | 9 | 3 | 9 | yes | MOSTLY OUT OF SCOPE | 20.2 |
| [sympy/sympy#21590](https://github.com/sympy/sympy/pull/21590) | error: too large: 41 hunks to judge (limit 40) | | | | | |
| [sympy/sympy#16890](https://github.com/sympy/sympy/pull/16890) | error: commit unavailable: not found: /repos/sympy/sympy/compare/8a | | | | | |
| [systemd/mkosi#594](https://github.com/systemd/mkosi/pull/594) | error: too large: 52 hunks to judge (limit 40) | | | | | |
| [vllm-project/vllm#27772](https://github.com/vllm-project/vllm/pull/27772) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
| [vllm-project/vllm#7049](https://github.com/vllm-project/vllm/pull/7049) | error: commit unavailable: not found: /repos/vllm-project/vllm/comp | | | | | |
