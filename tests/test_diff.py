from surgeon import heuristics
from surgeon.diff import parse_patch

PATCH = """diff --git a/app/util.py b/app/util.py
index 111..222 100644
--- a/app/util.py
+++ b/app/util.py
@@ -1,5 +1,5 @@
 def parse(x):
-    return x+1
+    return x + 1
 
 def other():
     pass
@@ -20,1 +20,2 @@ def other():
     pass
+    print("debug")
diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
diff --git a/package-lock.json b/package-lock.json
index 1..2 100644
--- a/package-lock.json
+++ b/package-lock.json
@@ -1 +1 @@
-  "a": 1
+  "a": 2
"""


def test_parse_patch_hunks_and_status():
    files = {f.path: f for f in parse_patch(PATCH)}
    assert set(files) == {"app/util.py", "new.py", "package-lock.json"}
    assert files["new.py"].status == "renamed" and files["new.py"].old_path == "old.py"
    assert files["new.py"].hunks[0].pseudo
    assert len(files["app/util.py"].hunks) == 2
    assert files["app/util.py"].hunks[1].changed_new == [21]


def test_heuristics_labels():
    files = parse_patch(PATCH)
    heuristics.apply(files, None, "parse crashes", "")
    by_id = {h.id: h for f in files for h in f.hunks}
    assert by_id["app/util.py#0"].label == "cleanup"  # `x+1` -> `x + 1` is whitespace-only
    assert "whitespace_only" in by_id["app/util.py#0"].tags
    assert by_id["app/util.py#1"].label is None  # real change: left to the judge
    assert by_id["new.py#0"].label == "cleanup" and "rename_only" in by_id["new.py#0"].tags
    assert by_id["package-lock.json#0"].label == "ancillary"


def test_kind_classification():
    k = heuristics.classify_kind
    assert k("tests/test_a.py") == "test"
    assert k("docs/guide.rst") == "docs"
    assert k("CHANGES.rst") == "docs"
    assert k("src/api/foo.ts") == "code"
    assert k("dist/app.min.js") == "generated"
    assert k(".github/workflows/ci.yml") == "config"
