"""Run the reviewer over the dataset and score the results.

The reviewer is injected so the harness can be exercised with a fake in tests
(deterministic, no network) and with the real `LLMReviewer` for an actual eval.
"""

from dataclasses import dataclass
from typing import Callable, Protocol

from app.models.findings import ReviewResult
from app.retrieval.retriever import CodeRetriever
from evals.dataset import Case
from evals.scoring import CaseResult, DEFAULT_TOLERANCE, score_case


class Reviewer(Protocol):
    def review(self, diff: str, context: str | None = None) -> ReviewResult: ...


@dataclass
class CaseRun:
    """A scored case plus the raw findings, kept for the detailed report."""

    result: CaseResult
    findings_repr: list[str]


def run_eval(
    cases: list[Case],
    reviewer: Reviewer,
    *,
    retrieval: bool = False,
    tolerance: int = DEFAULT_TOLERANCE,
    on_case: Callable[[Case, CaseResult], None] | None = None,
) -> list[CaseRun]:
    """Review and score every case. Returns one CaseRun per case, in order."""
    runs: list[CaseRun] = []
    for case in cases:
        context = _context_for(case) if retrieval else None
        review = reviewer.review(case.diff, context)
        result = score_case(case, review.findings, tolerance)
        runs.append(
            CaseRun(
                result=result,
                findings_repr=[_finding_repr(f) for f in review.findings],
            )
        )
        if on_case is not None:
            on_case(case, result)
    return runs


def _context_for(case: Case) -> str | None:
    if not case.repo_path:
        return None
    rendered = CodeRetriever(case.repo_path).retrieve(case.diff).render()
    return rendered or None


def _finding_repr(finding) -> str:
    location = finding.file
    if finding.line is not None:
        location += f":{finding.line}"
    return f"[{finding.severity}/{finding.category}] {location} — {finding.issue}"
