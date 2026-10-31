"""Reverse-import graph and blast radius. Built from the base revision so it reflects who depends on the code today."""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from . import langs

JS_RESOLVE_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"]
SOURCE_EXTS = (
    langs.PY_EXTS | langs.JS_EXTS | langs.JAVA_EXTS | langs.GO_EXTS | langs.RUST_EXTS | {".mod"}
)  # .mod: go.mod, read for module paths
_JAVA_TEST = re.compile(r"(?:^|/)(?:Test[A-Z]\w*|\w+(?:Test|Tests|IT))\.java$")  # case matters: Latest.java is not a test
TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "testing"}


def is_test_path(path: str) -> bool:
    p = path.lower()
    parts = set(p.split("/"))
    name = p.rsplit("/", 1)[-1]
    return bool(
        parts & TEST_PARTS
        or name.startswith(("test_", "test."))
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.js", "_test.go"))
        or "src/test/" in p
        or bool(_JAVA_TEST.search(path))
        or name == "conftest.py"
    )


@dataclass
class Edge:
    importer: str
    names: tuple[str, ...]  # () = whole-module import


@dataclass
class Blast:
    path: str
    symbol: str | None
    direct: int  # files importing this file
    direct_non_test: int
    transitive: int  # files that depend on it through any chain
    symbol_importers: int | None  # files that use `symbol` specifically (None when unknown)
    importers: list[str] = field(default_factory=list)  # up to 8, non-test first
    evidence: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class ImportGraph:
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.py_files = {p for p in files if p.endswith(".py")}
        self.all_paths = set(files)
        self.py_roots = self._python_roots()
        self.java_index, self.java_pkgs = self._java_indexes()
        self.go_dirs = self._go_dirs()
        self.go_modules = self._go_modules()
        self.importers: dict[str, list[Edge]] = defaultdict(list)
        self._build()

    # -- resolution ---------------------------------------------------------------
    def _python_roots(self) -> list[str]:
        roots = {""}
        for p in self.py_files:
            if not p.endswith("/__init__.py") and p != "__init__.py":
                continue
            d = posixpath.dirname(p)
            while d and posixpath.join(posixpath.dirname(d), "__init__.py") in self.py_files:
                d = posixpath.dirname(d)
            roots.add(posixpath.dirname(d))
        return sorted(roots, key=len)

    def _py_module(self, dotted: str, base_dir: str | None = None) -> str | None:
        rel = dotted.replace(".", "/")
        for root in [base_dir] if base_dir is not None else self.py_roots:
            stem = posixpath.join(root, rel) if rel else root
            cands = (f"{stem}.py", posixpath.join(stem, "__init__.py")) if rel else (posixpath.join(stem, "__init__.py"),)
            for cand in cands:
                cand = cand.lstrip("/")
                if cand in self.py_files:
                    return cand
        return None

    def _resolve_python(self, importer: str, ref: langs.ImportRef) -> list[tuple[str, tuple[str, ...]]]:
        base_dir = None
        if ref.level:
            d = posixpath.dirname(importer)
            for _ in range(ref.level - 1):
                d = posixpath.dirname(d)
            base_dir = d
        targets: list[tuple[str, tuple[str, ...]]] = []
        main = self._py_module(ref.module, base_dir) if (ref.module or base_dir is not None) else None
        sub_hit: set[str] = set()
        for name in ref.names:  # `from pkg import submodule` imports a module, not a symbol
            if name == "*":
                continue
            sub = self._py_module(f"{ref.module}.{name}" if ref.module else name, base_dir)
            if sub and sub != main:
                targets.append((sub, ()))
                sub_hit.add(name)
        if main:
            remaining = tuple(n for n in ref.names if n not in sub_hit)
            if remaining or not ref.names or not sub_hit:
                targets.append((main, remaining))
        return targets

    def _resolve_js(self, importer: str, ref: langs.ImportRef) -> list[tuple[str, tuple[str, ...]]]:
        spec = ref.module
        if not spec.startswith("."):
            return []
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        stem, ext = posixpath.splitext(base)
        cands = [base] if base in self.all_paths else []
        if ext in {".js", ".jsx", ".mjs", ".cjs"}:  # TS ESM style: './x.js' means './x.ts'
            cands += [stem + e for e in JS_RESOLVE_EXTS]
        cands += [base + e for e in JS_RESOLVE_EXTS] + [posixpath.join(base, "index" + e) for e in JS_RESOLVE_EXTS]
        for c in cands:
            if c in self.all_paths:
                return [(c, ref.names)]
        return []

    # -- java: fully qualified class name -> file, package -> files --------------------
    def _java_indexes(self) -> tuple[dict[str, str], dict[str, list[str]]]:
        by_class: dict[str, str] = {}
        by_pkg: dict[str, list[str]] = defaultdict(list)
        for p in self.all_paths:
            if not p.endswith(".java"):
                continue
            parts = p[: -len(".java")].split("/")
            for k in range(len(parts)):  # every suffix of the path is a candidate FQCN (source roots vary)
                by_class.setdefault(".".join(parts[k:]), p)
            for k in range(len(parts) - 1):
                by_pkg[".".join(parts[k:-1])].append(p)
        return by_class, by_pkg

    def _resolve_java(self, importer: str, ref: langs.ImportRef) -> list[tuple[str, tuple[str, ...]]]:
        if ref.names == ("*",):
            return [(f, ()) for f in dict.fromkeys(self.java_pkgs.get(ref.module, [])) if f != importer]
        target = self.java_index.get(ref.module)
        if target is None and "." in ref.module:  # a nested class: a.b.Outer.Inner lives in Outer.java
            target = self.java_index.get(ref.module.rsplit(".", 1)[0])
        return [(target, ref.names)] if target else []

    # -- go: imports name a package (a directory), not a file ---------------------------
    def _go_dirs(self) -> dict[str, list[str]]:
        dirs: dict[str, list[str]] = defaultdict(list)
        for p in self.all_paths:
            if p.endswith(".go") and not p.endswith("_test.go"):
                dirs[posixpath.dirname(p)].append(p)
        return dirs

    def _go_modules(self) -> list[tuple[str, str]]:
        """(module path, directory) for every go.mod, longest module path first."""
        mods = []
        for p, src in self.files.items():
            if posixpath.basename(p) == "go.mod":
                m = re.search(r"(?m)^module\s+(\S+)", src.decode("utf-8", "replace"))
                if m:
                    mods.append((m[1].strip('"'), posixpath.dirname(p)))
        return sorted(mods, key=lambda x: -len(x[0]))

    def _resolve_go(self, importer: str, ref: langs.ImportRef) -> list[tuple[str, tuple[str, ...]]]:
        best = None
        for mpath, mdir in self.go_modules:  # exact: strip the module path from the import path
            if ref.module == mpath or ref.module.startswith(mpath + "/"):
                best = (
                    posixpath.normpath(posixpath.join(mdir, ref.module[len(mpath) :].lstrip("/"))).lstrip("./")
                    if ref.module != mpath
                    else mdir
                )
                best = "" if best == "." else best
                break
        if best is None:  # no go.mod in the tree: the longest directory that ends the import path
            best = ""
            for d in self.go_dirs:
                if d and (ref.module == d or ref.module.endswith("/" + d)) and len(d) > len(best):
                    best = d
            if not best:
                return []
        if best not in self.go_dirs or (
            best == posixpath.dirname(importer) and not importer.endswith("_test.go")
        ):  # an external `pkg_test` file imports its own package
            return []
        return [(f, ()) for f in self.go_dirs[best]]

    # -- rust: crate::a::b, super::x, self::x, `mod x;` ---------------------------------
    def _rust_module_dir(self, path: str) -> str:
        d, name = posixpath.dirname(path), posixpath.basename(path)
        return d if name in {"lib.rs", "main.rs", "mod.rs"} else posixpath.join(d, name[:-3])

    def _rust_crate_src(self, path: str) -> str | None:
        parts = path.split("/")
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] == "src":
                return "/".join(parts[: i + 1])
        return None

    def _rust_file(self, base: str) -> str | None:
        cands = ("lib.rs", "main.rs") if posixpath.basename(base) == "src" else (f"{base}.rs", posixpath.join(base, "mod.rs"))
        for cand in cands:
            cand = posixpath.join(base, cand) if posixpath.basename(base) == "src" else cand
            if cand in self.all_paths:
                return cand
        return None

    def _resolve_rust(self, importer: str, ref: langs.ImportRef) -> list[tuple[str, tuple[str, ...]]]:
        segs = ref.module.split("::")
        head, rest = segs[0], segs[1:]
        if head == "crate":
            base = self._rust_crate_src(importer)
        elif head == "self":
            base = self._rust_module_dir(importer)
        elif head == "super":
            base = posixpath.dirname(self._rust_module_dir(importer))
            while rest and rest[0] == "super":  # super::super::x
                base, rest = posixpath.dirname(base), rest[1:]
        else:
            return []  # another crate or the std library
        if base is None:
            return []
        trimmed: list[str] = []
        while True:  # `use a::b::Item`: try a/b/Item, then a/b with Item as the imported name, then a
            f = self._rust_file(posixpath.join(base, *rest))
            if f and f != importer:
                return [(f, ref.names or tuple(trimmed[:1]))]
            if not rest:
                return []
            trimmed.insert(0, rest.pop())

    def _build(self) -> None:
        for path, src in self.files.items():
            lang = langs.language_of(path)
            if lang is None:
                continue
            for ref in langs.imports(path, src):
                resolver = {
                    "python": self._resolve_python,
                    "js": self._resolve_js,
                    "java": self._resolve_java,
                    "go": self._resolve_go,
                    "rust": self._resolve_rust,
                }[lang]
                resolved = resolver(path, ref)
                for target, names in resolved:
                    if target != path:
                        self.importers[target].append(Edge(path, names))

    # -- queries ------------------------------------------------------------------
    def direct_importers(self, path: str) -> list[str]:
        return sorted({e.importer for e in self.importers.get(path, [])})

    def transitive_importers(self, path: str, cap: int = 5000) -> set[str]:
        seen: set[str] = set()
        queue = deque([path])
        while queue and len(seen) < cap:
            cur = queue.popleft()
            for imp in self.direct_importers(cur):
                if imp not in seen and imp != path:
                    seen.add(imp)
                    queue.append(imp)
        return seen

    def uses_symbol(self, importer: str, edge_names: tuple[str, ...], symbol: str) -> bool:
        if symbol in edge_names:
            return True
        if "*" in edge_names or not edge_names:  # whole-module or star import: look for the name in the source
            return bool(re.search(rf"\b{re.escape(symbol)}\b", self.files[importer].decode("utf-8", "replace")))
        return False

    def blast(self, path: str, symbol: str | None = None) -> Blast:
        if path not in self.files and path not in self.importers:
            return Blast(path, symbol, 0, 0, 0, None, [], "new or non-source file: nobody imports it yet")
        direct = self.direct_importers(path)
        non_test = [p for p in direct if not is_test_path(p)]
        trans = self.transitive_importers(path)
        sym_count = None
        if symbol:
            users = {e.importer for e in self.importers.get(path, []) if self.uses_symbol(e.importer, e.names, symbol)}
            sym_count = len(users)
        ordered = non_test + [p for p in direct if is_test_path(p)]
        who = f"`{path}`" + (f"::{symbol}" if symbol else "")
        evidence = f"{who} is imported by {len(direct)} file(s) ({len(non_test)} non-test)"
        if sym_count is not None:
            evidence += f"; {sym_count} of them use `{symbol}`"
        if len(trans) > len(direct):
            evidence += f"; {len(trans)} depend on it transitively"
        return Blast(path, symbol, len(direct), len(non_test), len(trans), sym_count, ordered[:8], evidence)
