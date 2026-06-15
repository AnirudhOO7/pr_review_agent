"""Score agent findings against the labeled dataset.

Matching is by location: a finding counts as catching a planted bug if it points
at the right file and a line within `tolerance` of the planted line. We don't try
to semantically match the finding's prose — line proximity is the standard,
defensible signal for this kind of planted-bug eval.

Outcomes, per case:
  - buggy case, a finding lands on the bug  -> TP
  - buggy case, nothing lands on the bug    -> FN
  - clean case, the agent raises any finding -> FP
  - clean case, the agent stays silent       -> TN
"""

from dataclasses import dataclass
from typing import Literal

from app.models.findings import PRFinding
from evals.dataset import Case, ExpectedBug

Outcome = Literal["TP", "FN", "FP", "TN"]
DEFAULT_TOLERANCE = 3


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    label: str
    bug_type: str | None
    outcome: Outcome
    matched_line: int | None
    num_findings: int


def _normalize_path(path: str) -> str:
    path = path.strip().lstrip("./")
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def finding_matches(
    finding: PRFinding, expected: ExpectedBug, tolerance: int = DEFAULT_TOLERANCE
) -> bool:
    """True if the finding localizes to the planted bug."""
    if _normalize_path(finding.file) != _normalize_path(expected.file):
        return False
    if finding.line is None:
        return False
    return any(abs(finding.line - line) <= tolerance for line in expected.lines)


def score_case(
    case: Case,
    findings: list[PRFinding],
    tolerance: int = DEFAULT_TOLERANCE,
) -> CaseResult:
    if case.label == "buggy":
        assert case.expected is not None  # guaranteed by Case validation
        matched = next(
            (f for f in findings if finding_matches(f, case.expected, tolerance)),
            None,
        )
        return CaseResult(
            case_id=case.id,
            label=case.label,
            bug_type=case.expected.bug_type,
            outcome="TP" if matched else "FN",
            matched_line=matched.line if matched else None,
            num_findings=len(findings),
        )

    return CaseResult(
        case_id=case.id,
        label=case.label,
        bug_type=None,
        outcome="FP" if findings else "TN",
        matched_line=None,
        num_findings=len(findings),
    )


@dataclass(frozen=True)
class EvalSummary:
    """Aggregate metrics over a scored run."""

    results: list[CaseResult]

    def _count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)

    @property
    def tp(self) -> int:
        return self._count("TP")

    @property
    def fn(self) -> int:
        return self._count("FN")

    @property
    def fp(self) -> int:
        return self._count("FP")

    @property
    def tn(self) -> int:
        return self._count("TN")

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def recall_by_bug_type(self) -> dict[str, tuple[int, int]]:
        """bug_type -> (caught, total) across buggy cases."""
        totals: dict[str, int] = {}
        caught: dict[str, int] = {}
        for r in self.results:
            if r.bug_type is None:
                continue
            totals[r.bug_type] = totals.get(r.bug_type, 0) + 1
            if r.outcome == "TP":
                caught[r.bug_type] = caught.get(r.bug_type, 0) + 1
        return {bt: (caught.get(bt, 0), totals[bt]) for bt in sorted(totals)}

    def spurious_findings_on_clean(self) -> int:
        """Total findings raised across clean cases (noise signal)."""
        return sum(r.num_findings for r in self.results if r.label == "clean")


def aggregate(results: list[CaseResult]) -> EvalSummary:
    return EvalSummary(results=results)
