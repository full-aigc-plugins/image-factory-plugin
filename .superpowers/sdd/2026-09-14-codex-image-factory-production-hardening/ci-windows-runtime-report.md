# Windows CI runtime portability remediation

Date: 2026-09-14

Source run: GitHub Actions `34827669229`

Scope: Windows 3.11 and 3.13 offline-gate failures only

## Root cause

The 20 reported Windows failures reduced to four platform assumptions:

1. `generation_runner` passed a `.cmd` Codex launcher directly to Win32
   `CreateProcess`, producing `WinError 193` before the fake Codex could run.
2. prompt-library and concurrency tests executed the POSIX `bin/image-factory`
   shell wrapper directly on Windows.
3. capability probing treated POSIX execute bits as the cross-platform
   executable contract and did not discover `codex.cmd`/`codex.exe` names.
4. tests used POSIX `chmod` behavior and checkout mode bits as Windows runtime
   facts, although Windows does not expose those semantics through `stat` and
   `os.access` in the same way.

## RED evidence

Before production changes, the new platform simulations failed with:

- `AttributeError: module 'generation_runner' has no attribute 'build_subprocess_argv'`
- `AttributeError: module 'capability_probe' has no attribute '_is_executable_file'`

These failures established that the missing behavior was in production launch
and probe logic, rather than only in Windows fixtures.

## Implementation

- `.cmd` and `.bat` Codex launchers are now invoked through `COMSPEC /d /s /c`
  while `subprocess.run` remains `shell=False`. Every token is quoted and the
  command is wrapped using the documented nested-quote form; no raw or unquoted
  prompt is interpolated. Native executables retain the original argv path.
- Capability probing now applies native semantics: POSIX requires `X_OK`, while
  Windows accepts only an existing file with an executable `PATHEXT` suffix.
  PATH and appserver discovery include Windows executable extensions. An
  arbitrary explicit file remains rejected.
- Windows fake-Codex fixtures use `.cmd`; POSIX fixtures retain executable shell
  scripts.
- Tests of the Python CLI call `scripts/image_factory_cli.py` through
  `sys.executable`, including both concurrency subprocesses.
- The chmod-only unwritable-directory test is skipped on Windows with an
  explicit semantic reason; it continues to exercise the real permission
  boundary on POSIX.
- Distribution validation checks the Git index contract (`100755`) instead of
  assuming checkout mode bits survive on Windows.
- Approval and sandbox bypass flags remain forbidden and unchanged.

## Verification evidence

- Targeted RED-to-GREEN set: 7 tests passed.
- Default interpreter (`Python 3.14.3`): 395 tests passed in 19.822s.
- Python 3.13.0: 395 tests passed in 18.060s.
- `python3 -m compileall -q scripts tests`: exit 0.
- `python3.13 -m compileall -q scripts tests`: exit 0.
- `python3 scripts/validate_distribution.py .`: exit 0, reported
  `validated codex-image-factory compatibility foundation 0.1.2`.
- `git diff --check`: exit 0.

The remote Windows matrix has not been rerun because this task does not
authorize pushing. Its status remains pending fresh remote CI evidence.
