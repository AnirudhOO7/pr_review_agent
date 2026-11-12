"""Append-only audit log for completed review runs."""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.findings import ReviewResult

DEFAULT_RUNS_DIR = Path("runs")


class RunAuditLog:
    """Stores each review run as one JSONL record."""

    def __init__(self, runs_dir: Path = DEFAULT_RUNS_DIR) -> None:
        self._runs_dir = runs_dir

    def record(
        self,
        *,
        pr_url: str,
        model: str,
        latency_s: float,
        diff: str,
        result: ReviewResult,
        retrieval_summary: dict[str, int] | None = None,
    ) -> None:
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pr_url": pr_url,
            "model": model,
            "latency_s": round(latency_s, 2),
            "retrieval": retrieval_summary,
            "diff": diff,
            "findings": [finding.model_dump() for finding in result.findings],
        }
        with (self._runs_dir / "runs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
