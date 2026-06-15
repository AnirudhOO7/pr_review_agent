from anthropic import Anthropic
from anthropic import APIError, APIStatusError

from app.config.config import settings
from app.models.findings import ReviewResult


class ReviewError(Exception):
    """Raised when the LLM review call fails."""

class LLMReviewer:
    def __init__(self, model: str | None = None) -> None:
        if not settings.anthropic_api_key:
            raise ReviewError(
                "No Anthropic API key configured. Set ANTHROPIC_API_KEY in your .env."
            )
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = model or settings.model_name

    def review(self, diff: str, context: str | None = None) -> ReviewResult:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=(
                    "You are a senior code reviewer. Review the unified diff "
                    "and report concrete issues — correctness, security, "
                    "performance, style, maintainability. Only report real "
                    "problems; do not invent issues to fill the list. "
                    "When repository context is provided, use it to judge "
                    "whether a change breaks callers, mishandles an imported "
                    "API, or lacks test coverage — but only report findings "
                    "about the diff itself, not about the context."
                ),
                messages=[{"role": "user", "content": self._build_prompt(diff, context)}],
                output_format=ReviewResult,
            )
        except (APIStatusError, APIError) as exc:
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
