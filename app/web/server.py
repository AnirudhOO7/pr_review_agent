"""Web UI and JSON API for the PR Review Agent.

    uvicorn app.web.server:app --reload

Serves a single-page app from `static/` plus a small API that wraps the same
`ReviewService` the CLI uses. LLM and GitHub calls are blocking, so the
endpoints are plain `def` functions and run on FastAPI's threadpool.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.audit_log import RunAuditLog
from app.config.config import settings
from app.github.client import GitHubClient, GitHubError, parse_pr_url
from app.github.review_builder import InlineComment, PreparedReview, ReviewBuilder
from app.llm.reviewer import LLMReviewer, ReviewError
from app.models.findings import ReviewResult
from app.retrieval.retriever import CodeRetriever
from app.review_service import ReviewRun, ReviewService
from evals.dataset import CASES_DIR, load_cases

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
RUNS_DIR = PROJECT_ROOT / "runs"
EVAL_REPORT = PROJECT_ROOT / "evals" / "report.json"
EVAL_COMPARISON = PROJECT_ROOT / "evals" / "comparison.json"
MAX_DIFF_CHARS = 200_000

app = FastAPI(title="PR Review Agent", docs_url="/api/docs", redoc_url=None)


class ReviewRequest(BaseModel):
    pr_url: str | None = None
    diff: str | None = Field(default=None, max_length=MAX_DIFF_CHARS)
    repo_path: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> "ReviewRequest":
        if bool(self.pr_url and self.pr_url.strip()) == bool(self.diff and self.diff.strip()):
            raise ValueError("Provide exactly one of pr_url or diff.")
        return self


class PostRequest(BaseModel):
    pr_url: str
    body: str
    inline_comments: list[InlineComment]


@app.get("/api/status")
def status() -> dict:
    return {
        "model": settings.model_name,
        "prompt": settings.review_prompt,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "github_configured": bool(settings.github_token),
    }


@app.get("/api/samples")
def samples() -> list[dict]:
    """Labeled eval cases, offered in the UI as one-click demo diffs."""
    return [
        {
            "id": case.id,
            "label": case.label,
            "diff": case.diff,
            "repo_path": case.repo_path,
            "expected": (
                {
                    "file": case.expected.file,
                    "lines": case.expected.lines,
                    "bug_type": case.expected.bug_type,
                }
                if case.expected
                else None
            ),
        }
        for case in load_cases(CASES_DIR)
    ]


@app.post("/api/review")
def review(req: ReviewRequest) -> dict:
    retriever = None
    if req.repo_path:
        repo = Path(req.repo_path).expanduser()
        if not repo.is_dir():
            raise HTTPException(400, f"Repository path not found: {repo}")
        retriever = CodeRetriever(repo)

    try:
        reviewer = LLMReviewer()
    except ReviewError as exc:
        raise HTTPException(503, str(exc)) from exc

    service = ReviewService(
        reviewer=reviewer,
        retriever=retriever,
        audit_log=RunAuditLog(RUNS_DIR),
    )
    try:
        with service:
            if req.pr_url:
                pr_url = req.pr_url.strip()
                diff = service.github.fetch_diff(pr_url)
                if len(diff) > MAX_DIFF_CHARS:
                    raise HTTPException(
                        413, f"Diff is {len(diff):,} chars; the limit is {MAX_DIFF_CHARS:,}."
                    )
                run = service.review_diff(diff, source=pr_url)
            else:
                run = service.review_diff(req.diff, source="pasted diff")
    except GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ReviewError as exc:
        raise HTTPException(502, str(exc)) from exc

    return _run_to_dict(run)


@app.post("/api/post")
def post_review(req: PostRequest) -> dict:
    try:
        owner, repo, number = parse_pr_url(req.pr_url)
        with GitHubClient() as github:
            github.create_review(owner, repo, number, req.body, req.inline_comments)
    except GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"posted": True, "url": f"https://github.com/{owner}/{repo}/pull/{number}"}


@app.get("/api/eval")
def eval_report() -> dict:
    if not EVAL_REPORT.is_file():
        raise HTTPException(404, "No eval report yet. Run `python -m evals.run`.")
    return json.loads(EVAL_REPORT.read_text(encoding="utf-8"))


@app.get("/api/eval/comparison")
def eval_comparison() -> dict:
    if not EVAL_COMPARISON.is_file():
        raise HTTPException(404, "No comparison yet. Run `python -m evals.compare`.")
    return json.loads(EVAL_COMPARISON.read_text(encoding="utf-8"))


@app.get("/api/runs")
def runs(limit: int = 50) -> list[dict]:
    """Recent review runs from the audit log, newest first."""
    records = _read_runs()
    summaries = []
    for index, record in reversed(list(enumerate(records))):
        findings = record.get("findings", [])
        summaries.append(
            {
                "id": index,
                "timestamp": record.get("timestamp"),
                "source": record.get("pr_url"),
                "model": record.get("model"),
                "latency_s": record.get("latency_s"),
                "num_findings": len(findings),
                "severities": _count(findings, "severity"),
            }
        )
        if len(summaries) >= limit:
            break
    return summaries


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int) -> dict:
    records = _read_runs()
    if not 0 <= run_id < len(records):
        raise HTTPException(404, "Run not found.")
    record = records[run_id]
    diff = record.get("diff", "")
    result = ReviewResult.model_validate({"findings": record.get("findings", [])})
    return {
        "id": run_id,
        "source": record.get("pr_url"),
        "timestamp": record.get("timestamp"),
        "model": record.get("model"),
        "latency_s": record.get("latency_s"),
        "retrieval": record.get("retrieval"),
        "diff": diff,
        "findings": [f.model_dump() for f in result.findings],
        "github_review": _github_review_dict(ReviewBuilder().build(diff, result)),
    }


def _run_to_dict(run: ReviewRun) -> dict:
    return {
        "source": run.source,
        "model": run.model,
        "latency_s": run.latency_s,
        "retrieval": run.retrieval_summary,
        "diff": run.diff,
        "findings": [f.model_dump() for f in run.result.findings],
        "github_review": _github_review_dict(run.prepared),
    }


def _github_review_dict(prepared: PreparedReview) -> dict:
    return {
        "body": prepared.body,
        "inline_comments": prepared.inline_comments,
        "summary_only": [f.model_dump() for f in prepared.general_findings],
    }


def _read_runs() -> list[dict]:
    path = RUNS_DIR / "runs.jsonl"
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _count(findings: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.get(key, "?")] = counts.get(f.get(key, "?"), 0) + 1
    return counts


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
