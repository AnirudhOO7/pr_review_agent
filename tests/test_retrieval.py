import tempfile
import unittest
from pathlib import Path

from app.retrieval.retriever import CodeRetriever, RetrievedContext, Snippet
from app.retrieval.symbols import changed_files, changed_symbols


class SymbolExtractionTests(unittest.TestCase):
    def test_changed_files_uses_new_path_and_skips_dev_null(self) -> None:
        diff = (
            "--- a/app/foo.py\n"
            "+++ b/app/foo.py\n"
            "@@ -1 +1 @@\n"
            "+x = 1\n"
            "--- a/app/gone.py\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-y = 2\n"
        )
        self.assertEqual(changed_files(diff), ["app/foo.py"])

    def test_changed_symbols_extracts_defs_and_classes(self) -> None:
        diff = (
            "--- a/app/foo.py\n"
            "+++ b/app/foo.py\n"
            "@@ -1,2 +1,5 @@\n"
            "+def parse_pr_url(url):\n"
            "+    return url\n"
            "+class Reviewer:\n"
            " def untouched():\n"
            "+    pass\n"
        )
        self.assertEqual(
            changed_symbols(diff), {"parse_pr_url", "Reviewer", "untouched"}
        )


class CodeRetrieverTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, content: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_finds_callers_and_tests_outside_the_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # The changed file (should be excluded from results).
            self._write(root, "app/core.py", "def compute():\n    return 1\n")
            # A caller elsewhere.
            self._write(
                root, "app/caller.py", "from app.core import compute\n\nx = compute()\n"
            )
            # A test referencing it.
            self._write(
                root,
                "tests/test_core.py",
                "from app.core import compute\n\ndef test_compute():\n    assert compute() == 1\n",
            )

            diff = (
                "--- a/app/core.py\n"
                "+++ b/app/core.py\n"
                "@@ -1,2 +1,2 @@\n"
                "+def compute():\n"
                "+    return 2\n"
            )
            ctx = CodeRetriever(root).retrieve(diff)

            paths = {s.path for s in ctx.snippets}
            self.assertIn("app/caller.py", paths)
            self.assertIn("tests/test_core.py", paths)
            self.assertNotIn("app/core.py", paths)  # the diff file is excluded

            kinds = ctx.summary()
            self.assertGreaterEqual(kinds.get("caller", 0), 1)
            self.assertGreaterEqual(kinds.get("test", 0), 1)

    def test_resolves_local_import_to_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(
                root, "app/helpers.py", "def helper():\n    return 'help'\n"
            )
            self._write(
                root,
                "app/service.py",
                "from app.helpers import helper\n\ndef run():\n    return helper()\n",
            )

            diff = (
                "--- a/app/service.py\n"
                "+++ b/app/service.py\n"
                "@@ -3,2 +3,2 @@\n"
                "+def run():\n"
                "+    return helper() or 0\n"
            )
            ctx = CodeRetriever(root).retrieve(diff)

            imports = [s for s in ctx.snippets if s.kind == "import"]
            self.assertTrue(
                any(s.path == "app/helpers.py" and s.symbol == "helper" for s in imports)
            )

    def test_render_is_empty_for_no_snippets(self) -> None:
        self.assertEqual(RetrievedContext().render(), "")
        self.assertTrue(RetrievedContext().is_empty)

    def test_render_groups_by_kind(self) -> None:
        ctx = RetrievedContext(
            snippets=[
                Snippet("a.py", "caller", "f", 3, "  3 | f()"),
                Snippet("tests/test_a.py", "test", "f", 9, "  9 | f()"),
            ]
        )
        rendered = ctx.render()
        self.assertIn("Callers of changed symbols", rendered)
        self.assertIn("Related tests", rendered)
        self.assertIn("a.py", rendered)


if __name__ == "__main__":
    unittest.main()
