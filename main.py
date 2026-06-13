import argparse

from app.review_service import ReviewService


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a GitHub pull request.")
    parser.add_argument("pr_url", help="URL of the PR to review")
    args = parser.parse_args()

    with ReviewService() as service:
        result = service.review_pr(args.pr_url)

    if not result.findings:
        print("No issues found.")
        return
    for f in result.findings:
        location = f"{f.file}:{f.line}" if f.line is not None else f.file
        print(f"[{f.severity}/{f.category}] {location}\n  {f.issue}\n")


if __name__ == "__main__":
    main()