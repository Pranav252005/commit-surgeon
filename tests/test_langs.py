from surgeon import langs
from surgeon.graph import ImportGraph, is_test_path


def graph(files: dict[str, str]) -> ImportGraph:
    return ImportGraph({p: s.encode() for p, s in files.items()})


# ---------------------------------------------------------------- java
JAVA = {
    "src/main/java/com/acme/util/Strings.java": "package com.acme.util;\npublic class Strings { public static String up(String s){return s;} }\n",
    "src/main/java/com/acme/util/Dates.java": "package com.acme.util;\npublic class Dates { }\n",
    "src/main/java/com/acme/app/Main.java": 'package com.acme.app;\nimport com.acme.util.Strings;\nimport static com.acme.util.Strings.up;\nimport com.acme.util.*;\nimport java.util.List;\nclass Main { void run(){ Strings.up("x"); } }\n',
    "src/main/java/com/acme/app/Other.java": "package com.acme.app;\nimport com.acme.util.Dates;\nclass Other {}\n",
    "src/test/java/com/acme/util/StringsTest.java": "package com.acme.util;\nimport com.acme.util.Strings;\nclass StringsTest {}\n",
}


def test_java_symbols_and_imports():
    src = JAVA["src/main/java/com/acme/app/Main.java"].encode()
    assert [s.name for s in langs.symbols("Main.java", src)] == ["Main", "Main.run"]
    refs = langs.imports("Main.java", src)
    assert ("com.acme.util.Strings", ()) in [(r.module, r.names) for r in refs]
    assert ("com.acme.util", ("*",)) in [(r.module, r.names) for r in refs]
    assert ("com.acme.util.Strings", ("up",)) in [(r.module, r.names) for r in refs]  # static import


def test_java_graph_resolves_class_wildcard_and_static_imports():
    g = graph(JAVA)
    assert g.direct_importers("src/main/java/com/acme/util/Strings.java") == [
        "src/main/java/com/acme/app/Main.java",
        "src/test/java/com/acme/util/StringsTest.java",
    ]
    assert "src/main/java/com/acme/app/Main.java" in g.direct_importers("src/main/java/com/acme/util/Dates.java")  # via the wildcard
    assert "src/main/java/com/acme/app/Other.java" in g.direct_importers("src/main/java/com/acme/util/Dates.java")
    b = g.blast("src/main/java/com/acme/util/Strings.java", "Strings")
    assert (b.direct, b.direct_non_test) == (2, 1)


# ---------------------------------------------------------------- go
GO = {
    "internal/util/util.go": "package util\nfunc Clean(s string) string { return s }\ntype Box struct{}\nfunc (b *Box) Open() {}\n",
    "internal/util/extra.go": "package util\nfunc Helper() {}\n",
    "internal/util/util_test.go": 'package util\nimport "testing"\nfunc TestX(t *testing.T) {}\n',
    "cmd/app/main.go": 'package main\nimport (\n  "fmt"\n  u "github.com/acme/tool/internal/util"\n)\nfunc main(){ fmt.Println(u.Clean("x")) }\n',
    "cmd/other/main.go": 'package main\nimport "github.com/acme/tool/internal/util"\nfunc main(){ util.Helper() }\n',
}


def test_go_symbols_and_receiver_names():
    src = GO["internal/util/util.go"].encode()
    assert [(s.name, s.kind) for s in langs.symbols("util.go", src)] == [("Clean", "function"), ("Box", "class"), ("Box.Open", "method")]


def test_go_import_is_a_package_not_a_file_and_stdlib_is_ignored():
    g = graph(GO)
    assert g.direct_importers("internal/util/util.go") == ["cmd/app/main.go", "cmd/other/main.go"]
    assert g.direct_importers("internal/util/extra.go") == ["cmd/app/main.go", "cmd/other/main.go"]
    assert g.direct_importers("cmd/app/main.go") == []  # "fmt" resolves to nothing in the repo
    assert not any("util_test.go" in p for p in g.importers)  # _test.go files are not part of the package's public surface


# ---------------------------------------------------------------- rust
RUST = {
    "src/lib.rs": "pub mod config;\nmod util;\nuse crate::config::Settings;\n",
    "src/config.rs": "pub struct Settings;\nimpl Settings { pub fn load() {} }\n",
    "src/util/mod.rs": "pub fn helper() {}\npub mod strings;\n",
    "src/util/strings.rs": "use super::helper;\nuse crate::config::Settings;\npub fn up() {}\n",
    "src/bin/tool.rs": "use other_crate::thing;\nfn main() {}\n",
}


def test_rust_symbols_and_use_trees():
    src = b"use crate::a::b::Item;\nuse super::c::{D, E as F};\nuse a::{self, B};\nuse x::*;\nmod m;\nstruct S;\nimpl S { fn f(&self){} }\n"
    assert [s.name for s in langs.symbols("l.rs", src)] == ["S", "S", "S.f"]  # `mod m;` is not a definition
    mods = [(r.module, r.names) for r in langs.imports("l.rs", src)]
    assert ("crate::a::b::Item", ()) in mods and ("super::c::D", ()) in mods and ("super::c::E", ()) in mods
    assert ("a", ()) in mods and ("a::B", ()) in mods and ("x", ("*",)) in mods and ("self::m", ()) in mods


def test_rust_graph_resolves_crate_super_self_and_mod_decls():
    g = graph(RUST)
    assert g.direct_importers("src/config.rs") == ["src/lib.rs", "src/util/strings.rs"]
    assert g.direct_importers("src/util/mod.rs") == ["src/lib.rs", "src/util/strings.rs"]  # `mod util;` and `use super::helper`
    assert g.direct_importers("src/util/strings.rs") == ["src/util/mod.rs"]  # `pub mod strings;` in mod.rs
    assert g.importers.get("src/bin/tool.rs") is None  # external crates are ignored


def test_test_path_detection_for_new_languages():
    for p in ["src/test/java/a/B.java", "a/FooTest.java", "a/TestFoo.java", "a/FooIT.java", "pkg/x_test.go", "tests/it.rs"]:
        assert is_test_path(p), p
    assert not is_test_path("src/main/java/a/Latest.java")


def test_go_mod_resolves_the_root_package_and_nested_modules():
    g = graph(
        {
            "go.mod": "module github.com/acme/tool\n\ngo 1.22\n",
            "tool.go": "package tool\nfunc Run() {}\n",
            "doc/doc.go": 'package doc\nimport "github.com/acme/tool"\nfunc Gen() { tool.Run() }\n',
            "sub/x.go": 'package sub\nimport "github.com/acme/tool/doc"\nimport "github.com/other/lib"\n',
        }
    )
    assert g.direct_importers("tool.go") == ["doc/doc.go"]  # the root package, only reachable through go.mod
    assert g.direct_importers("doc/doc.go") == ["sub/x.go"]
