# PR Review Agent — Eval Report

- Generated: 2026-06-15T20:33:39+00:00
- Model: `claude-haiku-4-5`
- Retrieval: off
- Match tolerance: ±3 lines
- Cases: 12 (8 buggy, 4 clean)

## Detection metrics

| Metric | Value |
| --- | --- |
| Precision | 0.73 |
| Recall | 1.00 |
| F1 | 0.84 |
| TP / FN / FP / TN | 8 / 0 / 3 / 1 |

## Recall by bug type

| Bug type | Caught / Total |
| --- | --- |
| injection | 2/2 |
| missing-guard | 1/1 |
| missing-null-check | 1/1 |
| mutable-default | 1/1 |
| off-by-one | 1/1 |
| race-condition | 1/1 |
| resource-leak | 1/1 |

## Noise

- Spurious findings on clean cases: 8

## Per-case results

| Case | Label | Bug type | Outcome | Match line | # findings |
| --- | --- | --- | --- | --- | --- |
| buggy_command_injection | buggy | injection | ✓ caught | 3 | 3 |
| buggy_division_no_guard | buggy | missing-guard | ✓ caught | 3 | 1 |
| buggy_missing_null_check | buggy | missing-null-check | ✓ caught | 2 | 3 |
| buggy_mutable_default | buggy | mutable-default | ✓ caught | 1 | 1 |
| buggy_off_by_one | buggy | off-by-one | ✓ caught | 4 | 2 |
| buggy_race_condition | buggy | race-condition | ✓ caught | 1 | 4 |
| buggy_resource_leak | buggy | resource-leak | ✓ caught | 1 | 3 |
| buggy_sql_injection | buggy | injection | ✓ caught | 2 | 2 |
| clean_average_guarded | clean | — | ✗ false alarm | — | 3 |
| clean_context_manager_io | clean | — | ✗ false alarm | — | 3 |
| clean_parametrized_sql | clean | — | ✓ silent | — | 0 |
| clean_slugify | clean | — | ✗ false alarm | — | 2 |
