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

Measured on the bundled benchmark: **43 hand-planted cases (24 buggy, 19 clean)**, including 11 cross-file cases against a fixture repo. Every configuration was run **3 times**; values are mean ± std. Model: `claude-haiku-4-5`.

| Config | Precision | Recall | F1 | False alarms on clean code |
|---|---|---|---|---|
| Original prompt (v1), no retrieval | 0.57 ± 0.01 | 0.96 ± 0.04 | 0.72 ± 0.02 | 89% |
| Defect-only prompt (v2), no retrieval | 0.70 ± 0.01 | 0.94 ± 0.02 | 0.80 ± 0.00 | 51% |
| **v2 + structural retrieval (headline)** | **0.69 ± 0.01** | **0.97 ± 0.02** | **0.81 ± 0.00** | **54%** |
| v2 + retrieval, major/critical only | 0.71 ± 0.03 | 0.94 ± 0.02 | 0.81 ± 0.02 | 49% |

What the numbers say:

- **The prompt was the big lever.** Requiring a concrete failure scenario for every finding cut false alarms on clean code from 89% to 51% and lifted F1 from 0.72 to 0.80, with recall roughly unchanged.
- **Retrieval helped only where it should, and only a little.** On the 11 cross-file cases, recall went from 0.94 ± 0.10 to 1.00 ± 0.00 (it stopped missing the occasional caller break); overall F1 moved 0.80 → 0.81, which is within noise. Haiku often infers a broken contract from the diff alone (e.g. a docstring that now says "or None"). Retrieval is worth turning on (`--repo`) when a local checkout is available, since it is cheap and made cross-file catches perfect and stable, but it is not where the precision came from.
- **Clean code is the open problem.** Even with v2, about half of clean cases get at least one finding. Reviewing them by hand, the labels hold: the findings are model errors (claiming `textContent` allows XSS, inventing caller breaks for an added default parameter). With retrieval on, the model sometimes over-reads caller context and reports breaks that aren't there.

Full per-case results: [`evals/report.md`](evals/report.md); the A/B table: [`evals/comparison.md`](evals/comparison.md). The original 12-case, single-run result (1.00 recall, 0.73 precision, 0.84 F1) used prompt v1; on the larger set that prompt scores 0.57 precision.

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
  web/             FastAPI server + single-page UI (static/)
evals/             Eval harness: labeled dataset, scorer, report generator
main.py            CLI entry point
tests/             Unit tests (diff parsing, retrieval, review service, eval)
```

Pipeline: parse the PR URL → fetch the unified diff via the GitHub API → (optional) run structural retrieval over a local checkout → send diff + context to the model → validate findings against the Pydantic schema → print, and optionally post inline review comments → append the run to `runs/runs.jsonl`.

---

## Web app

```bash
uv sync                      # or: pip install -r requirements.txt
cp .env.example .env         # add ANTHROPIC_API_KEY (and GITHUB_TOKEN for PR URLs)
uv run uvicorn app.web.server:app --port 8000
```

Open http://localhost:8000. Three tabs:

- **Review** - paste a diff, pick one of the labeled planted-bug samples, or enter a GitHub PR URL. Findings appear inline on the diff and in a severity-sorted list; for samples, the planted bug lines are marked so you can see whether the agent caught it. A GitHub preview shows which findings post inline and which are demoted to the summary, and **Post to GitHub** sends the review (PR URLs only, after a confirmation).
- **Evaluation** - precision / recall / F1, confusion matrix, recall by bug type, and per-case results from `evals/report.json`. Any case can be re-run live.
- **History** - every run from `runs/runs.jsonl`; click one to reopen it.

Pasted diffs only need `ANTHROPIC_API_KEY`. Interactive API docs are at `/api/docs`.

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

The harness runs the reviewer over every case, scores each finding by location (a finding catches a planted bug if it lands within ±3 lines of it), and writes `evals/report.md` + `evals/report.json`.

```bash
python -m evals.run --trials 3          # mean ± std over 3 runs (needs ANTHROPIC_API_KEY)
python -m evals.run --retrieval         # with structural retrieval
python -m evals.run --prompt v1         # the original prompt, for comparison
python -m evals.run --min-severity major  # score only major/critical findings
python -m evals.compare --trials 3      # A/B all configurations -> evals/comparison.md
```

### Dataset (43 cases: 24 planted-bug, 19 clean)

| File | Cases | What it tests |
|---|---|---|
| `evals/cases/seed.json` | 12 (8 bug / 4 clean) | The original set: off-by-one, null check, SQL and command injection, race, division guard, resource leak, mutable default |
| `evals/cases/general.json` | 20 (10 / 10) | Paired bug/clean versions of the same change: path traversal, pickle deserialization, MD5 passwords, swallowed payment errors, always-true auth check, naive datetimes, list mutation while iterating, infinite pagination, missing `await`, `innerHTML` XSS |
| `evals/cases/context.json` | 11 (6 / 5) | Diffs against a fixture repo (`evals/fixtures/shop`) where the change looks fine on its own and only breaks a caller elsewhere: `None` instead of `0.0`, a new required parameter, seconds to `timedelta`, exception to `None`, a renamed dict key, swapped tuple order. The clean counterparts change the same functions in ways every caller can handle. |

`general.json` and `context.json` are generated by `python -m evals.build_cases` from readable before/after source, where a trailing `#@bug` marks the planted line. The marker is stripped and diffs come from `difflib`, so line numbers are computed, not hand-counted. A test checks every expected line is an added line in its diff.

### Metrics

- **Precision / recall / F1**, per case: a buggy case is a TP if a finding lands on the planted bug, else FN; a clean case is a FP if the agent raises anything, else TN.
- **False-alarm rate**: share of clean cases that got any finding. Precision alone can hide this when buggy cases outnumber clean ones.
- **Context-dependent subset**: the same metrics on `context.json` only, where retrieval is the variable.
- **Trials**: the reviewer is an LLM, so each config runs N times and reports mean ± sample std.

### What `evals.compare` measures

| Config | Prompt | Retrieval | Severity floor | Isolates |
|---|---|---|---|---|
| baseline | v1 | off | minor | the original agent |
| prompt-v2 | v2 | off | minor | the effect of the defect-only prompt |
| v2+retr | v2 | on | minor | the effect of structural retrieval |
| v2+retr+M | v2 | on | major | surfacing only major/critical findings |

Prompt `v2` (in `app/llm/reviewer.py`) requires a concrete failure scenario for every finding, rules out style/docs/test nits, and says an empty review is a valid answer. Set `REVIEW_PROMPT=v1` to use the original.

---

## Testing

```bash
python -m unittest
```

Covers diff parsing, structural retrieval, review building, the review service, the web API, and the eval scorer.

---

## Note on data

The `runs/` directory can contain full PR diffs, including private repository code. Keep those files local and don't commit them.
