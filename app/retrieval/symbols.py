"""Extract the changed files and the symbols defined in a unified diff.

The symbols a diff *defines* (functions, classes) are the anchors for structural
retrieval: once we know that `parse_pr_url` was touched, we can grep the rest of
the repo for its callers and tests.
"""

import re

# Definition patterns across common languages. Each captures the symbol name in
# group 1. Matched against the content of added/changed diff lines.
_DEFINITION_PATTERNS = (
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),                 # Python
    re.compile(r"^\s*class\s+(\w+)"),                            # Python / many
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)"),            # Go
    re.compile(r"\bfunction\s+(\w+)"),                          # JS / TS
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*="),  # JS / TS
    re.compile(r"^\s*(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+(\w+)\s*\("),  # Java / C-like
)


def changed_files(diff: str) -> list[str]:
    """New-side file paths touched by the diff (deleted files excluded)."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[len("+++ ") :].strip()
            if path == "/dev/null":
                continue
            if path.startswith("b/"):
                path = path[2:]
            if path not in files:
                files.append(path)
    return files


def changed_symbols(diff: str) -> set[str]:
    """Names of functions/classes defined on added or context lines of the diff.

    Both added (`+`) and context (` `) lines are considered: a one-line change
    inside a function body shows the body as `+` and the `def` as context, and
    we still want that enclosing symbol.
    """
    symbols: set[str] = set()
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line.startswith(("+", " ")):
            content = line[1:]
            for pattern in _DEFINITION_PATTERNS:
                match = pattern.match(content)
                if match:
                    symbols.add(match.group(1))
    return symbols
