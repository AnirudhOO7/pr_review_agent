import unittest

from app.github.review_builder import ReviewBuilder
from app.models.findings import PRFinding, ReviewResult


class ReviewBuilderTests(unittest.TestCase):
    def test_splits_inline_and_summary_findings(self) -> None:
        result = ReviewResult(
            findings=[
                PRFinding(
                    file="app/example.py",
                    line=2,
                    severity="major",
                    category="correctness",
                    issue="Inline issue.",
                ),
                PRFinding(
                    file="app/example.py",
                    line=99,
                    severity="minor",
                    category="style",
                    issue="Summary issue.",
                ),
            ]
        )
        diff = (
            "--- a/app/example.py\n"
            "+++ b/app/example.py\n"
            "@@ -1,1 +1,2 @@\n"
            " old\n"
            "+new\n"
        )

        prepared = ReviewBuilder().build(diff, result)

        self.assertEqual(len(prepared.inline_comments), 1)
        self.assertEqual(prepared.inline_comments[0]["line"], 2)
        self.assertEqual(len(prepared.general_findings), 1)
        self.assertIn("Summary issue.", prepared.body)

    def test_empty_review_has_clear_summary(self) -> None:
        prepared = ReviewBuilder().build("diff", ReviewResult(findings=[]))

        self.assertEqual(prepared.body, "Automated review: no issues found.")
        self.assertEqual(prepared.inline_comments, [])
        self.assertEqual(prepared.general_findings, [])


if __name__ == "__main__":
    unittest.main()
