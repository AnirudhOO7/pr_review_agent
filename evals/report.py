"""Render an eval run as a Markdown report and a machine-readable JSON blob."""

from datetime import datetime, timezone

from evals.harness import CaseRun
from evals.scoring import EvalSummary, aggregate

_OUTCOME_MARK = {"TP": "✓ caught", "FN": "✗ missed", "FP": "✗ false alarm", "TN": "✓ silent"}


def build_summary(runs: list[CaseRun]) -> EvalSummary:
    return aggregate([run.result for run in runs])


def render_markdown(
    runs: list[CaseRun],
    *,
    model: str,
    retrieval: bool,
    tolerance: int,
) -> str:
    summary = build_summary(runs)
    buggy = sum(1 for r in summary.results if r.label == "buggy")
    clean = sum(1 for r in summary.results if r.label == "clean")

    lines: list[str] = [
        "# PR Review Agent — Eval Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Model: `{model}`",
        f"- Retrieval: {'on' if retrieval else 'off'}",
        f"- Match tolerance: ±{tolerance} lines",
        f"- Cases: {len(summary.results)} ({buggy} buggy, {clean} clean)",
        "",
        "## Detection metrics",
        "",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Precision | {summary.precision:.2f} |",
        f"| Recall | {summary.recall:.2f} |",
        f"| F1 | {summary.f1:.2f} |",
        f"| TP / FN / FP / TN | {summary.tp} / {summary.fn} / {summary.fp} / {summary.tn} |",
        "",
        "## Recall by bug type",
        "",
        "| Bug type | Caught / Total |",
        "| --- | --- |",
    ]
    for bug_type, (caught, total) in summary.recall_by_bug_type().items():
        lines.append(f"| {bug_type} | {caught}/{total} |")

    lines += [
        "",
        "## Noise",
        "",
        f"- Spurious findings on clean cases: {summary.spurious_findings_on_clean()}",
        "",
        "## Per-case results",
        "",
        "| Case | Label | Bug type | Outcome | Match line | # findings |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for run in runs:
        r = run.result
        lines.append(
            f"| {r.case_id} | {r.label} | {r.bug_type or '—'} | "
            f"{_OUTCOME_MARK[r.outcome]} | {r.matched_line if r.matched_line is not None else '—'} "
            f"| {r.num_findings} |"
        )

    lines.append("")
    return "\n".join(lines)


def to_dict(
    runs: list[CaseRun],
    *,
    model: str,
    retrieval: bool,
    tolerance: int,
) -> dict:
    summary = build_summary(runs)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "retrieval": retrieval,
        "tolerance": tolerance,
        "metrics": {
            "precision": round(summary.precision, 4),
            "recall": round(summary.recall, 4),
            "f1": round(summary.f1, 4),
            "tp": summary.tp,
            "fn": summary.fn,
            "fp": summary.fp,
            "tn": summary.tn,
        },
        "recall_by_bug_type": {
            bt: {"caught": caught, "total": total}
            for bt, (caught, total) in summary.recall_by_bug_type().items()
        },
        "cases": [
            {
                "case_id": run.result.case_id,
                "label": run.result.label,
                "bug_type": run.result.bug_type,
                "outcome": run.result.outcome,
                "matched_line": run.result.matched_line,
                "num_findings": run.result.num_findings,
                "findings": run.findings_repr,
            }
            for run in runs
        ],
    }
