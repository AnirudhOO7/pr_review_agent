import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.github.client import GitHubClient
from app.llm.reviewer import LLMReviewer
from app.models.findings import ReviewResult

RUNS_DIR = Path("runs")

class ReviewService:
    def __init__(self, github: GitHubClient | None = None, reviewer: LLMReviewer | None = None)-> None:
        self._github = github or GitHubClient()
        self._reviewer = reviewer or LLMReviewer()

    def review_pr(self, pr_url:str)->ReviewResult:
        diff = self._github.fetch_diff(pr_url)

        start = time.perf_counter()
        result = self._reviewer.review(diff)
        latency_s = time.perf_counter() - start

        self._capture_run(pr_url, diff, result, latency_s)
        return result

    def _capture_run(self, pr_url: str, diff: str, result: ReviewResult, latency_s: float) -> None:
        RUNS_DIR.mkdir(exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pr_url": pr_url,
            "model": self._reviewer.model,
            "latency_s": round(latency_s, 2),
            "diff": diff,
            "findings": [f.model_dump() for f in result.findings],
        }
        with (RUNS_DIR / "runs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def close(self) -> None:
        self._github.close()

    def __enter__(self) -> "ReviewService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()        