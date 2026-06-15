"""The labeled evaluation dataset.

Each case is a self-contained "PR": a unified diff plus ground truth. Buggy
cases carry the planted bug's location and type; clean cases carry nothing. We
plant the bugs ourselves precisely so the ground truth is exact — something a
scrape of real-world PRs can never give you.

Cases live as JSON under `evals/cases/`. A file may hold a single case object
or a list of them, so the set grows by dropping in more files.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CASES_DIR = Path(__file__).parent / "cases"
Label = Literal["buggy", "clean"]


@dataclass(frozen=True)
class ExpectedBug:
    """Ground truth for a planted bug."""

    file: str
    lines: list[int]
    bug_type: str
    category: str | None = None


@dataclass(frozen=True)
class Case:
    """One labeled review case."""

    id: str
    label: Label
    diff: str
    expected: ExpectedBug | None = None
    repo_path: str | None = None

    def __post_init__(self) -> None:
        if self.label == "buggy" and self.expected is None:
            raise ValueError(f"Buggy case {self.id!r} must declare an expected bug.")
        if self.label == "clean" and self.expected is not None:
            raise ValueError(f"Clean case {self.id!r} must not declare an expected bug.")


def load_cases(cases_dir: str | Path = CASES_DIR) -> list[Case]:
    """Load every case from the JSON files in `cases_dir`, sorted by id."""
    directory = Path(cases_dir)
    if not directory.is_dir():
        raise NotADirectoryError(f"Cases directory not found: {directory}")

    cases: list[Case] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            case = _case_from_dict(record)
            if case.id in seen:
                raise ValueError(f"Duplicate case id: {case.id!r}")
            seen.add(case.id)
            cases.append(case)

    return sorted(cases, key=lambda c: c.id)


def _case_from_dict(record: dict) -> Case:
    expected_raw = record.get("expected")
    expected = None
    if expected_raw is not None:
        expected = ExpectedBug(
            file=expected_raw["file"],
            lines=list(expected_raw["lines"]),
            bug_type=expected_raw["bug_type"],
            category=expected_raw.get("category"),
        )
    return Case(
        id=record["id"],
        label=record["label"],
        diff=record["diff"],
        expected=expected,
        repo_path=record.get("repo_path"),
    )
