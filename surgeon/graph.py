"""Reverse-import graph and blast radius. Built from the base revision so it reflects who depends on the code today."""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from . import langs

JS_RESOLVE_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"]
SOURCE_EXTS = langs.PY_EXTS | langs.JS_EXTS
TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "testing"}


def is_test_path(path: str) -> bool:
    p = path.lower()
    parts = set(p.split("/"))
    name = p.rsplit("/", 1)[-1]
    return bool(
        parts & TEST_PARTS
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.js"))
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

    def _build(self) -> None:
        for path, src in self.files.items():
            lang = langs.language_of(path)
            if lang is None:
                continue
            for ref in langs.imports(path, src):
                resolved = self._resolve_python(path, ref) if lang == "python" else self._resolve_js(path, ref)
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
