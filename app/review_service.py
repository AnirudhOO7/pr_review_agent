import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.audit_log import RunAuditLog
from app.github.client import GitHubClient, parse_pr_url
from app.github.review_builder import PreparedReview, ReviewBuilder
from app.llm.reviewer import LLMReviewer
from app.models.findings import ReviewResult
from app.retrieval.retriever import CodeRetriever

RUNS_DIR = Path("runs")
PostMode = Literal["none", "dry-run", "live"]


@dataclass(frozen=True)
class ReviewRun:
    """Everything one review produced: the diff, findings, and run metadata."""

    source: str
    diff: str
    result: ReviewResult
    prepared: PreparedReview
    model: str
    latency_s: float
    retrieval_summary: dict[str, int] | None


class ReviewService:
    """Coordinates one PR review from diff fetch through optional posting."""

    def __init__(
        self,
        github: GitHubClient | None = None,
        reviewer: LLMReviewer | None = None,
        retriever: CodeRetriever | None = None,
        review_builder: ReviewBuilder | None = None,
        audit_log: RunAuditLog | None = None,
    ) -> None:
        # The GitHub client is created lazily so pasted-diff reviews work
        # without a GITHUB_TOKEN.
        self._github = github
        self._reviewer = reviewer or LLMReviewer()
        self._retriever = retriever
        self._review_builder = review_builder or ReviewBuilder()
        self._audit_log = audit_log or RunAuditLog(RUNS_DIR)
        self.last_prepared_review: PreparedReview | None = None

    @property
    def github(self) -> GitHubClient:
        if self._github is None:
            self._github = GitHubClient()
        return self._github

    def review_pr(self, pr_url: str, post_mode: PostMode = "none") -> ReviewResult:
        diff = self.github.fetch_diff(pr_url)
        run = self.review_diff(diff, source=pr_url)

        if post_mode in {"dry-run", "live"}:
            self.last_prepared_review = run.prepared

        if post_mode == "live":
            self.post_review(pr_url, run.prepared)
        return run.result

    def review_diff(self, diff: str, source: str = "pasted diff") -> ReviewRun:
        """Review a unified diff and record the run. Makes no GitHub calls."""
        context, retrieval_summary = self._retrieve_context(diff)

        start = time.perf_counter()
        result = self._reviewer.review(diff, context)
        latency_s = time.perf_counter() - start

        self._capture_run(source, diff, result, latency_s, retrieval_summary)
        return ReviewRun(
            source=source,
            diff=diff,
            result=result,
            prepared=self.prepare_review(diff, result),
            model=self._reviewer.model,
            latency_s=round(latency_s, 2),
            retrieval_summary=retrieval_summary,
        )

    def _retrieve_context(self, diff: str) -> tuple[str | None, dict[str, int] | None]:
        """Run structural retrieval if a retriever is configured."""
        if self._retriever is None:
            return None, None
        retrieved = self._retriever.retrieve(diff)
        if retrieved.is_empty:
            return None, {}
        return retrieved.render(), retrieved.summary()

    def prepare_review(self, diff: str, result: ReviewResult) -> PreparedReview:
        """Build GitHub review content without making network calls."""
        return self._review_builder.build(diff, result)

    def post_review(self, pr_url: str, prepared: PreparedReview) -> None:
        """Post a prepared review to GitHub."""
        owner, repo, pull_number = parse_pr_url(pr_url)
        self.github.create_review(
            owner,
            repo,
            pull_number,
            prepared.body,
            prepared.inline_comments,
        )

    def _capture_run(
        self,
        pr_url: str,
        diff: str,
        result: ReviewResult,
        latency_s: float,
        retrieval_summary: dict[str, int] | None = None,
    ) -> None:
        self._audit_log.record(
            pr_url=pr_url,
            model=self._reviewer.model,
            latency_s=latency_s,
            diff=diff,
            result=result,
            retrieval_summary=retrieval_summary,
        )

    def close(self) -> None:
        if self._github is not None:
            self._github.close()

    def __enter__(self) -> "ReviewService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
