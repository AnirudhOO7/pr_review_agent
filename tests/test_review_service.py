import json
import tempfile
import unittest
from pathlib import Path

from app.audit_log import RunAuditLog
from app.github.review_builder import InlineComment
from app.models.findings import PRFinding, ReviewResult
from app.review_service import ReviewService


class FakeGitHubClient:
    def __init__(self) -> None:
        self.created_reviews = []

    def create_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        body: str,
        comments: list[InlineComment],
    ) -> None:
        self.created_reviews.append((owner, repo, pull_number, body, comments))

    def close(self) -> None:
        pass


class FakeReviewer:
    model = "test-model"

    def __init__(self, result: ReviewResult | None = None) -> None:
        self.result = result or ReviewResult(findings=[])

    def review(self, diff: str, context: str | None = None) -> ReviewResult:
        self.last_context = context
        return self.result


class ReviewServiceRunCaptureTests(unittest.TestCase):
    def test_capture_run_appends_jsonl_record(self) -> None:
        result = ReviewResult(
            findings=[
                PRFinding(
                    file="app/example.py",
                    line=10,
                    severity="major",
                    category="correctness",
                    issue="Return value can be None.",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            service = ReviewService(
                github=FakeGitHubClient(),
                reviewer=FakeReviewer(),
                audit_log=RunAuditLog(runs_dir),
            )

            service._capture_run(
                "https://github.com/owner/repo/pull/1",
                "diff --git a/app/example.py b/app/example.py",
                result,
                1.236,
            )

            records = (runs_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 1)

            record = json.loads(records[0])
            self.assertEqual(record["pr_url"], "https://github.com/owner/repo/pull/1")
            self.assertEqual(record["model"], "test-model")
            self.assertEqual(record["latency_s"], 1.24)
            self.assertEqual(record["findings"][0]["file"], "app/example.py")

    def test_review_pr_dry_run_prepares_without_posting(self) -> None:
        github = FakeGitHubClient()
        github.fetch_diff = lambda pr_url: (
            "--- a/app/example.py\n"
            "+++ b/app/example.py\n"
            "@@ -1,0 +1,1 @@\n"
            "+new\n"
        )
        result = ReviewResult(
            findings=[
                PRFinding(
                    file="app/example.py",
                    line=1,
                    severity="major",
                    category="correctness",
                    issue="Inline issue.",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            service = ReviewService(
                github=github,
                reviewer=FakeReviewer(result),
                audit_log=RunAuditLog(Path(tmpdir) / "runs"),
            )
            service.review_pr(
                "https://github.com/owner/repo/pull/1",
                post_mode="dry-run",
            )

        self.assertIsNotNone(service.last_prepared_review)
        self.assertEqual(len(service.last_prepared_review.inline_comments), 1)
        self.assertEqual(github.created_reviews, [])

    def test_review_pr_live_posts_prepared_review(self) -> None:
        github = FakeGitHubClient()
        github.fetch_diff = lambda pr_url: (
            "--- a/app/example.py\n"
            "+++ b/app/example.py\n"
            "@@ -1,0 +1,1 @@\n"
            "+new\n"
        )
        result = ReviewResult(
            findings=[
                PRFinding(
                    file="app/example.py",
                    line=1,
                    severity="major",
                    category="correctness",
                    issue="Inline issue.",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            service = ReviewService(
                github=github,
                reviewer=FakeReviewer(result),
                audit_log=RunAuditLog(Path(tmpdir) / "runs"),
            )
            service.review_pr(
                "https://github.com/owner/repo/pull/1",
                post_mode="live",
            )

        self.assertEqual(len(github.created_reviews), 1)
        owner, repo, pull_number, _body, comments = github.created_reviews[0]
        self.assertEqual((owner, repo, pull_number), ("owner", "repo", 1))
        self.assertEqual(comments[0]["path"], "app/example.py")


if __name__ == "__main__":
    unittest.main()
