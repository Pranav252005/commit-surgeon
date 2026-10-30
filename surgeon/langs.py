"""Symbol and import extraction. tree-sitter first, regex fallback for imports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import PurePosixPath

PY_EXTS = {".py"}
JS_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
JAVA_EXTS = {".java"}
GO_EXTS = {".go"}
RUST_EXTS = {".rs"}
TSX_EXTS = {".tsx", ".jsx"}


@dataclass(frozen=True)
class Symbol:
    name: str  # qualified, e.g. "Client.send"
    kind: str  # function | class | method
    start: int  # 1-based, inclusive
    end: int  # 1-based, inclusive

    @property
    def top(self) -> str:
        return self.name.split(".")[0]


@dataclass(frozen=True)
class ImportRef:
    module: str  # python: dotted name without leading dots; js: raw specifier
    level: int = 0  # python relative level (number of leading dots)
    names: tuple[str, ...] = ()  # imported names; "*" star/namespace, "default" js default; () = whole module
    alias: str = ""  # go: the local package name when it differs from the last path segment


def language_of(path: str) -> str | None:
    ext = PurePosixPath(path).suffix.lower()
    if ext in PY_EXTS:
        return "python"
    if ext in JS_EXTS:
        return "js"
    if ext in JAVA_EXTS:
        return "java"
    if ext in GO_EXTS:
        return "go"
    if ext in RUST_EXTS:
        return "rust"
    return None


@cache
def _parser(lang: str, tsx: bool, ts: bool):
    try:
        from tree_sitter import Language, Parser

        if lang == "python":
            import tree_sitter_python as m

            language = Language(m.language())
        elif lang == "java":
            import tree_sitter_java as m

            language = Language(m.language())
        elif lang == "go":
            import tree_sitter_go as m

            language = Language(m.language())
        elif lang == "rust":
            import tree_sitter_rust as m

            language = Language(m.language())
        elif ts:
            import tree_sitter_typescript as m

            language = Language(m.language_tsx() if tsx else m.language_typescript())
        else:
            import tree_sitter_javascript as m

            language = Language(m.language())
        return Parser(language)
    except Exception:  # missing wheel, ABI mismatch: callers fall back to regex
        return None


def _parse(path: str, source: bytes):
    lang = language_of(path)
    if lang is None:
        return None, None
    ext = PurePosixPath(path).suffix.lower()
    parser = _parser(lang, ext in {".tsx", ".jsx"}, ext in {".ts", ".tsx", ".mts", ".cts"})
    if parser is None:
        return lang, None
    return lang, parser.parse(source)


def _text(node) -> str:
    return node.text.decode("utf-8", "replace")


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


# --------------------------------------------------------------------------- symbols

_PY_DEF = {"function_definition": "function", "class_definition": "class"}
_JS_DEF = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "abstract_class_declaration": "class",
}
_JAVA_DEF = {
    "class_declaration": "class",
    "interface_declaration": "class",
    "enum_declaration": "class",
    "record_declaration": "class",
    "annotation_type_declaration": "class",
    "method_declaration": "method",
    "constructor_declaration": "method",
}
_RUST_DEF = {
    "function_item": "function",
    "struct_item": "class",
    "enum_item": "class",
    "trait_item": "class",
    "union_item": "class",
    "mod_item": "class",
}
_JS_FN_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}


def symbols(path: str, source: bytes) -> list[Symbol]:
    """All named definitions in the file with line ranges (qualified by enclosing class/function)."""
    lang, tree = _parse(path, source)
    if tree is None:
        return []
    out: list[Symbol] = []

    def visit(node, prefix: str, parent_kind: str = "") -> None:
        name = None
        kind = None
        if lang == "python" and node.type in _PY_DEF:
            n = node.child_by_field_name("name")
            if n is not None:
                name, kind = _text(n), _PY_DEF[node.type]
                if kind == "function" and parent_kind == "class":
                    kind = "method"
        elif lang == "js":
            if node.type in _JS_DEF:
                n = node.child_by_field_name("name")
                if n is not None:
                    name, kind = _text(n), _JS_DEF[node.type]
            elif node.type == "variable_declarator":
                n, v = node.child_by_field_name("name"), node.child_by_field_name("value")
                if n is not None and v is not None and v.type in _JS_FN_VALUES and n.type == "identifier":
                    name, kind = _text(n), "function"
        elif lang == "java" and node.type in _JAVA_DEF:
            n = node.child_by_field_name("name")
            if n is not None:
                name, kind = _text(n), _JAVA_DEF[node.type]
        elif lang == "go":
            if node.type == "function_declaration":
                n = node.child_by_field_name("name")
                name, kind = (_text(n), "function") if n is not None else (None, None)
            elif node.type == "method_declaration":
                n = node.child_by_field_name("name")
                recv = _go_receiver(node)
                if n is not None:
                    name, kind = (f"{recv}.{_text(n)}" if recv else _text(n)), "method"
            elif node.type == "type_spec":
                n = node.child_by_field_name("name")
                if n is not None:
                    name, kind = _text(n), "class"
        elif lang == "rust":
            if node.type in _RUST_DEF:
                n = node.child_by_field_name("name")
                if node.type == "mod_item" and node.child_by_field_name("body") is None:
                    n = None  # `mod m;` only declares a file, it is not a definition
                if n is not None:
                    name, kind = _text(n), _RUST_DEF[node.type]
                    if kind == "function" and parent_kind == "class":
                        kind = "method"
            elif node.type == "impl_item":
                n = node.child_by_field_name("type")
                if n is not None:
                    name, kind = re.sub(r"<.*", "", _text(n)), "class"
        if name is not None:
            qualified = f"{prefix}.{name}" if prefix else name
            out.append(Symbol(qualified, kind, node.start_point[0] + 1, node.end_point[0] + 1))
            prefix, parent_kind = qualified, kind
        for child in node.children:
            visit(child, prefix, parent_kind)

    visit(tree.root_node, "")
    return out


def _go_receiver(node) -> str:
    recv = node.child_by_field_name("receiver")
    if recv is None:
        return ""
    m = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*\)?\s*$", _text(recv).strip().rstrip(")").strip())
    return m.group(1) if m else ""


def enclosing_symbol(syms: list[Symbol], first: int, last: int | None = None) -> Symbol | None:
    """Innermost symbol containing the line range; falls back to the symbol containing `first`."""
    last = last if last is not None else first
    best = None
    for s in syms:
        if s.start <= first and last <= s.end and (best is None or (s.end - s.start) < (best.end - best.start)):
            best = s
    if best is None:
        for s in syms:
            if s.start <= first <= s.end and (best is None or (s.end - s.start) < (best.end - best.start)):
                best = s
    return best


# --------------------------------------------------------------------------- imports

_PY_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*)", re.M)
_PY_FROM_RE = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\s+(\(?[^\n#]*)", re.M)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,$]+\s+from\s+)?|export\s+(?:[\w*{}\s,$]+\s+)?from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)


def imports(path: str, source: bytes) -> list[ImportRef]:
    lang, tree = _parse(path, source)
    if lang is None:
        return []
    if tree is None:
        return _imports_regex(lang, source.decode("utf-8", "replace")) if lang in {"python", "js"} else []
    if lang == "python":
        return _imports_python(tree)
    if lang == "java":
        return _imports_java(tree)
    if lang == "go":
        return _imports_go(tree)
    if lang == "rust":
        return _imports_rust(tree)
    return _imports_js(tree)


def _imports_python(tree) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in _walk(tree.root_node):
        if node.type == "import_statement":
            for c in node.children_by_field_name("name"):
                target = c.child_by_field_name("name") if c.type == "aliased_import" else c
                if target is not None:
                    refs.append(ImportRef(_text(target)))
        elif node.type == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            raw = _text(mod) if mod is not None else ""
            level = len(raw) - len(raw.lstrip("."))
            names: list[str] = []
            for c in node.children_by_field_name("name"):
                target = c.child_by_field_name("name") if c.type == "aliased_import" else c
                if target is not None:
                    names.append(_text(target))
            if any(c.type == "wildcard_import" for c in node.children):
                names.append("*")
            refs.append(ImportRef(raw.lstrip("."), level, tuple(names)))
    return refs


def _imports_js(tree) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in _walk(tree.root_node):
        if node.type in {"import_statement", "export_statement"}:
            src = node.child_by_field_name("source")
            if src is None:
                continue
            names: list[str] = []
            for d in _walk(node):
                if d.type in {"import_specifier", "export_specifier"}:
                    n = d.child_by_field_name("name")
                    if n is not None:
                        names.append(_text(n))
                elif d.type == "namespace_import" or d.type == "namespace_export":
                    names.append("*")
                elif d.type == "import_clause":
                    names.extend("default" for c in d.children if c.type == "identifier")
            if node.type == "export_statement" and not names:
                names.append("*")
            refs.append(ImportRef(_text(src).strip("'\"`"), 0, tuple(names)))
        elif node.type == "call_expression":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn is not None and args is not None and _text(fn) in {"require", "import"}:
                first = next((c for c in args.children if c.type == "string"), None)
                if first is not None:
                    refs.append(ImportRef(_text(first).strip("'\"`")))
    return refs


def _imports_java(tree) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in tree.root_node.children:
        if node.type != "import_declaration":
            continue
        ident = next((c for c in node.children if c.type in {"scoped_identifier", "identifier"}), None)
        if ident is None:
            continue
        path = _text(ident)
        if any(c.type == "asterisk" for c in node.children):
            refs.append(ImportRef(path, 0, ("*",)))  # wildcard: every class in the package
        elif any(c.type == "static" for c in node.children) and "." in path:
            cls, _, member = path.rpartition(".")
            refs.append(ImportRef(cls, 0, (member,)))
        else:
            refs.append(ImportRef(path))
    return refs


def _imports_go(tree) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in _walk(tree.root_node):
        if node.type == "import_spec":
            p = node.child_by_field_name("path")
            if p is None:
                continue
            alias = node.child_by_field_name("name")
            a = _text(alias) if alias is not None else ""
            refs.append(ImportRef(_text(p).strip('"`'), 0, (), "" if a in {"_", "."} else a))
    return refs


def _rust_use_paths(node, prefix: str = ""):
    t = node.type
    if t in {"scoped_identifier", "identifier", "crate", "self", "super"}:
        yield prefix + _text(node), ()
    elif t == "scoped_use_list":
        path, lst = node.child_by_field_name("path"), node.child_by_field_name("list")
        base = prefix + (_text(path) + "::" if path is not None else "")
        for c in lst.named_children if lst is not None else []:
            yield from _rust_use_paths(c, base)
    elif t == "use_list":
        for c in node.named_children:
            yield from _rust_use_paths(c, prefix)
    elif t == "use_as_clause":
        p = node.child_by_field_name("path")
        if p is not None:
            yield from _rust_use_paths(p, prefix)
    elif t == "use_wildcard":
        inner = next((c for c in node.named_children), None)
        yield (prefix + _text(inner) if inner is not None else prefix.rstrip(":")), ("*",)


def _imports_rust(tree) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in _walk(tree.root_node):
        if node.type == "use_declaration":
            arg = node.child_by_field_name("argument")
            for path, names in _rust_use_paths(arg) if arg is not None else []:
                refs.append(ImportRef(re.sub(r"::self$", "", path), 0, names))
        elif node.type == "mod_item" and node.child_by_field_name("body") is None:  # `mod m;` declares a child file
            n = node.child_by_field_name("name")
            if n is not None:
                refs.append(ImportRef("self::" + _text(n)))
    return refs


def _imports_regex(lang: str, text: str) -> list[ImportRef]:
    refs: list[ImportRef] = []
    if lang == "python":
        for m in _PY_IMPORT_RE.finditer(text):
            for part in m.group(1).split(","):
                refs.append(ImportRef(part.strip().split()[0]))
        for m in _PY_FROM_RE.finditer(text):
            names = [n.strip().split()[0] for n in m.group(3).strip("() \\").split(",") if n.strip()]
            refs.append(ImportRef(m.group(2), len(m.group(1)), tuple(names)))
    else:
        for m in _JS_IMPORT_RE.finditer(text):
            refs.append(ImportRef(m.group(1)))
    return refs
