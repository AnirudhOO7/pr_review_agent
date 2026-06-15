import unittest

from app.github.diff_parser import commentable_lines


class CommentableLinesTests(unittest.TestCase):
    def test_added_and_context_lines_are_commentable(self) -> None:
        diff = (
            "diff --git a/app/example.py b/app/example.py\n"
            "index 111..222 100644\n"
            "--- a/app/example.py\n"
            "+++ b/app/example.py\n"
            "@@ -10,3 +10,4 @@ def f():\n"
            " context_a\n"
            "+added_b\n"
            " context_c\n"
            " context_d\n"
        )
        # New-file lines: 10=context_a, 11=added_b, 12=context_c, 13=context_d
        self.assertEqual(commentable_lines(diff), {"app/example.py": {10, 11, 12, 13}})

    def test_deleted_lines_do_not_advance_new_counter(self) -> None:
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -5,3 +5,2 @@\n"
            " keep\n"
            "-gone\n"
            "+replacement\n"
        )
        # 5=keep, deletion skipped, 6=replacement
        self.assertEqual(commentable_lines(diff), {"foo.py": {5, 6}})

    def test_multiple_files_tracked_separately(self) -> None:
        diff = (
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,1 +1,2 @@\n"
            " x\n"
            "+y\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -1,0 +1,1 @@\n"
            "+z\n"
        )
        self.assertEqual(commentable_lines(diff), {"a.py": {1, 2}, "b.py": {1}})

    def test_deleted_file_is_ignored(self) -> None:
        diff = (
            "--- a/gone.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-line_one\n"
            "-line_two\n"
        )
        self.assertEqual(commentable_lines(diff), {})


if __name__ == "__main__":
    unittest.main()
