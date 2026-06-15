import unittest

from app.models.findings import PRFinding, ReviewResult
from evals.dataset import Case, ExpectedBug, load_cases
from evals.harness import run_eval
from evals.report import build_summary, render_markdown
from evals.scoring import aggregate, finding_matches, score_case


def _finding(file: str, line: int | None, category: str = "correctness") -> PRFinding:
    return PRFinding(
        file=file, line=line, severity="major", category=category, issue="x"
    )


def _buggy(case_id: str, file: str, lines: list[int]) -> Case:
    return Case(
        id=case_id,
        label="buggy",
        diff="diff",
        expected=ExpectedBug(file=file, lines=lines, bug_type="off-by-one"),
    )


def _clean(case_id: str) -> Case:
    return Case(id=case_id, label="clean", diff="diff")


class FindingMatchTests(unittest.TestCase):
    def test_matches_within_tolerance_and_normalizes_path(self) -> None:
        expected = ExpectedBug(file="app/foo.py", lines=[10], bug_type="x")
        self.assertTrue(finding_matches(_finding("b/app/foo.py", 12), expected, tolerance=3))
        self.assertFalse(finding_matches(_finding("app/foo.py", 20), expected, tolerance=3))

    def test_wrong_file_never_matches(self) -> None:
        expected = ExpectedBug(file="app/foo.py", lines=[10], bug_type="x")
        self.assertFalse(finding_matches(_finding("app/bar.py", 10), expected))

    def test_none_line_never_matches(self) -> None:
        expected = ExpectedBug(file="app/foo.py", lines=[10], bug_type="x")
        self.assertFalse(finding_matches(_finding("app/foo.py", None), expected))


class ScoreCaseTests(unittest.TestCase):
    def test_buggy_case_outcomes(self) -> None:
        case = _buggy("c", "app/foo.py", [10])
        self.assertEqual(score_case(case, [_finding("app/foo.py", 11)]).outcome, "TP")
        self.assertEqual(score_case(case, [_finding("app/foo.py", 99)]).outcome, "FN")
        self.assertEqual(score_case(case, []).outcome, "FN")

    def test_clean_case_outcomes(self) -> None:
        case = _clean("c")
        self.assertEqual(score_case(case, []).outcome, "TN")
        self.assertEqual(score_case(case, [_finding("a.py", 1)]).outcome, "FP")


class AggregateTests(unittest.TestCase):
    def test_precision_recall_f1(self) -> None:
        results = [
            score_case(_buggy("b1", "f.py", [1]), [_finding("f.py", 1)]),  # TP
            score_case(_buggy("b2", "f.py", [1]), []),                     # FN
            score_case(_clean("c1"), [_finding("z.py", 1)]),               # FP
            score_case(_clean("c2"), []),                                  # TN
        ]
        summary = aggregate(results)
        self.assertEqual((summary.tp, summary.fn, summary.fp, summary.tn), (1, 1, 1, 1))
        self.assertAlmostEqual(summary.precision, 0.5)
        self.assertAlmostEqual(summary.recall, 0.5)
        self.assertAlmostEqual(summary.f1, 0.5)

    def test_recall_by_bug_type(self) -> None:
        results = [
            score_case(_buggy("b1", "f.py", [1]), [_finding("f.py", 1)]),  # caught
            score_case(_buggy("b2", "f.py", [1]), []),                     # missed
        ]
        # both share bug_type off-by-one
        self.assertEqual(aggregate(results).recall_by_bug_type(), {"off-by-one": (1, 2)})


class FakeReviewer:
    """Flags every diff at app/foo.py:1 — used to drive the harness offline."""

    def review(self, diff: str, context: str | None = None) -> ReviewResult:
        return ReviewResult(findings=[_finding("app/foo.py", 1)])


class HarnessTests(unittest.TestCase):
    def test_run_eval_scores_each_case(self) -> None:
        cases = [
            _buggy("b1", "app/foo.py", [1]),  # FakeReviewer hits it -> TP
            _clean("c1"),                     # FakeReviewer fires -> FP
        ]
        runs = run_eval(cases, FakeReviewer())
        outcomes = {r.result.case_id: r.result.outcome for r in runs}
        self.assertEqual(outcomes, {"b1": "TP", "c1": "FP"})
        markdown = render_markdown(runs, model="fake", retrieval=False, tolerance=3)
        self.assertIn("Precision", markdown)
        self.assertIn("b1", markdown)


class SeedDatasetTests(unittest.TestCase):
    def test_seed_dataset_loads_and_is_well_formed(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 12)
        self.assertTrue(any(c.label == "buggy" for c in cases))
        self.assertTrue(any(c.label == "clean" for c in cases))
        # Every buggy expected line points at a real added line in its diff.
        for case in cases:
            if case.label == "buggy":
                added = case.diff.count("\n+") - case.diff.count("\n+++")
                for line in case.expected.lines:
                    self.assertLessEqual(line, added, f"{case.id}: line {line} > {added} added")


if __name__ == "__main__":
    unittest.main()
