import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.github.client import GitHubClient, parse_pr_url
from app.github.diff_parser import commentable_lines
from app.llm.reviewer import LLMReviewer
from app.models.findings import PRFinding, ReviewResult
from app.retrieval.retriever import CodeRetriever

RUNS_DIR = Path("runs")
PostMode = Literal["none", "dry-run", "live"]


@dataclass(frozen=True)
class PreparedReview:
    """GitHub review payload built from model findings."""

    body: str
    inline_comments: list[dict]
    general_findings: list[PRFinding]


class ReviewService:
    def __init__(
        self,
        github: GitHubClient | None = None,
        reviewer: LLMReviewer | None = None,
        retriever: CodeRetriever | None = None,
    ) -> None:
        self._github = github or GitHubClient()
        self._reviewer = reviewer or LLMReviewer()
        self._retriever = retriever
        self.last_prepared_review: PreparedReview | None = None

    def review_pr(self, pr_url: str, post_mode: PostMode = "none") -> ReviewResult:
        diff = self._github.fetch_diff(pr_url)
        context, retrieval_summary = self._retrieve_context(diff)

        start = time.perf_counter()
        result = self._reviewer.review(diff, context)
        latency_s = time.perf_counter() - start

        self._capture_run(pr_url, diff, result, latency_s, retrieval_summary)

        if post_mode in {"dry-run", "live"}:
            self.last_prepared_review = self.prepare_review(diff, result)

        if post_mode == "live":
            self.post_review(pr_url, self.last_prepared_review)
        return result

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
        commentable = commentable_lines(diff)

        inline_comments: list[dict] = []
        general_findings: list[PRFinding] = []
        for finding in result.findings:
            if self._can_comment_inline(finding, commentable):
                inline_comments.append(
                    {
                        "path": finding.file,
                        "line": finding.line,
                        "side": "RIGHT",
                        "body": self._comment_body(finding),
                    }
                )
            else:
                general_findings.append(finding)

        body = self._summary_body(result.findings, inline_comments, general_findings)
        return PreparedReview(body, inline_comments, general_findings)

    def post_review(self, pr_url: str, prepared: PreparedReview) -> None:
        """Post a prepared review to GitHub."""
        owner, repo, pull_number = parse_pr_url(pr_url)
        self._github.create_review(
            owner,
            repo,
            pull_number,
            prepared.body,
            prepared.inline_comments,
        )

    @staticmethod
    def _can_comment_inline(
        finding: PRFinding,
        commentable: dict[str, set[int]],
    ) -> bool:
        return (
            finding.line is not None
            and finding.line in commentable.get(finding.file, set())
        )

    @staticmethod
    def _comment_body(finding: PRFinding) -> str:
        return f"**[{finding.severity}/{finding.category}]** {finding.issue}"

    @staticmethod
    def _summary_body(
        all_findings: list[PRFinding],
        inline_comments: list[dict],
        general_findings: list[PRFinding],
    ) -> str:
        if not all_findings:
            return "Automated review: no issues found."

        lines = [
            f"Automated review: {len(all_findings)} finding(s), "
            f"{len(inline_comments)} can be posted inline."
        ]

        if general_findings:
            lines.append("")
            lines.append("Findings that could not be tied to a changed line:")
            for finding in general_findings:
                location = f"`{finding.file}`"
                if finding.line is not None:
                    location += f":{finding.line}"
                lines.append(
                    f"- {location} **[{finding.severity}/{finding.category}]** "
                    f"{finding.issue}"
                )
        return "\n".join(lines)

    def _capture_run(
        self,
        pr_url: str,
        diff: str,
        result: ReviewResult,
        latency_s: float,
        retrieval_summary: dict[str, int] | None = None,
    ) -> None:
        RUNS_DIR.mkdir(exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pr_url": pr_url,
            "model": self._reviewer.model,
            "latency_s": round(latency_s, 2),
            "retrieval": retrieval_summary,
            "diff": diff,
            "findings": [finding.model_dump() for finding in result.findings],
        }
        with (RUNS_DIR / "runs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def close(self) -> None:
        self._github.close()

    def __enter__(self) -> "ReviewService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
