# PR Review Agent

> An LLM-powered code reviewer for GitHub pull requests, built with structured outputs, structural code retrieval, and a measurable evaluation harness.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-D4A27F)
![Pydantic](https://img.shields.io/badge/Pydantic-validated_outputs-E92063?logo=pydantic&logoColor=white)

Give it a GitHub PR URL it fetches the diff, optionally retrieves the surrounding code context, asks an Anthropic model for structured review findings, prints them, posts them as inline PR comments, and stores an audit record of every run.

---

## Why this project

Most AI code review demos generate prose and stop there. This one is built like a service you'd actually run:

- **Structured, schema-validated outputs** - every finding is a Pydantic-validated object with `file`, `line`, `severity`, `category`, and `issue`, not free text. The model can't return something the rest of the pipeline can't parse.
- **Structural code retrieval (no embeddings)** - given a local checkout, it greps the working tree for callers of changed symbols, resolves the changed files' imports, and surfaces related tests, then feeds that context alongside the diff so the model can reason about a change's blast radius. For "what does this diff *depend on*," exact symbol matching is more precise than semantic similarity and needs no vector store or extra infra.
- **A real evaluation harness** - the agent is measured against a labeled planted-bug dataset with automated, location-based scoring (precision / recall / F1, plus per-bug-type recall). Quality is a number, not a vibe.

---

## Key results

Measured against the bundled planted-bug benchmark (`evals/cases/seed.json`): **12 cases - 8 buggy, 4 clean.** Bugs are planted by hand, so the ground truth is exact.

| Metric | Score |
|---|---|
| Recall | 1.00 (8/8 planted bugs caught) |
| Precision | ~0.73 |
| F1 | 0.84 |

*(Representative run: TP=8, FN=0, FP=3, TN=1. Exact numbers vary run to run since the reviewer is an LLM. The harness regenerates the report on demand see below.)*

The benchmark is intentionally small and hand-built its purpose is to demonstrate an honest, reproducible evaluation methodology, and it's designed to grow: drop more JSON cases into `evals/cases/` and re-run.

---

## How it works

```text
app/
  config/          Environment-based settings
  github/          GitHub API client, PR-URL parsing, diff parsing
  llm/             Anthropic review client
  models/          Pydantic response models (structured findings)
  retrieval/       Structural (grep-based) retrieval of diff context
  review_service.py    Orchestration: fetch -> retrieve -> review -> post
evals/             Eval harness: labeled dataset, scorer, report generator
main.py            CLI entry point
tests/             Unit tests (diff parsing, retrieval, review service, eval)
```

Pipeline: parse the PR URL → fetch the unified diff via the GitHub API → (optional) run structural retrieval over a local checkout → send diff + context to the model → validate findings against the Pydantic schema → print, and optionally post inline review comments → append the run to `runs/runs.jsonl`.

---

## Setup

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env`:

```bash
ANTHROPIC_API_KEY=your_anthropic_key
GITHUB_TOKEN=your_github_token
```

Optional: `MODEL_NAME` overrides the default model (`claude-haiku-4-5`).

---

## Usage

Review a PR (print findings only):

```bash
python main.py https://github.com/owner/repo/pull/123
```

Add structural code context from a local checkout (enables caller/import/test retrieval):

```bash
python main.py https://github.com/owner/repo/pull/123 --repo /path/to/checkout
```

Preview the GitHub review workflow without posting:

```bash
python main.py https://github.com/owner/repo/pull/123 --dry-run-comments
```

Post findings as inline review comments:

```bash
python main.py https://github.com/owner/repo/pull/123 --post
```

Example output:

```text
[major/correctness] app/example.py:42
  This branch can return None even though callers expect a string.
```

---

## Evaluation

The harness runs the reviewer over every case, scores each finding by location (a finding catches a planted bug if it lands within a few lines of it), and writes `evals/report.md` + `evals/report.json` with precision, recall, F1, per-bug-type recall, and a per-case breakdown.

```bash
python -m evals.run               # full eval (needs ANTHROPIC_API_KEY)
python -m evals.run --retrieval   # same, with structural retrieval enabled
```

Scoring, per case:

- **buggy** + a finding on the planted line → true positive; nothing → false negative
- **clean** + any finding → false positive; silent → true negative

Grow the dataset by adding JSON files to `evals/cases/` (one case or a list). Each buggy case is a unified diff plus the expected `{file, lines, bug_type, category}`.

---

## Testing

```bash
python -m unittest
```

Covers diff parsing, structural retrieval, the review service, and the eval scorer.

---

## Note on data

The `runs/` directory can contain full PR diffs, including private repository code. Keep those files local and don't commit them.
