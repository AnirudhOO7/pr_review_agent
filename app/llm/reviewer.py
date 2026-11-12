from anthropic import Anthropic
from anthropic import APIError, APIStatusError

from app.config.config import settings
from app.models.findings import ReviewResult


class ReviewError(Exception):
    """Raised when the LLM review call fails."""


# v1: the original prompt. Broad remit (style and maintainability included),
# which catches bugs but also flags clean code.
PROMPT_V1 = (
    "You are a senior code reviewer. Review the unified diff "
    "and report concrete issues — correctness, security, "
    "performance, style, maintainability. Only report real "
    "problems; do not invent issues to fill the list. "
    "When repository context is provided, use it to judge "
    "whether a change breaks callers, mishandles an imported "
    "API, or lacks test coverage — but only report findings "
    "about the diff itself, not about the context."
)

# v2: defect-only. Every finding needs a concrete failure scenario, nits are
# out of scope, and an empty review is an explicitly good outcome.
PROMPT_V2 = """You are a senior engineer reviewing a pull request for defects.

Report a finding ONLY if the changed code will misbehave: wrong results, a crash
or unhandled exception, a security vulnerability, data loss or corruption, a
race condition, a resource leak, or a broken contract with code that calls it.
For every finding you must be able to name a concrete input or situation that
triggers the problem. If you cannot, do not report it.

Do NOT report: style, naming, formatting, docstrings, comments, type hints,
logging, missing tests, "consider" suggestions, refactors, or speculative
issues that depend on code you cannot see. Do not report something merely
because it could be written differently.

Most well-written changes have no defects. Returning an empty findings list is
the correct answer when the diff is sound; never pad the list.

Location: set `file` to the new-side path and `line` to the new-file line number
of the changed line where the defect is (count from the @@ hunk header).

When repository context is provided (callers, imports, tests), use it to check
whether the change breaks how existing code uses the changed function or data:
signatures, return types, None-vs-exception behavior, units, keys, ordering.
Report such a break on the changed line in the diff, and name the affected
caller in the issue text. Only report findings about the diff itself."""

PROMPTS = {"v1": PROMPT_V1, "v2": PROMPT_V2}


class LLMReviewer:
    def __init__(self, model: str | None = None, prompt: str | None = None) -> None:
        if not settings.anthropic_api_key:
            raise ReviewError(
                "No Anthropic API key configured. Set ANTHROPIC_API_KEY in your .env."
            )
        self.prompt = prompt or settings.review_prompt
        if self.prompt not in PROMPTS:
            raise ReviewError(f"Unknown prompt {self.prompt!r}; choose from {sorted(PROMPTS)}.")
        # Extra retries so concurrent eval runs ride out rate limits.
        self._client = Anthropic(api_key=settings.anthropic_api_key, max_retries=6)
        self.model = model or settings.model_name

    def review(self, diff: str, context: str | None = None) -> ReviewResult:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=PROMPTS[self.prompt],
                messages=[{"role": "user", "content": self._build_prompt(diff, context)}],
                output_format=ReviewResult,
            )
        except APIStatusError as exc:
            if exc.status_code == 401:
                raise ReviewError(
                    "Anthropic rejected the API key (401). Update ANTHROPIC_API_KEY "
                    "in .env and restart the server."
                ) from exc
            raise ReviewError(f"LLM review failed: {exc}") from exc
        except APIError as exc:
            raise ReviewError(f"LLM review failed: {exc}") from exc
        return response.parsed_output

    @staticmethod
    def _build_prompt(diff: str, context: str | None) -> str:
        if not context:
            return diff
        return (
            f"{context}\n\n"
            "# Diff under review\n"
            "Review only the changes in this diff. Use the repository context "
            "above to inform your findings.\n\n"
            f"{diff}"
        )
