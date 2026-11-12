import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.models.findings import PRFinding, ReviewResult
from app.web import server

DIFF = (
    "--- a/app/example.py\n"
    "+++ b/app/example.py\n"
    "@@ -1,0 +1,2 @@\n"
    "+def f(x):\n"
    "+    return 1 / x\n"
)


class FakeReviewer:
    model = "test-model"

    def __init__(self, *args, **kwargs) -> None:
        pass

    def review(self, diff: str, context: str | None = None) -> ReviewResult:
        return ReviewResult(
            findings=[
                PRFinding(
                    file="app/example.py",
                    line=2,
                    severity="major",
                    category="correctness",
                    issue="Division by zero when x == 0.",
                ),
                PRFinding(
                    file="app/other.py",
                    line=9,
                    severity="minor",
                    category="style",
                    issue="Not in the diff.",
                ),
            ]
        )


class WebServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runs_dir = Path(self.tmp.name) / "runs"
        patches = [
            mock.patch.object(server, "RUNS_DIR", self.runs_dir),
            mock.patch.object(server, "LLMReviewer", FakeReviewer),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.client = TestClient(server.app)

    def test_index_serves_html(self) -> None:
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("PR Review Agent", res.text)

    def test_review_pasted_diff_returns_findings_and_github_preview(self) -> None:
        res = self.client.post("/api/review", json={"diff": DIFF})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["source"], "pasted diff")
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(len(body["findings"]), 2)
        self.assertEqual(len(body["github_review"]["inline_comments"]), 1)
        self.assertEqual(body["github_review"]["summary_only"][0]["file"], "app/other.py")

    def test_review_is_recorded_in_history(self) -> None:
        self.client.post("/api/review", json={"diff": DIFF})
        runs = self.client.get("/api/runs").json()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["num_findings"], 2)
        self.assertEqual(runs[0]["severities"], {"major": 1, "minor": 1})

        detail = self.client.get(f"/api/runs/{runs[0]['id']}").json()
        self.assertEqual(detail["diff"], DIFF)

    def test_review_requires_exactly_one_source(self) -> None:
        self.assertEqual(self.client.post("/api/review", json={}).status_code, 422)
        both = {"diff": DIFF, "pr_url": "https://github.com/o/r/pull/1"}
        self.assertEqual(self.client.post("/api/review", json=both).status_code, 422)

    def test_review_rejects_missing_repo_path(self) -> None:
        res = self.client.post(
            "/api/review", json={"diff": DIFF, "repo_path": "/no/such/dir"}
        )
        self.assertEqual(res.status_code, 400)

    def test_samples_come_from_eval_cases(self) -> None:
        samples = self.client.get("/api/samples").json()
        self.assertTrue(samples)
        buggy = [s for s in samples if s["label"] == "buggy"]
        self.assertTrue(all(s["expected"] for s in buggy))

    def test_eval_report_missing_returns_404(self) -> None:
        with mock.patch.object(server, "EVAL_REPORT", Path(self.tmp.name) / "none.json"):
            self.assertEqual(self.client.get("/api/eval").status_code, 404)

    def test_eval_report_is_served(self) -> None:
        report = Path(self.tmp.name) / "report.json"
        report.write_text(json.dumps({"metrics": {"recall": 1.0}}))
        with mock.patch.object(server, "EVAL_REPORT", report):
            self.assertEqual(self.client.get("/api/eval").json()["metrics"]["recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
