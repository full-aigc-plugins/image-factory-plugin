# Windows CI vendored blob parity repair

## Status

The confirmed Windows checkout failure is repaired locally. The complete
`vendor/upstream/**` snapshot tree now disables Git text conversion, preserving
the byte identity required by the pinned upstream blob baseline. No push, tag,
installation, canary, release action, or SDD progress update was performed.

## Root cause and minimal fix

Windows checkout applied CRLF conversion to vendored text files. The baseline
test hashes working-tree bytes as Git blobs, so those converted bytes no longer
matched the pinned upstream Git blob IDs even though the repository content was
correct on Linux and macOS.

Added one repository attribute rule:

```gitattributes
vendor/upstream/** -text
```

This applies to every file in the byte-preserved snapshot tree, including
metadata, source text, and binary assets, and prevents checkout/check-in text
normalization from changing snapshot bytes.

## TDD evidence

RED was observed before `.gitattributes` existed:

```text
python3 -m unittest tests.test_distribution.DistributionTests.test_vendored_upstream_snapshots_disable_git_text_conversion -v
Ran 1 test in 0.036s
FAILED (failures=80)
```

Every vendored file returned `text: unspecified` instead of the required
`text: unset` from the real `git check-attr` command.

GREEN after adding the rule:

```text
python3 -m unittest tests.test_distribution tests.test_upstream_snapshot_baseline -v
Ran 12 tests in 0.325s
OK
```

The distribution regression enumerates the complete vendored tree and verifies
the effective Git attribute for each file. The upstream baseline simultaneously
verifies all 77 pinned source-file blob IDs.

## Full verification

```text
python3.13 -m unittest discover -s tests
Ran 393 tests in 18.118s
OK

python3 -m unittest discover -s tests
Ran 393 tests in 19.750s
OK

python3.13 -m compileall -q scripts tests
exit 0

python3 -m compileall -q scripts tests
exit 0

python3 scripts/validate_distribution.py .
validated codex-image-factory compatibility foundation 0.1.2

git diff --check
exit 0
```

## Remaining gate

The local attribute semantics, blob baseline, and full suites are verified.
Actual six-cell GitHub Actions confirmation remains an external gate after a
separately authorized push; this repair does not claim that remote rerun.
