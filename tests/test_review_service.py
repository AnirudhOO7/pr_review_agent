import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.findings import PRFinding, ReviewResult
from app.review_service import ReviewService


class FakeGitHubClient:
    def close(self) -> None:
        pass


class FakeReviewer:
    model = "test-model"


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
            service = ReviewService(github=FakeGitHubClient(), reviewer=FakeReviewer())

            with patch("app.review_service.RUNS_DIR", runs_dir):
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


if __name__ == "__main__":
    unittest.main()
