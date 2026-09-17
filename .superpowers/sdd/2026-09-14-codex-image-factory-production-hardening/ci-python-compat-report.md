# Python 3.13 CI compatibility repair

## Status

The confirmed Python 3.13 test-import failure is repaired locally with one
compatibility declaration. No push, tag, installation, canary, release action,
or SDD progress update was performed.

## Root cause and fix

`tests/test_cli.py` annotated `derived_run_targets` with `CliFixture` before the
fixture class was defined. The local default Python 3.14 accepted the module,
while Python 3.13 evaluated the annotation during import and raised `NameError`.

The test module now imports `annotations` from `__future__`, deferring annotation
evaluation without changing runtime behavior, test cases, or the test count.

## Red/green evidence

Before the fix:

```text
python3.13 -m unittest tests.test_cli -v
NameError: name 'CliFixture' is not defined
exit 1
```

After the fix:

```text
python3.13 -m unittest tests.test_cli -v
Ran 68 tests in 8.278s
OK
```

## Full verification

```text
python3.13 -m unittest discover -s tests
Ran 392 tests in 18.326s
OK

python3 -m unittest discover -s tests
Ran 392 tests in 19.265s
OK

python3.13 -m compileall -q scripts tests
exit 0

python3 -m compileall -q scripts tests
exit 0

python3 scripts/validate_distribution.py .
validated image-factory compatibility foundation 0.1.2

git diff --check
exit 0
```

The existing offline verification already records 392 successful tests, so no
offline evidence update was necessary.

## Remaining concern

Local reproduction proves the Python 3.13 import failure is removed. The six-cell
GitHub Actions matrix remains an external gate and must be rerun after an
authorized push; this task did not push or mutate any release/runtime evidence.
