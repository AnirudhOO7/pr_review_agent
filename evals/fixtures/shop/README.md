# Fixture repo: shop

A tiny checkout codebase used as the local checkout for the eval's
context-dependent cases (`evals/cases/context.json`). Each of those cases is a
diff against a file here whose bug (or safety) only shows up in the callers,
imports or tests elsewhere in this tree, so it measures what structural
retrieval adds. Not imported or executed by the project.
