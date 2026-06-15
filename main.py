import argparse

from app.models.findings import ReviewResult
from app.retrieval.retriever import CodeRetriever
from app.review_service import PostMode, PreparedReview, ReviewService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a GitHub pull request.")
    parser.add_argument("pr_url", help="URL of the PR to review.")
    parser.add_argument(
        "--repo",
        metavar="PATH",
        help="Local checkout of the repo. Enables structural retrieval of "
        "callers, imported modules, and related tests for the diff.",
    )

    comment_group = parser.add_mutually_exclusive_group()
    comment_group.add_argument(
        "--dry-run-comments",
        action="store_true",
        help="Preview the GitHub review workflow without posting comments.",
    )
    comment_group.add_argument(
        "--post",
        action="store_true",
        help="Post findings as inline review comments on the PR.",
    )
    return parser.parse_args()


def post_mode_from_args(args: argparse.Namespace) -> PostMode:
    if args.post:
        return "live"
    if args.dry_run_comments:
        return "dry-run"
    return "none"


def print_findings(result: ReviewResult) -> None:
    if not result.findings:
        print("No issues found.")
        return

    for finding in result.findings:
        location = (
            f"{finding.file}:{finding.line}"
            if finding.line is not None
            else finding.file
        )
        print(
            f"[{finding.severity}/{finding.category}] {location}\n"
            f"  {finding.issue}\n"
        )


def print_prepared_review(prepared: PreparedReview) -> None:
    print(
        "Prepared GitHub review: "
        f"{len(prepared.inline_comments)} inline comment(s), "
        f"{len(prepared.general_findings)} summary finding(s)."
    )


def main() -> None:
    args = parse_args()
    post_mode = post_mode_from_args(args)
    retriever = CodeRetriever(args.repo) if args.repo else None

    with ReviewService(retriever=retriever) as service:
        result = service.review_pr(args.pr_url, post_mode=post_mode)
        prepared = service.last_prepared_review

    print_findings(result)

    if post_mode == "dry-run":
        if prepared is not None:
            print_prepared_review(prepared)
        print("Dry run complete. No comments were posted.")
    elif post_mode == "live":
        print("Posted review to the PR.")


if __name__ == "__main__":
    main()
