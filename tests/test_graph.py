from surgeon import langs
from surgeon.graph import ImportGraph


def graph(files: dict[str, str]) -> ImportGraph:
    return ImportGraph({p: s.encode() for p, s in files.items()})


def test_python_absolute_relative_and_submodule_imports():
    g = graph(
        {
            "pkg/__init__.py": "",
            "pkg/core.py": "def f(): pass\ndef g(): pass\n",
            "pkg/util.py": "from .core import f\n",
            "pkg/sub/__init__.py": "",
            "pkg/sub/deep.py": "from ..core import g\nfrom .. import util\n",
            "app.py": "import pkg.core\nfrom pkg import util\n",
            "tests/test_core.py": "from pkg.core import f\n",
        }
    )
    assert g.direct_importers("pkg/core.py") == ["app.py", "pkg/sub/deep.py", "pkg/util.py", "tests/test_core.py"]
    assert g.direct_importers("pkg/util.py") == ["app.py", "pkg/sub/deep.py"]
    b = g.blast("pkg/core.py", "f")
    assert (b.direct, b.direct_non_test) == (4, 3)
    assert b.symbol_importers == 2  # util and the test import f; app.py imports the module but never mentions f; deep imports only g
    assert g.blast("pkg/core.py", "g").symbol_importers == 1


def test_src_layout_root_detected():
    g = graph({"src/lib/__init__.py": "", "src/lib/a.py": "", "src/lib/b.py": "from lib.a import x\n"})
    assert g.direct_importers("src/lib/a.py") == ["src/lib/b.py"]


def test_js_relative_resolution():
    g = graph(
        {
            "src/a.ts": "export const x = 1;",
            "src/dir/index.ts": "export const y = 2;",
            "src/b.ts": "import { x } from './a';\nimport {y} from './dir';\nconst z = require('./a');",
            "src/c.ts": "import x from './a.js';",
            "src/d.ts": "import react from 'react';",
        }
    )
    assert g.direct_importers("src/a.ts") == ["src/b.ts", "src/c.ts"]
    assert g.direct_importers("src/dir/index.ts") == ["src/b.ts"]


def test_new_file_has_no_blast():
    assert graph({"a.py": ""}).blast("missing.py").direct == 0


def test_symbols_qualified_names_and_enclosing():
    src = b"class A:\n    def m(self):\n        x = 1\n\ndef top():\n    pass\n"
    syms = langs.symbols("a.py", src)
    assert [s.name for s in syms] == ["A", "A.m", "top"]
    assert langs.enclosing_symbol(syms, 3).name == "A.m"
    assert langs.enclosing_symbol(syms, 6).name == "top"
