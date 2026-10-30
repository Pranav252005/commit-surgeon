import json

import httpx

from surgeon.diff import Hunk
from surgeon.judge import Judge, ModelConfig, _parse, judge_hunks


def hunk(label=None):
    return Hunk("a.py#0", "a.py", "a.py", "modified", 0, 1, 1, 1, 0, ["x"], [], [1], [], "@@ -1 +1 @@\n+x\n", label=label)


def fake(reply, calls):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    return httpx.Client(base_url="http://x/v1", transport=httpx.MockTransport(handler))


def test_parse_tolerates_wrapping_and_rejects_bad_labels():
    assert _parse('Sure! {"label": "needed", "confidence": 2, "reason": "fix"}').confidence == 1.0
    assert _parse('{"label": "maybe"}') is None
    assert _parse("no json here") is None


def test_judge_labels_caches_and_sends_openai_shape(tmp_path):
    calls: list = []
    j = Judge(ModelConfig(model="m"), tmp_path, fake('{"label":"cleanup","confidence":0.8,"reason":"renames"}', calls))
    hs = [hunk(), hunk(label="cleanup")]  # second is already settled by heuristics: no call
    assert judge_hunks(hs, j, "pr", "issue", "body") == 1
    assert hs[0].label == "cleanup" and len(calls) == 1
    assert json.loads(calls[0].content)["model"] == "m"
    again = hunk()
    judge_hunks([again], j, "pr", "issue", "body")
    assert len(calls) == 1  # served from cache


def test_unreachable_model_does_not_raise(tmp_path):
    def boom(req):
        raise httpx.ConnectError("down")

    j = Judge(ModelConfig(), tmp_path, httpx.Client(base_url="http://x/v1", transport=httpx.MockTransport(boom)))
    assert not j.available()
    h = hunk()
    assert judge_hunks([h], j, "p", "i", "b") == 0 and h.label is None
