"""Regenerate the eval report on demand.

    python -m evals.run                # full eval against the dataset
    python -m evals.run --retrieval    # same, with structural retrieval enabled
    python -m evals.run --cases path/  # a different case directory

Requires ANTHROPIC_API_KEY (it runs the real reviewer). Writes the report to
evals/report.md and evals/report.json, and prints the headline numbers.
"""

import argparse
import json
from pathlib import Path

from app.config.config import settings
from app.llm.reviewer import LLMReviewer
from evals.dataset import CASES_DIR, load_cases
from evals.harness import run_eval
from evals.report import build_summary, render_markdown, to_dict
from evals.scoring import DEFAULT_TOLERANCE

REPORT_DIR = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PR-review eval harness.")
    parser.add_argument("--cases", default=str(CASES_DIR), help="Directory of case JSON files.")
    parser.add_argument("--retrieval", action="store_true", help="Enable structural retrieval.")
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE, help="Line-match tolerance.")
    parser.add_argument("--model", default=settings.model_name, help="Model override.")
    parser.add_argument("--out", default=str(REPORT_DIR / "report.md"), help="Markdown report path.")
    parser.add_argument("--json", dest="json_out", default=str(REPORT_DIR / "report.json"), help="JSON report path.")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    print(f"Loaded {len(cases)} cases from {args.cases}")

    reviewer = LLMReviewer(model=args.model)

    def progress(case, result) -> None:
        print(f"  {result.outcome:<3} {case.id}")

    runs = run_eval(
        cases,
        reviewer,
        retrieval=args.retrieval,
        tolerance=args.tolerance,
        on_case=progress,
    )

    markdown = render_markdown(
        runs, model=args.model, retrieval=args.retrieval, tolerance=args.tolerance
    )
    Path(args.out).write_text(markdown, encoding="utf-8")
    Path(args.json_out).write_text(
        json.dumps(
            to_dict(runs, model=args.model, retrieval=args.retrieval, tolerance=args.tolerance),
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = build_summary(runs)
    print(
        f"\nPrecision {summary.precision:.2f} | Recall {summary.recall:.2f} | "
        f"F1 {summary.f1:.2f}  (TP={summary.tp} FN={summary.fn} FP={summary.fp} TN={summary.tn})"
    )
    print(f"Report written to {args.out} and {args.json_out}")


if __name__ == "__main__":
    main()
