"""Run the reviewer over the dataset and score the results.

The reviewer is injected so the harness can be exercised with a fake in tests
(deterministic, no network) and with the real `LLMReviewer` for an actual eval.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Protocol

from app.models.findings import ReviewResult
from app.retrieval.retriever import CodeRetriever
from evals.dataset import Case
from evals.scoring import CaseResult, DEFAULT_TOLERANCE, filter_by_severity, score_case


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
    min_severity: str = "minor",
    workers: int = 1,
    on_case: Callable[[Case, CaseResult], None] | None = None,
) -> list[CaseRun]:
    """Review and score every case. Returns one CaseRun per case, in order.

    `min_severity` drops findings below that severity before scoring, which
    models a reviewer that only surfaces major/critical issues. `workers` runs
    cases concurrently (the LLM call is I/O bound); results keep case order.
    """

    def run_one(case: Case) -> CaseRun:
        context = _context_for(case) if retrieval else None
        review = reviewer.review(case.diff, context)
        findings = filter_by_severity(review.findings, min_severity)
        result = score_case(case, findings, tolerance)
        if on_case is not None:
            on_case(case, result)
        return CaseRun(result=result, findings_repr=[_finding_repr(f) for f in findings])

    if workers <= 1:
        return [run_one(case) for case in cases]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_one, cases))


def run_trials(
    cases: list[Case],
    reviewer: Reviewer,
    *,
    trials: int = 1,
    **kwargs,
) -> list[list[CaseRun]]:
    """Repeat the eval `trials` times. LLM output varies run to run, so a
    single run's precision/recall is one sample, not the number."""
    return [run_eval(cases, reviewer, **kwargs) for _ in range(trials)]


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
