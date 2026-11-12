# PR Review Agent — Configuration Comparison

- Generated: 2026-11-12T14:10:56+00:00
- Model: `claude-haiku-4-5` · trials per config: 3
- Cases: 43 (24 buggy, 19 clean); context-dependent subset: 11

Values are mean ± sample std across trials. False alarms = share of clean cases where the agent raised any finding.

## All cases

| Config | Prompt | Retrieval | Severity floor | Precision | Recall | F1 | False alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | v1 | off | minor | 0.57 ± 0.01 | 0.96 ± 0.04 | 0.72 ± 0.02 | 0.89 ± 0.00 |
| prompt-v2 | v2 | off | minor | 0.70 ± 0.01 | 0.94 ± 0.02 | 0.80 ± 0.00 | 0.51 ± 0.03 |
| v2+retr | v2 | on | minor | 0.69 ± 0.01 | 0.97 ± 0.02 | 0.81 ± 0.00 | 0.54 ± 0.03 |
| v2+retr+M | v2 | on | major | 0.71 ± 0.03 | 0.94 ± 0.02 | 0.81 ± 0.02 | 0.49 ± 0.08 |

## Context-dependent subset

| Config | Prompt | Retrieval | Severity floor | Precision | Recall | F1 | False alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | v1 | off | minor | 0.55 ± 0.01 | 0.94 ± 0.10 | 0.69 ± 0.02 | 0.93 ± 0.12 |
| prompt-v2 | v2 | off | minor | 0.69 ± 0.08 | 0.94 ± 0.10 | 0.79 ± 0.06 | 0.53 ± 0.23 |
| v2+retr | v2 | on | minor | 0.67 ± 0.00 | 1.00 ± 0.00 | 0.80 ± 0.00 | 0.60 ± 0.00 |
| v2+retr+M | v2 | on | major | 0.67 ± 0.00 | 1.00 ± 0.00 | 0.80 ± 0.00 | 0.60 ± 0.00 |
