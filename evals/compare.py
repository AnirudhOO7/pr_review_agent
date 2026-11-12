"""A/B the reviewer across configurations on the same dataset.

    python -m evals.compare --trials 3

Runs every configuration below for N trials and writes evals/comparison.md and
evals/comparison.json: overall precision / recall / F1 / false-alarm rate, plus
the same metrics on the context-dependent subset (cases tied to a fixture repo),
which is where structural retrieval can make a difference.

Configurations:
  baseline   prompt v1, no retrieval, all severities   (the original agent)
  prompt-v2  prompt v2, no retrieval, all severities   (isolates the prompt)
  v2+retr    prompt v2, retrieval on                   (isolates retrieval)
  v2+retr+M  prompt v2, retrieval on, major+ only      (production setting)
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from evals.dataset import load_cases
from evals.report import RATE_METRICS
from evals.run import REPORT_DIR, add_common_args, evaluate, headline

CONFIGS = [
    ("baseline", {"prompt": "v1", "retrieval": False, "min_severity": "minor"}),
    ("prompt-v2", {"prompt": "v2", "retrieval": False, "min_severity": "minor"}),
    ("v2+retr", {"prompt": "v2", "retrieval": True, "min_severity": "minor"}),
    ("v2+retr+M", {"prompt": "v2", "retrieval": True, "min_severity": "major"}),
]
LABELS = {"precision": "Precision", "recall": "Recall", "f1": "F1", "false_alarm_rate": "False alarms"}


def render(comparison: dict) -> str:
    lines = [
        "# PR Review Agent — Configuration Comparison",
        "",
        f"- Generated: {comparison['generated_at']}",
        f"- Model: `{comparison['model']}` · trials per config: {comparison['trials']}",
        f"- Cases: {comparison['cases']} ({comparison['buggy']} buggy, {comparison['clean']} clean); "
        f"context-dependent subset: {comparison['context_cases']}",
        "",
        "Values are mean ± sample std across trials. False alarms = share of clean "
        "cases where the agent raised any finding.",
        "",
    ]
    for scope, title in (("overall", "All cases"), ("context", "Context-dependent subset")):
        lines += [
            f"## {title}",
            "",
            "| Config | Prompt | Retrieval | Severity floor | "
            + " | ".join(LABELS[k] for k in RATE_METRICS) + " |",
            "| --- | --- | --- | --- | " + " | ".join("---" for _ in RATE_METRICS) + " |",
        ]
        for row in comparison["configs"]:
            data = row[scope]
            if data is None:
                continue
            m, sd = data["metrics"], data["metrics_std"]
            lines.append(
                f"| {row['name']} | {row['prompt']} | {'on' if row['retrieval'] else 'off'} | "
                f"{row['min_severity']} | "
                + " | ".join(f"{m[k]:.2f} ± {sd[k]:.2f}" for k in RATE_METRICS) + " |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B eval across configurations.")
    add_common_args(parser)
    parser.add_argument("--only", nargs="*", help="Run only these config names.")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    rows = []
    for name, cfg in CONFIGS:
        if args.only and name not in args.only:
            continue
        print(f"\n== {name}: {cfg}", flush=True)
        report = evaluate(
            cases,
            model=args.model,
            tolerance=args.tolerance,
            trials=args.trials,
            workers=args.workers,
            verbose=False,
            **cfg,
        )
        print(headline(report))
        # Keep each config's full report alongside the comparison.
        (REPORT_DIR / "runs").mkdir(exist_ok=True)
        (REPORT_DIR / "runs" / f"{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        context = report["subsets"].get("context-dependent")
        rows.append(
            {
                "name": name,
                **cfg,
                "overall": {"metrics": report["metrics"], "metrics_std": report["metrics_std"]},
                "context": context,
            }
        )

    comparison = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": args.model,
        "trials": args.trials,
        "cases": len(cases),
        "buggy": sum(1 for c in cases if c.label == "buggy"),
        "clean": sum(1 for c in cases if c.label == "clean"),
        "context_cases": sum(1 for c in cases if c.repo_path),
        "configs": rows,
    }
    (REPORT_DIR / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    (REPORT_DIR / "comparison.md").write_text(render(comparison), encoding="utf-8")
    print("\nWrote evals/comparison.md and evals/comparison.json")


if __name__ == "__main__":
    main()
