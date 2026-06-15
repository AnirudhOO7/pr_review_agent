from typing import Literal

from pydantic import BaseModel, Field


class PRFinding(BaseModel):
    """A single issue identified in a pull request diff."""

    file: str = Field(description="Path to the file the finding refers to.")
    line: int | None = Field(
        default=None,
        description="Most relevant line number, or null for file-level findings.",
    )
    severity: Literal["minor", "major", "critical"]
    category: Literal[
        "correctness",
        "security",
        "performance",
        "style",
        "maintainability",
    ]
    issue: str = Field(description="Clear, specific description of the problem")


class ReviewResult(BaseModel):
    """The full set of findings produced for one review run."""

    findings: list[PRFinding]
