"""Rule-based risk signals: pattern matching on paths and changed lines, no model.

A hunk that carries one of these is worth a careful look. The report marks it risky unless the issue asked for it.
All rules are static text patterns, so they miss what they cannot see (multi-line signatures, indirect calls).
"""

from __future__ import annotations

import posixpath
import re

WHY = {
    "risk:ci": "changes CI/workflow configuration",
    "risk:crypto": "touches authentication or cryptography code",
    "risk:dependency": "adds a dependency",
    "risk:shell_network": "adds a shell or network call",
    "risk:tests_removed": "removes tests",
    "risk:signature": "changes a public function signature",
}

CI_MARKERS = (".github/workflows/", ".github/actions/", ".circleci/", ".buildkite/", ".gitlab-ci", "azure-pipelines", ".travis.yml")
CI_NAMES = {"jenkinsfile", "cloudbuild.yaml", "bitbucket-pipelines.yml"}
CRYPTO_PATH = re.compile(
    r"(?:^|[/_.-])(?:crypto\w*|auth(?:n|z|entic\w*|oris\w*|oriz\w*)?|security|ssl|tls|jwt|oauth\w*|passwords?|secrets?|hmac|cipher\w*)(?:[/_.-]|$)"
)
CRYPTO_LINE = re.compile(
    r"hashlib\.|hmac\.|bcrypt|argon2|scrypt|pbkdf2|createCipher|createHash|createHmac|crypto\.subtle|jsonwebtoken"
    r"|jwt\.(?:encode|decode|sign|verify)|verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify"
    r"|_create_unverified|\b(?:AES|RSA|MD5|SHA-?(?:1|256|512))\b",
    re.I,
)
SHELL_NET_LINE = re.compile(
    r"subprocess\.|os\.system\(|os\.popen\(|\bPopen\(|child_process|\bexecSync\(|Runtime\.getRuntime\(\)\.exec|ProcessBuilder"
    r"|exec\.Command\(|Command::new\(|\bcurl\s|\bwget\s|requests\.(?:get|post|put|patch|delete)\(|urllib\.request|urlopen\("
    r"|httpx\.(?:get|post|put|patch|delete|Client|AsyncClient)\b|\bfetch\(|\baxios[.(]|http\.(?:Get|Post)\(|net/http"
    r"|XMLHttpRequest|socket\.socket|HttpClient|reqwest::"
)
MANIFESTS = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "cargo.toml",
    "go.mod",
    "gemfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "composer.json",
}
_NOT_DEPS = {"version", "name", "description", "requires-python", "python", "node", "npm", "license", "main", "type"}
_DEP = [
    re.compile(r'^\s*"([@\w./-]+)"\s*:\s*"[\^~<>=*]*\d'),  # package.json
    re.compile(r"^\s*[\"']?([A-Za-z][\w.-]*)(?:\[[^\]]*\])?\s*(?:[<>=!~]=|===?)\s*\d"),  # requirements.txt, pyproject dependencies
    re.compile(r"^\s*([A-Za-z][\w-]*)\s*=\s*(?:\"[\^~<>=]*\d|\{\s*version)"),  # Cargo.toml
    re.compile(r"^\s*(?:require\s+)?([\w.-]+\.[\w./-]+)\s+v\d"),  # go.mod
    re.compile(r"^\s*gem\s+['\"]([\w-]+)['\"]"),  # Gemfile
    re.compile(r"<artifactId>([^<]+)</artifactId>"),  # pom.xml
]
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+test|^\s*(?:it|test|describe)\(|@Test\b|^\s*func\s+Test|#\[test\]|^\s*fn\s+test_")
_SIG = [
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z]\w*)\s*\(([^)]*)\)"),  # Python; names starting with _ are private
    re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z]\w*)\s*\(([^)]*)\)"),  # JS/TS exports
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)\s*\(([^)]*)\)"),  # Go exported
    re.compile(r"^\s*pub(?:\([^)]*\))?\s+(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"),  # Rust pub
    re.compile(r"^\s*public\s+[\w<>\[\],.? ]+?\s+(\w+)\s*\(([^)]*)\)"),  # Java public
]


def is_ci(path: str) -> bool:
    p = path.lower()
    return any(m in p for m in CI_MARKERS) or posixpath.basename(p) in CI_NAMES


def new_dependencies(path: str, added: list[str], removed: list[str]) -> set[str]:
    if posixpath.basename(path.lower()) not in MANIFESTS:
        return set()

    def names(lines: list[str]) -> set[str]:
        out = set()
        for line in lines:
            for rx in _DEP:
                m = rx.match(line) or (rx.search(line) if rx.pattern.startswith("<") else None)
                if m and m[1].lower() not in _NOT_DEPS:
                    out.add(m[1].lower())
                    break
        return out

    return names(added) - names(removed)


def _signatures(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        for rx in _SIG:
            m = rx.match(line)
            if m and not m[1].startswith("_"):
                out[m[1]] = re.sub(r"\s+", "", m[2])
                break
    return out


def changed_signatures(added: list[str], removed: list[str]) -> list[str]:
    before, after = _signatures(removed), _signatures(added)
    return sorted(n for n in before if n in after and before[n] != after[n])


def signals(path: str, kind: str, added: list[str], removed: list[str]) -> list[str]:
    """Risk tags for one hunk. Tests and docs only ever raise the 'tests removed' tag."""
    tags: list[str] = []
    if kind == "test":
        if sum(bool(_TEST_DEF.match(x)) for x in removed) > sum(bool(_TEST_DEF.match(x)) for x in added):
            tags.append("risk:tests_removed")
        return tags
    if kind == "docs":
        return tags
    if is_ci(path):
        tags.append("risk:ci")
    if CRYPTO_PATH.search(path.lower()) or any(CRYPTO_LINE.search(x) for x in added + removed):
        tags.append("risk:crypto")
    if new_dependencies(path, added, removed):
        tags.append("risk:dependency")
    if kind != "config" and any(SHELL_NET_LINE.search(x) for x in added):
        tags.append("risk:shell_network")
    if changed_signatures(added, removed):
        tags.append("risk:signature")
    return tags


def explain(tags: list[str]) -> str:
    return "; ".join(WHY[t] for t in tags if t in WHY)
