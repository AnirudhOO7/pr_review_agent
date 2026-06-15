"""Parse unified diffs to find which lines can carry inline review comments.

GitHub rejects an entire review request (422) if any comment points at a line
that is not part of the diff. Before posting, we compute the set of line numbers
that are actually commentable so we can route findings safely.
"""

import re

# Hunk header, e.g. "@@ -12,7 +12,9 @@ def foo():"
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")


def commentable_lines(diff: str) -> dict[str, set[int]]:
    """Map each file's new path to the set of RIGHT-side line numbers that can
    carry an inline comment.

    Added (`+`) and context (` `) lines inside a hunk are commentable; deleted
    (`-`) lines live on the LEFT side and are skipped, as are hunk headers and
    file metadata.
    """
    result: dict[str, set[int]] = {}
    current_file: str | None = None
    new_line = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            current_file = _new_path(raw)
            if current_file is not None:
                result.setdefault(current_file, set())
            continue

        if raw.startswith("@@"):
            match = _HUNK_HEADER.match(raw)
            new_line = int(match["start"]) if match else 0
            continue

        if current_file is None or raw.startswith(("---", "diff --git", "index ")):
            continue

        if raw.startswith("+"):
            result[current_file].add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            # Deletion: only advances the old-file counter, not the new one.
            continue
        elif raw.startswith("\\"):
            # "\ No newline at end of file" — not a real line.
            continue
        else:
            # Context line (leading space): part of the diff and commentable.
            result[current_file].add(new_line)
            new_line += 1

    return result


def _new_path(plus_header: str) -> str | None:
    """Extract the new-file path from a '+++ b/path' header, or None for /dev/null."""
    path = plus_header[len("+++ ") :].strip()
    if path == "/dev/null":
        return None
    if path.startswith("b/"):
        path = path[2:]
    return path
