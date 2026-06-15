"""Structural retrieval over a local checkout.

Given a diff and the repository it applies to, pull the code the diff depends on
without embeddings or a vector store: grep the working tree for callers of the
changed symbols, resolve the changed files' imports, and surface related tests.
The result is rendered alongside the diff so the reviewer sees the blast radius
of a change, not just the change itself.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.retrieval.symbols import changed_files, changed_symbols

SnippetKind = Literal["caller", "import", "test"]

# Source extensions we are willing to read. Keeps the walk off binaries, data,
# and lockfiles.
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java",
    ".rb", ".rs", ".c", ".h", ".cpp", ".cc", ".cs", ".php",
}
_IGNORED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".tox", ".idea",
}
_MAX_FILE_BYTES = 512 * 1024

_PY_FROM_IMPORT = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.+)")
_PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)")


@dataclass(frozen=True)
class Snippet:
    """A slice of code retrieved from outside the diff."""

    path: str
    kind: SnippetKind
    symbol: str
    line: int
    text: str


@dataclass(frozen=True)
class RetrievedContext:
    """Everything structural retrieval found for one diff."""

    snippets: list[Snippet] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.snippets

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.snippets:
            counts[s.kind] = counts.get(s.kind, 0) + 1
        return counts

    def render(self) -> str:
        """Format the snippets for inclusion in the review prompt."""
        if self.is_empty:
            return ""
        headings: list[tuple[SnippetKind, str]] = [
            ("caller", "Callers of changed symbols (outside the diff)"),
            ("import", "Imported modules the diff depends on"),
            ("test", "Related tests"),
        ]
        blocks: list[str] = ["# Repository context retrieved for this diff"]
        for kind, title in headings:
            group = [s for s in self.snippets if s.kind == kind]
            if not group:
                continue
            blocks.append(f"\n## {title}")
            for s in group:
                blocks.append(f"\n`{s.path}` (around line {s.line}, re: `{s.symbol}`)")
                blocks.append(f"```\n{s.text}\n```")
        return "\n".join(blocks)


class CodeRetriever:
    """Finds the code a diff depends on by scanning a local checkout."""

    def __init__(
        self,
        repo_path: str | Path,
        *,
        context_lines: int = 2,
        max_per_kind: int = 8,
    ) -> None:
        self._root = Path(repo_path).resolve()
        if not self._root.is_dir():
            raise NotADirectoryError(f"Repo path is not a directory: {self._root}")
        self._context_lines = context_lines
        self._max_per_kind = max_per_kind

    def retrieve(self, diff: str) -> RetrievedContext:
        changed = set(changed_files(diff))
        symbols = changed_symbols(diff)

        snippets: list[Snippet] = []
        if symbols:
            snippets.extend(self._find_references(symbols, changed))
        snippets.extend(self._find_imports(changed))
        return RetrievedContext(snippets=snippets)

    # -- references (callers + tests) -------------------------------------

    def _find_references(
        self, symbols: set[str], changed: set[str]
    ) -> list[Snippet]:
        """Lines outside the changed files that mention a changed symbol."""
        word = re.compile(r"\b(" + "|".join(re.escape(s) for s in symbols) + r")\b")
        callers: list[Snippet] = []
        tests: list[Snippet] = []

        for path in self._source_files():
            rel = self._rel(path)
            if rel in changed:
                continue
            lines = self._read_lines(path)
            if lines is None:
                continue
            is_test = _is_test_path(rel)
            bucket = tests if is_test else callers
            limit = self._max_per_kind
            for i, line in enumerate(lines):
                if len(bucket) >= limit:
                    break
                match = word.search(line)
                if match:
                    bucket.append(
                        Snippet(
                            path=rel,
                            kind="test" if is_test else "caller",
                            symbol=match.group(1),
                            line=i + 1,
                            text=self._excerpt(lines, i),
                        )
                    )
            if len(callers) >= self._max_per_kind and len(tests) >= self._max_per_kind:
                break

        return callers + tests

    # -- imports ----------------------------------------------------------

    def _find_imports(self, changed: set[str]) -> list[Snippet]:
        """Resolve Python imports in changed files to their local definitions."""
        snippets: list[Snippet] = []
        seen: set[str] = set()
        for rel in sorted(changed):
            if not rel.endswith(".py"):
                continue
            path = self._root / rel
            lines = self._read_lines(path)
            if lines is None:
                continue
            for module, names in self._iter_py_imports(lines):
                target = self._resolve_module(module)
                if target is None or self._rel(target) in changed:
                    continue
                key = self._rel(target)
                if key in seen or len(snippets) >= self._max_per_kind:
                    continue
                seen.add(key)
                snippets.append(self._import_snippet(target, module, names))
        return snippets

    def _iter_py_imports(self, lines: list[str]):
        for line in lines:
            from_match = _PY_FROM_IMPORT.match(line)
            if from_match:
                names = [n.strip() for n in from_match.group(2).split(",")]
                yield from_match.group(1), names
                continue
            import_match = _PY_IMPORT.match(line)
            if import_match:
                yield import_match.group(1), []

    def _resolve_module(self, module: str) -> Path | None:
        """Map a dotted module path to a file inside the repo, if it's local."""
        parts = module.split(".")
        candidates = [
            self._root.joinpath(*parts).with_suffix(".py"),
            self._root.joinpath(*parts, "__init__.py"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _import_snippet(
        self, target: Path, module: str, names: list[str]
    ) -> Snippet:
        lines = self._read_lines(target) or []
        # Prefer the definition of the first imported name; fall back to the head.
        for name in names:
            for i, line in enumerate(lines):
                if re.match(rf"\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b", line):
                    return Snippet(
                        path=self._rel(target),
                        kind="import",
                        symbol=name,
                        line=i + 1,
                        text=self._excerpt(lines, i, after=self._context_lines + 4),
                    )
        head = "\n".join(lines[:12])
        return Snippet(
            path=self._rel(target),
            kind="import",
            symbol=module,
            line=1,
            text=head,
        )

    # -- filesystem helpers ----------------------------------------------

    def _source_files(self):
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.suffix not in _SOURCE_EXTENSIONS:
                continue
            if any(part in _IGNORED_DIRS for part in path.relative_to(self._root).parts):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path

    def _read_lines(self, path: Path) -> list[str] | None:
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return None

    def _excerpt(self, lines: list[str], index: int, after: int | None = None) -> str:
        before = self._context_lines
        end_pad = after if after is not None else self._context_lines
        start = max(0, index - before)
        end = min(len(lines), index + end_pad + 1)
        out = []
        for i in range(start, end):
            out.append(f"{i + 1:>5} | {lines[i]}")
        return "\n".join(out)

    def _rel(self, path: Path) -> str:
        return str(path.resolve().relative_to(self._root))


def _is_test_path(rel_path: str) -> bool:
    lowered = rel_path.lower()
    parts = lowered.replace("\\", "/").split("/")
    name = parts[-1]
    if any(p in {"test", "tests", "__tests__", "spec"} for p in parts[:-1]):
        return True
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "test" in name
        or "spec" in name
    )
