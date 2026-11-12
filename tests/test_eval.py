import unittest
from pathlib import Path

from app.models.findings import PRFinding, ReviewResult
from evals.dataset import Case, ExpectedBug, load_cases
from evals.harness import run_eval
from evals.build_cases import build_diff
from evals.harness import run_trials
from evals.report import build_summary, render_markdown, to_dict
from evals.scoring import aggregate, filter_by_severity, finding_matches, score_case

CONFIG = {"model": "fake", "prompt": "v2", "retrieval": False, "tolerance": 3, "min_severity": "minor"}


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
        markdown = render_markdown(to_dict([runs], config=CONFIG))
        self.assertIn("Precision", markdown)
        self.assertIn("b1", markdown)

    def test_min_severity_drops_minor_findings_before_scoring(self) -> None:
        class MinorReviewer:
            def review(self, diff, context=None):
                return ReviewResult(findings=[PRFinding(
                    file="a.py", line=1, severity="minor", category="style", issue="nit")])

        runs = run_eval([_clean("c1")], MinorReviewer(), min_severity="major")
        self.assertEqual(runs[0].result.outcome, "TN")
        self.assertEqual(runs[0].findings_repr, [])

    def test_workers_preserve_case_order(self) -> None:
        cases = [_clean(f"c{i}") for i in range(10)]
        runs = run_eval(cases, FakeReviewer(), workers=4)
        self.assertEqual([r.result.case_id for r in runs], [c.id for c in cases])


class FlakyReviewer:
    """Catches the bug on odd calls only, to exercise multi-trial stats."""

    def __init__(self) -> None:
        self.calls = 0

    def review(self, diff, context=None):
        self.calls += 1
        line = 1 if self.calls % 2 else 50
        return ReviewResult(findings=[_finding("app/foo.py", line)])


class TrialReportTests(unittest.TestCase):
    def test_mean_std_and_majority_outcome(self) -> None:
        cases = [_buggy("b1", "app/foo.py", [1])]
        trials = run_trials(cases, FlakyReviewer(), trials=3)  # TP, FN, TP
        report = to_dict(trials, config=CONFIG)
        self.assertEqual(report["trials"], 3)
        self.assertAlmostEqual(report["metrics"]["recall"], 2 / 3, places=3)
        self.assertGreater(report["metrics_std"]["recall"], 0)
        self.assertEqual(report["cases"][0]["outcomes"], ["TP", "FN", "TP"])
        self.assertEqual(report["cases"][0]["outcome"], "TP")
        self.assertEqual(report["recall_by_bug_type"]["off-by-one"], {"caught": 2, "total": 3})

    def test_subset_metrics_and_false_alarm_rate(self) -> None:
        cases = [_buggy("b1", "app/foo.py", [1]), _clean("c1"), _clean("c2")]
        report = to_dict([run_eval(cases, FakeReviewer())], config=CONFIG,
                         subsets={"ctx": {"c1"}})
        self.assertEqual(report["metrics"]["false_alarm_rate"], 1.0)
        self.assertEqual(report["subsets"]["ctx"]["cases"], 1)
        self.assertIn("± 0.00", render_markdown(report))


class ScoringHelpersTests(unittest.TestCase):
    def test_filter_by_severity(self) -> None:
        findings = [
            PRFinding(file="a", line=1, severity=s, category="correctness", issue="x")
            for s in ("minor", "major", "critical")
        ]
        self.assertEqual(len(filter_by_severity(findings, "minor")), 3)
        self.assertEqual([f.severity for f in filter_by_severity(findings, "major")],
                         ["major", "critical"])


class BuildCasesTests(unittest.TestCase):
    def test_bug_marker_is_stripped_and_located(self) -> None:
        before = "a = 1\nb = 2\nc = 3\n"
        after = "a = 1\nb = 20  #@bug\nc = 3\nd = 4\n"
        diff, lines = build_diff("x.py", before, after)
        self.assertEqual(lines, [2])
        self.assertNotIn("#@bug", diff)
        self.assertIn("+b = 20\n", diff)
        self.assertTrue(diff.startswith("--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,4 @@"))


class SeedDatasetTests(unittest.TestCase):
    def test_seed_dataset_loads_and_is_well_formed(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 12)
        self.assertTrue(any(c.label == "buggy" for c in cases))
        self.assertTrue(any(c.label == "clean" for c in cases))
        # Every buggy expected line points at an added line of its diff.
        for case in cases:
            if case.label == "buggy":
                added = _added_lines(case.diff).get(case.expected.file, set())
                for line in case.expected.lines:
                    self.assertIn(line, added, f"{case.id}: line {line} is not an added line")

    def test_context_cases_point_at_existing_fixture_repo(self) -> None:
        context = [c for c in load_cases() if c.repo_path]
        self.assertGreaterEqual(len(context), 6)
        for case in context:
            self.assertTrue(Path(case.repo_path).is_dir(), case.id)


def _added_lines(diff: str) -> dict[str, set[int]]:
    """New-file line numbers of `+` lines, per file."""
    out: dict[str, set[int]] = {}
    current, line = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            current = raw[4:].removeprefix("b/")
            out.setdefault(current, set())
        elif raw.startswith("@@"):
            line = int(raw.split("+")[1].split(",")[0].split(" ")[0])
        elif raw.startswith("---"):
            continue
        elif raw.startswith("+"):
            out[current].add(line)
            line += 1
        elif not raw.startswith("-"):
            line += 1
    return out


if __name__ == "__main__":
    unittest.main()
