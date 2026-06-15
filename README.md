# PR Review Agent

PR Review Agent is a small Python CLI that reviews GitHub pull requests with an
LLM. You pass it a GitHub PR URL, it fetches the pull request diff, asks
Anthropic for structured review findings, prints the results, and stores an
audit record for later inspection.

## What It Does

- Fetches a unified diff for a GitHub pull request.
- Sends the diff to an Anthropic model for code review.
- Returns structured findings with file, line, severity, category, and issue.
- Stores each run as JSONL in `runs/runs.jsonl`.

## Project Structure

```text
app/
  config/          Environment-based settings
  github/          GitHub API client and PR URL parsing
  llm/             Anthropic review client
  models/          Pydantic response models
  review_service.py
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

## Development

Run the tests:

```bash
python -m unittest
```

## Notes

The `runs/` directory can contain full pull request diffs, including private
repository code. Keep those files local and avoid committing them.
