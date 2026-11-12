# PR Review Agent — Eval Report

- Generated: 2026-11-12T14:10:11+00:00
- Model: `claude-haiku-4-5` · prompt `v2`
- Retrieval: on
- Severity floor: minor · match tolerance ±3 lines
- Cases: 43 (24 buggy, 19 clean) · trials: 3

## Detection metrics (mean ± std across trials)

| Metric | Value |
| --- | --- |
| Precision | 0.69 ± 0.01 |
| Recall | 0.97 ± 0.02 |
| F1 | 0.81 ± 0.00 |
| False-alarm rate (clean cases flagged) | 0.54 ± 0.03 |
| TP / FN / FP / TN (mean) | 23.3 / 0.7 / 10.3 / 8.7 |

## Subset: context-dependent (11 cases)

| Precision | Recall | F1 | False-alarm rate |
| --- | --- | --- | --- |
| 0.67 ± 0.00 | 1.00 ± 0.00 | 0.80 ± 0.00 | 0.60 ± 0.00 |

## Recall by bug type

| Bug type | Caught / Total |
| --- | --- |
| async | 3/3 |
| caller-contract | 18/18 |
| datetime | 3/3 |
| error-handling | 3/3 |
| infinite-loop | 3/3 |
| injection | 6/6 |
| insecure-deserialization | 3/3 |
| iteration-mutation | 3/3 |
| logic-error | 3/3 |
| missing-guard | 3/3 |
| missing-null-check | 3/3 |
| mutable-default | 3/3 |
| off-by-one | 3/3 |
| path-traversal | 3/3 |
| race-condition | 1/3 |
| resource-leak | 3/3 |
| weak-crypto | 3/3 |
| xss | 3/3 |

## Per-case results

| Case | Label | Bug type | Outcome | Across trials | Match line | Avg findings |
| --- | --- | --- | --- | --- | --- | --- |
| buggy_command_injection | buggy | injection | ✓ caught | TP TP TP | 3 | 1.67 |
| buggy_division_no_guard | buggy | missing-guard | ✓ caught | TP TP TP | 3 | 1 |
| buggy_infinite_pagination | buggy | infinite-loop | ✓ caught | TP TP TP | 9 | 1 |
| buggy_md5_password | buggy | weak-crypto | ✓ caught | TP TP TP | 4 | 1.33 |
| buggy_missing_await | buggy | async | ✓ caught | TP TP TP | 2 | 1 |
| buggy_missing_null_check | buggy | missing-null-check | ✓ caught | TP TP TP | 2 | 1.33 |
| buggy_mutable_default | buggy | mutable-default | ✓ caught | TP TP TP | 1 | 1 |
| buggy_mutate_while_iterating | buggy | iteration-mutation | ✓ caught | TP TP TP | 2 | 1 |
| buggy_naive_datetime | buggy | datetime | ✓ caught | TP TP TP | 10 | 1 |
| buggy_off_by_one | buggy | off-by-one | ✓ caught | TP TP TP | 4 | 1 |
| buggy_or_condition_authz | buggy | logic-error | ✓ caught | TP TP TP | 2 | 1 |
| buggy_path_traversal | buggy | path-traversal | ✓ caught | TP TP TP | 11 | 1 |
| buggy_pickle_session | buggy | insecure-deserialization | ✓ caught | TP TP TP | 9 | 1 |
| buggy_race_condition | buggy | race-condition | ✗ missed | FN TP FN | 1 | 0.33 |
| buggy_resource_leak | buggy | resource-leak | ✓ caught | TP TP TP | 1 | 1 |
| buggy_sql_injection | buggy | injection | ✓ caught | TP TP TP | 2 | 1 |
| buggy_swallowed_payment_error | buggy | error-handling | ✓ caught | TP TP TP | 14 | 1 |
| buggy_xss_innerhtml | buggy | xss | ✓ caught | TP TP TP | 4 | 1 |
| clean_average_guarded | clean | — | ✓ silent | TN TN TN | — | 0 |
| clean_awaited_lookup | clean | — | ✓ silent | TN FP TN | — | 0.33 |
| clean_aware_datetime | clean | — | ✗ false alarm | FP FP TN | — | 0.67 |
| clean_bounded_pagination | clean | — | ✗ false alarm | FP FP FP | — | 1 |
| clean_context_manager_io | clean | — | ✗ false alarm | FP FP FP | — | 1 |
| clean_parametrized_sql | clean | — | ✓ silent | TN TN TN | — | 0 |
| clean_payment_error_handled | clean | — | ✓ silent | TN TN FP | — | 0.33 |
| clean_rebuild_list | clean | — | ✓ silent | TN TN TN | — | 0 |
| clean_role_membership | clean | — | ✓ silent | TN TN TN | — | 0 |
| clean_safe_download | clean | — | ✗ false alarm | FP FP FP | — | 1 |
| clean_scrypt_password | clean | — | ✗ false alarm | FP FP FP | — | 1.67 |
| clean_signed_session | clean | — | ✗ false alarm | FP FP FP | — | 1.67 |
| clean_slugify | clean | — | ✓ silent | TN TN TN | — | 0 |
| clean_textcontent | clean | — | ✗ false alarm | FP FP FP | — | 1 |
| ctx_buggy_discount_returns_none | buggy | caller-contract | ✓ caught | TP TP TP | 9 | 2 |
| ctx_buggy_find_user_returns_none | buggy | caller-contract | ✓ caught | TP TP TP | 23 | 1.33 |
| ctx_buggy_reserve_stock_required_param | buggy | caller-contract | ✓ caught | TP TP TP | 13 | 1 |
| ctx_buggy_serialize_key_rename | buggy | caller-contract | ✓ caught | TP TP TP | 7 | 1 |
| ctx_buggy_session_ttl_timedelta | buggy | caller-contract | ✓ caught | TP TP TP | 11 | 1 |
| ctx_buggy_split_name_order | buggy | caller-contract | ✓ caught | TP TP TP | 32 | 1 |
| ctx_clean_find_user_strip | clean | — | ✗ false alarm | FP FP FP | — | 1 |
| ctx_clean_format_price_currency | clean | — | ✗ false alarm | FP FP FP | — | 1.33 |
| ctx_clean_lookup_coupon_normalized | clean | — | ✗ false alarm | FP FP FP | — | 1 |
| ctx_clean_serialize_add_field | clean | — | ✓ silent | TN TN TN | — | 0 |
| ctx_clean_session_ttl_constant | clean | — | ✓ silent | TN TN TN | — | 0 |
