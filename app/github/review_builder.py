"""Build GitHub review payloads from model findings."""

from dataclasses import dataclass
from typing import Literal, TypedDict

from app.github.diff_parser import commentable_lines
from app.models.findings import PRFinding, ReviewResult


class InlineComment(TypedDict):
    """A GitHub inline review comment payload."""

    path: str
    line: int
    side: Literal["RIGHT"]
    body: str


@dataclass(frozen=True)
class PreparedReview:
    """GitHub review payload built from model findings."""

    body: str
    inline_comments: list[InlineComment]
    general_findings: list[PRFinding]


class ReviewBuilder:
    """Separates inline comments from summary-only findings."""

    def build(self, diff: str, result: ReviewResult) -> PreparedReview:
        commentable = commentable_lines(diff)

        inline_comments: list[InlineComment] = []
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
        inline_comments: list[InlineComment],
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
