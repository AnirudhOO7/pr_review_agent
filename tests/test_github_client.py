import unittest

from app.github.client import GitHubError, parse_pr_url


class ParsePrUrlTests(unittest.TestCase):
    def test_parses_standard_pull_request_url(self) -> None:
        self.assertEqual(
            parse_pr_url("https://github.com/openai/example/pull/123"),
            ("openai", "example", 123),
        )

    def test_parses_url_with_extra_path_or_query(self) -> None:
        self.assertEqual(
            parse_pr_url("https://github.com/org/repo/pull/456/files?diff=split"),
            ("org", "repo", 456),
        )

    def test_rejects_non_pull_request_url(self) -> None:
        with self.assertRaises(GitHubError):
            parse_pr_url("https://github.com/openai/example/issues/123")


if __name__ == "__main__":
    unittest.main()
