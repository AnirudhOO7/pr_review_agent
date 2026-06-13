from app.config import settings
import httpx
import re

GITHUB_API_BASE = "https://api.github.com"


# Matches the standard web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
_PR_URL_PATTERN = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<pull_number>\d+)"
)


class GitHubError(Exception):
    """Raised when a GitHub API request fails or a URL can't be parsed."""

def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Extract (owner, repo, number) from a GitHub pull request URL."""
    match = _PR_URL_PATTERN.search(url)
    if not match:
        raise GitHubError(
            f"Not a valid GitHub PR URL: {url!r}. "
            "Expected https://github.com/owner/repo/pull/123"
        )
    return match["owner"], match["repo"], int(match["pull_number"])


class GithubClient:
    """Minimal GitHub API client for retrieving PR diffs."""
    def __init__(self, token: str | None = None, timeout: float = 30.0) -> None:
        self._token = token or settings.github_token
        if not self._token:
            raise GitHubError(
                "No GitHub token configured. Set GITHUB_TOKEN in your .env."
            )
        self._client = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers={
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2026-03-10",
            },
            timeout=timeout,
        )
    def fetch_diff(self, pr_url: str) -> str:
        """Fetch the unified diff for a pull request, given its web URL."""
        owner, repo, pull_number = parse_pr_url(pr_url)
        try:
            response = self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pull_number}",
                headers={"Accept": "application/vnd.github.v3.diff"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubError(self._explain_error(exc)) from exc
        except httpx.RequestError as exc:
            raise GitHubError(f"Network error contacting GitHub: {exc}") from exc
        return response.text

    @staticmethod
    def _explain_error(exc: httpx.HTTPStatusError) -> str:
        status = exc.response.status_code
        if status == 401:
            return "GitHub auth failed (401). Check that GITHUB_TOKEN is valid."
        if status == 403:
            return "Forbidden (403). Token may lack scope, or you hit a rate limit."
        if status == 404:
            return "PR not found (404). Check the URL or the token's repo access."
        return f"GitHub API error ({status}): {exc.response.text[:200]}"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()