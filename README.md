# PR Review Agent

PR Review Agent is a small Python CLI that reviews GitHub pull requests with an
LLM. You pass it a GitHub PR URL, it fetches the pull request diff, asks
Anthropic for structured review findings, prints the results, and stores an
audit record for later inspection.

## What It Does

- Fetches a unified diff for a GitHub pull request.
- Optionally retrieves repository context (callers, imports, related tests) for
  the diff from a local checkout via structural grep — no embeddings.
- Sends the diff (and any context) to an Anthropic model for code review.
- Returns structured findings with file, line, severity, category, and issue.
- Optionally posts findings as inline review comments on the PR.
- Stores each run as JSONL in `runs/runs.jsonl`.

## Project Structure

```text
app/
  config/          Environment-based settings
  github/          GitHub API client, PR URL parsing, diff parsing
  llm/             Anthropic review client
  models/          Pydantic response models
  retrieval/       Structural (grep-based) retrieval of diff context
  review_service.py
evals/             Eval harness: labeled dataset, scorer, report generator
main.py            CLI entry point
```

## Setup

This project requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```bash
ANTHROPIC_API_KEY=your_anthropic_key
GITHUB_TOKEN=your_github_token
```

## Usage

```bash
python main.py https://github.com/owner/repo/pull/123
```

Preview the GitHub review workflow without posting comments:

```bash
python main.py https://github.com/owner/repo/pull/123 --dry-run-comments
```

Post review comments to the PR:

```bash
python main.py https://github.com/owner/repo/pull/123 --post
```

Add repository context with `--repo` pointing at a local checkout. The agent
runs structural retrieval — grepping the working tree for callers of the
changed symbols, resolving the changed files' imports, and surfacing related
tests — and feeds that alongside the diff so it can reason about the change's
blast radius:

```bash
python main.py https://github.com/owner/repo/pull/123 --repo /path/to/checkout
```

Retrieval is lexical/structural (no embeddings or vector store): for finding
what a diff *depends on* — exact callers, imports, tests — matching on symbol
names is more precise than semantic similarity, and needs no extra infra.

Example output:

```text
[major/correctness] app/example.py:42
  This branch can return None even though callers expect a string.
```

## Configuration

Environment variables:

- `ANTHROPIC_API_KEY`: Anthropic API key used by the reviewer.
- `GITHUB_TOKEN`: GitHub token used to fetch PR diffs.
- `MODEL_NAME`: Optional model override. Defaults to `claude-haiku-4-5`.

## Evaluation

The eval harness measures how well the agent finds bugs, against a labeled
dataset of planted-bug and clean "PRs" in `evals/cases/`. Bugs are planted by
hand so the ground truth is exact.

```bash
python -m evals.run               # full eval (needs ANTHROPIC_API_KEY)
python -m evals.run --retrieval   # same, with structural retrieval enabled
```

It runs the reviewer over every case, scores findings by location (a finding
catches a planted bug if it lands within a few lines of it), and writes
`evals/report.md` + `evals/report.json` with precision, recall, F1, per-bug-type
recall, and a per-case breakdown.

Scoring outcomes per case:

- **buggy** + a finding on the planted line → true positive; no such finding → false negative
- **clean** + any finding → false positive; silent → true negative

Grow the dataset by dropping more JSON files into `evals/cases/` (a file holds
one case or a list). Each case is a unified diff plus, for buggy cases, the
expected `{file, lines, bug_type, category}`.

## Development

Run the tests:

```bash
python -m unittest
```

## Notes

The `runs/` directory can contain full pull request diffs, including private
repository code. Keep those files local and avoid committing them.
