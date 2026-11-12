"""Render an eval run as a Markdown report and a machine-readable JSON blob.

A report covers one configuration (model, prompt, retrieval, severity floor)
run for one or more trials. Headline metrics are the mean across trials, with
the sample standard deviation alongside, because a single LLM run is noisy.
"""

import statistics
from collections import Counter
from datetime import datetime, timezone

from evals.harness import CaseRun
from evals.scoring import EvalSummary, aggregate

_OUTCOME_MARK = {"TP": "✓ caught", "FN": "✗ missed", "FP": "✗ false alarm", "TN": "✓ silent"}
RATE_METRICS = ("precision", "recall", "f1", "false_alarm_rate")
COUNT_METRICS = ("tp", "fn", "fp", "tn")


def build_summary(runs: list[CaseRun]) -> EvalSummary:
    return aggregate([run.result for run in runs])


def metric_stats(summaries: list[EvalSummary]) -> tuple[dict, dict]:
    """(mean, std) of each metric across trial summaries."""
    mean: dict[str, float] = {}
    std: dict[str, float] = {}
    for name in RATE_METRICS + COUNT_METRICS:
        values = [float(getattr(s, name)) for s in summaries]
        mean[name] = round(statistics.fmean(values), 4)
        if name in RATE_METRICS:
            std[name] = round(statistics.stdev(values), 4) if len(values) > 1 else 0.0
    return mean, std


def to_dict(
    trials: list[list[CaseRun]],
    *,
    config: dict,
    subsets: dict[str, set[str]] | None = None,
) -> dict:
    """JSON report. `config` holds model/prompt/retrieval/tolerance/min_severity;
    `subsets` maps a name to the case ids it covers (e.g. context-dependent)."""
    summaries = [build_summary(runs) for runs in trials]
    mean, std = metric_stats(summaries)

    subset_out = {}
    for name, ids in (subsets or {}).items():
        sub = [s.subset(ids) for s in summaries]
        if not sub or not sub[0].results:
            continue
        sub_mean, sub_std = metric_stats(sub)
        subset_out[name] = {
            "cases": len(sub[0].results),
            "metrics": sub_mean,
            "metrics_std": sub_std,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **config,
        "trials": len(trials),
        "metrics": mean,
        "metrics_std": std,
        "subsets": subset_out,
        "recall_by_bug_type": _recall_by_bug_type(summaries),
        "cases": _case_rows(trials),
    }


def render_markdown(report: dict) -> str:
    """Markdown view of a `to_dict` report."""
    m, sd = report["metrics"], report["metrics_std"]
    buggy = sum(1 for c in report["cases"] if c["label"] == "buggy")
    clean = len(report["cases"]) - buggy

    def fmt(name: str) -> str:
        if report["trials"] > 1:
            return f"{m[name]:.2f} ± {sd[name]:.2f}"
        return f"{m[name]:.2f}"

    lines = [
        "# PR Review Agent — Eval Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Model: `{report['model']}` · prompt `{report['prompt']}`",
        f"- Retrieval: {'on' if report['retrieval'] else 'off'}",
        f"- Severity floor: {report['min_severity']} · match tolerance ±{report['tolerance']} lines",
        f"- Cases: {len(report['cases'])} ({buggy} buggy, {clean} clean) · trials: {report['trials']}",
        "",
        "## Detection metrics" + (" (mean ± std across trials)" if report["trials"] > 1 else ""),
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Precision | {fmt('precision')} |",
        f"| Recall | {fmt('recall')} |",
        f"| F1 | {fmt('f1')} |",
        f"| False-alarm rate (clean cases flagged) | {fmt('false_alarm_rate')} |",
        "| TP / FN / FP / TN (mean) | "
        + " / ".join(f"{round(m[k], 1):g}" for k in ("tp", "fn", "fp", "tn")) + " |",
        "",
    ]

    for name, sub in report.get("subsets", {}).items():
        sm, ss = sub["metrics"], sub["metrics_std"]
        lines += [
            f"## Subset: {name} ({sub['cases']} cases)",
            "",
            "| Precision | Recall | F1 | False-alarm rate |",
            "| --- | --- | --- | --- |",
            "| " + " | ".join(f"{sm[k]:.2f} ± {ss[k]:.2f}" for k in RATE_METRICS) + " |",
            "",
        ]

    lines += ["## Recall by bug type", "", "| Bug type | Caught / Total |", "| --- | --- |"]
    for bug_type, v in report["recall_by_bug_type"].items():
        lines.append(f"| {bug_type} | {v['caught']}/{v['total']} |")

    lines += [
        "",
        "## Per-case results",
        "",
        "| Case | Label | Bug type | Outcome | Across trials | Match line | Avg findings |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in report["cases"]:
        lines.append(
            f"| {c['case_id']} | {c['label']} | {c['bug_type'] or '—'} | "
            f"{_OUTCOME_MARK[c['outcome']]} | {' '.join(c['outcomes'])} | "
            f"{c['matched_line'] if c['matched_line'] is not None else '—'} | {c['num_findings']:g} |"
        )
    lines.append("")
    return "\n".join(lines)


def _recall_by_bug_type(summaries: list[EvalSummary]) -> dict:
    totals: Counter = Counter()
    caught: Counter = Counter()
    for summary in summaries:
        for bug_type, (c, t) in summary.recall_by_bug_type().items():
            caught[bug_type] += c
            totals[bug_type] += t
    return {bt: {"caught": caught[bt], "total": totals[bt]} for bt in sorted(totals)}


def _case_rows(trials: list[list[CaseRun]]) -> list[dict]:
    rows = []
    for i, first in enumerate(trials[0]):
        per_case = [runs[i] for runs in trials]
        outcomes = [r.result.outcome for r in per_case]
        good = "TP" if first.result.label == "buggy" else "TN"
        bad = "FN" if good == "TP" else "FP"
        majority = good if outcomes.count(good) > len(outcomes) / 2 else bad
        matched = next((r.result.matched_line for r in per_case if r.result.matched_line), None)
        # Show findings from a trial that agrees with the majority outcome.
        shown = next(r for r in per_case if r.result.outcome == majority) if majority in outcomes else first
        rows.append(
            {
                "case_id": first.result.case_id,
                "label": first.result.label,
                "bug_type": first.result.bug_type,
                "outcome": majority,
                "outcomes": outcomes,
                "matched_line": matched,
                "num_findings": round(statistics.fmean(r.result.num_findings for r in per_case), 2),
                "findings": shown.findings_repr,
            }
        )
    return rows
