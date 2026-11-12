"""Regenerate the eval report on demand.

    python -m evals.run                      # full eval, default prompt (v2)
    python -m evals.run --retrieval          # with structural retrieval
    python -m evals.run --trials 3           # mean ± std across 3 runs
    python -m evals.run --prompt v1          # the original prompt
    python -m evals.run --min-severity major # score only major/critical findings

Requires ANTHROPIC_API_KEY (it runs the real reviewer). Writes the report to
evals/report.md and evals/report.json, and prints the headline numbers.
"""

import argparse
import json
from pathlib import Path

from app.config.config import settings
from app.llm.reviewer import PROMPTS, LLMReviewer
from evals.dataset import CASES_DIR, Case, load_cases
from evals.harness import run_trials
from evals.report import render_markdown, to_dict
from evals.scoring import DEFAULT_TOLERANCE, SEVERITY_RANK

REPORT_DIR = Path(__file__).parent


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cases", default=str(CASES_DIR), help="Directory of case JSON files.")
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE, help="Line-match tolerance.")
    parser.add_argument("--model", default=settings.model_name, help="Model override.")
    parser.add_argument("--trials", type=int, default=1, help="Repeat the eval N times.")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent LLM calls.")


def context_subsets(cases: list[Case]) -> dict[str, set[str]]:
    """Cases tied to a fixture repo are the ones retrieval can change."""
    ids = {c.id for c in cases if c.repo_path}
    return {"context-dependent": ids} if ids else {}


def evaluate(
    cases: list[Case],
    *,
    model: str,
    prompt: str,
    retrieval: bool,
    min_severity: str,
    tolerance: int,
    trials: int,
    workers: int,
    verbose: bool = True,
) -> dict:
    """Run one configuration and return its JSON report."""
    reviewer = LLMReviewer(model=model, prompt=prompt)

    def progress(case, result) -> None:
        if verbose:
            print(f"  {result.outcome:<3} {case.id}", flush=True)

    trial_runs = run_trials(
        cases,
        reviewer,
        trials=trials,
        retrieval=retrieval,
        tolerance=tolerance,
        min_severity=min_severity,
        workers=workers,
        on_case=progress,
    )
    config = {
        "model": model,
        "prompt": prompt,
        "retrieval": retrieval,
        "tolerance": tolerance,
        "min_severity": min_severity,
    }
    return to_dict(trial_runs, config=config, subsets=context_subsets(cases))


def headline(report: dict) -> str:
    m, sd = report["metrics"], report["metrics_std"]
    return (
        f"Precision {m['precision']:.2f}±{sd['precision']:.2f} | "
        f"Recall {m['recall']:.2f}±{sd['recall']:.2f} | "
        f"F1 {m['f1']:.2f}±{sd['f1']:.2f} | "
        f"False alarms {m['false_alarm_rate']:.2f}±{sd['false_alarm_rate']:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PR-review eval harness.")
    add_common_args(parser)
    parser.add_argument("--retrieval", action="store_true", help="Enable structural retrieval.")
    parser.add_argument("--prompt", default=settings.review_prompt, choices=sorted(PROMPTS))
    parser.add_argument("--min-severity", default="minor", choices=list(SEVERITY_RANK))
    parser.add_argument("--out", default=str(REPORT_DIR / "report.md"), help="Markdown report path.")
    parser.add_argument("--json", dest="json_out", default=str(REPORT_DIR / "report.json"), help="JSON report path.")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    print(f"Loaded {len(cases)} cases from {args.cases}")

    report = evaluate(
        cases,
        model=args.model,
        prompt=args.prompt,
        retrieval=args.retrieval,
        min_severity=args.min_severity,
        tolerance=args.tolerance,
        trials=args.trials,
        workers=args.workers,
    )
    Path(args.out).write_text(render_markdown(report), encoding="utf-8")
    Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + headline(report))
    print(f"Report written to {args.out} and {args.json_out}")


if __name__ == "__main__":
    main()
