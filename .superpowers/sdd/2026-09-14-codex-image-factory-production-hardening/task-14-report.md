# Task 14 Report: Definite failed-item lifecycle

## Final status

PASS. A `Partial` current round containing only terminal `Generated`, `Failed`,
or `Skipped` rows can now be evaluated deterministically. Receiptless definite
failures score `missing_artifact` and finalize atomically to `Evaluated` without
changing their ledger evidence. The next round is created only after an explicit
rewrite or `retry-unchanged` instruction, and generation still requires fresh
approval.

`Pending`, `Attempting`, and `Unknown` remain non-evaluable and preserve job and
scores bytes. `Generated` rows still require exact receipt evidence, while a
receipt attached to `Failed` or `Skipped` is rejected as contradictory.

## TDD evidence

- RED: the initial focused run failed because definite failures were rejected by
  the generated-receipt-only check, and nonterminal states returned the old
  undifferentiated evidence error.
- GREEN: `python3 -m unittest tests.test_cli.EvaluateAndOptimizeCommandTests tests.test_multi_round_lifecycle -v`
  passed after the minimal terminal-row eligibility implementation.
- Skill RED/GREEN: the new judge/recovery contract assertions failed before the
  Skill changes and passed after them.

## Verification evidence

- Focused source and Skill suite: 101 tests passed.
- Full source suite: 386 tests passed.
- `python3 -m compileall -q scripts tests`: exited 0.
- `python3 scripts/validate_distribution.py .`: reported compatibility
  foundation 0.1.2 and exited 0.
- `git diff --check`: exited 0.

## Self-review

- Evaluation eligibility is checked before advisory/label reads and before
  either scores or ledger mutation.
- Failed/Skipped ledger rows are read only; evaluation persists through the
  existing single `record_evaluation_final` mutation.
- Optimization and approval behavior remain on the Task 12/13 safety path; the
  regression test proves zero generation invocations through evaluation,
  optimization, validation, quote, and approval refusal.
- No push, tag, installation, paid canary, or external generation was performed.

## Commit

This report and the Task 14 implementation are committed together as
`fix: evaluate definite image failures`; use the commit hash reported by the
executing agent.

## Concerns and remaining gates

No Task 14 correctness concern remains in the local offline scope. Independent
Task 14 review and renewed whole-branch review are still required. Remote CI,
remote SHA parity, fresh Marketplace installation, fresh-session smoke, and paid
canary remain separate release gates and were not authorized here.
