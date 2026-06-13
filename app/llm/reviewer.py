from anthropic import Anthropic
from anthropic import APIError, APIStatusError

from app.config.config import settings
from app.models.findings import ReviewResult


class ReviewError(Exception):
    """Raised when the LLM review call fails."""

class LLMReviewer:
    def __init__(self, model: str | None = None) -> None:
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = model or settings.model_name

    def review(self, diff:str)->ReviewResult:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=(
                    "You are a senior code reviewer. Review the unified diff "
                    "and report concrete issues — correctness, security, "
                    "performance, style, maintainability. Only report real "
                    "problems; do not invent issues to fill the list."
                ),
                messages=[{"role": "user", "content": diff}],
                output_format=ReviewResult,
            )
        except (APIStatusError, APIError) as exc:
            raise ReviewError(f"LLM review failed: {exc}") from exc
        return response.parsed_output