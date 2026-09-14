# Collecting runtime evidence

Offline gates live in [`../verification/offline.md`](../verification/offline.md);
release gates live in [`../verification/runtime.md`](../verification/runtime.md).
This file is the procedure for the two runtime gates that a maintainer has to
observe by hand, plus the host conditions that decide whether either can run at
all.

Read this before concluding that a plugin failure is a plugin bug. Every
condition below was observed on a real host, not inferred.

## 1. Host conditions that the plugin depends on

The plugin never generates an image itself. It drives `codex exec`, and the
built-in image tool writes to `<CODEX_HOME>/generated_images`. Three
consequences follow, and all three are checked by `probe`:

| Condition | Checked as | Failure it causes |
| --- | --- | --- |
| A resolvable Codex binary | `codex_binary`, `reasons` | Nothing can be launched |
| A signed-in account | `auth_present` | Generation is refused upstream |
| A writable `<CODEX_HOME>/generated_images` | `generation_dir_writable` | Artifacts cannot be collected at all |

Run `probe` first. It spends nothing and it is the only cheap way to tell a
genuine blocker from a configuration mistake:

```bash
bin/image-factory probe --json --codex-bin <codex> --destination <dir>
```

A verdict other than `available` carries a `guidance` line naming the fix.

### Sandbox interaction (observed)

If the caller wraps the plugin in a restricted sandbox, that sandbox — not the
plugin — decides whether generation works, because the restriction is inherited
by every child process the plugin spawns.

Observed on macOS with `codex exec -s workspace-write -C <dir>`: `probe`
reported `generation_dir_writable: false` with
`reasons: ["verified_codex_binary", "generation_dir_unwritable"]`, because
`~/.codex/generated_images` sits outside the writable workspace. The same
command succeeded with no `-s` override, since the host's own
`sandbox_mode` applied.

Two valid ways to make a restricted caller work:

* leave the host's configured sandbox mode in effect, or
* keep the narrow sandbox and widen it with `--add-dir <CODEX_HOME>/generated_images`.

Do not "fix" this by passing `--dangerously-bypass-approvals-and-sandbox`. The
plugin treats that flag as forbidden on purpose (`scripts/generation_runner.py`,
`FORBIDDEN_FLAGS`, asserted in tests); reaching for it in the caller defeats a
guarantee the plugin is testing for.

### Plan and job placement (observed)

Neither the plan nor the job ledger may live inside the destination tree. Both
placements are refused before anything is spent:

```text
{"error": "path collision between plan and destination tree", "ok": false}
{"error": "path collision between job and destination tree", "ok": false}
```

Keep three sibling directories: `plans/`, `jobs/`, `out/`.

## 2. Cross-platform generation evidence

`runtime.md` records generation evidence observed on **macOS only**. The offline
suite and the job lock run on Linux, macOS, and Windows in CI; the *generation
path* has not been driven on Linux or Windows. Recording it requires a host with
a signed-in account on that platform — CI cannot supply one and must not.

On the target host:

1. `bin/image-factory probe --json` and confirm `verdict: available`.
2. Write a one-item plan under `plans/`, then
   `bin/image-factory validate-plan plans/p.json --json` and confirm `ok: true`.
3. `bin/image-factory quote plans/p.json --json` and record `plan_sha256`.
4. `bin/image-factory run --plan plans/p.json --job jobs/j.json --destination out/ --json`
   and confirm it exits 3 with `error_category: approval_required` while leaving
   `out/` empty. This is the zero-spend check; do not skip it.
5. Re-run step 4 with `--approve` and confirm `ok: true`, one `Generated` item,
   and `state: Completed`.
6. Re-hash the artifact with the platform's own tool (`shasum -a 256`,
   `certutil -hashfile`, `sha256sum`) and confirm it equals the receipt's
   `sha256`. Re-read the pixel size independently of the plugin.

Record the platform, the Codex version, the plan hash, the artifact SHA-256, and
the pixel size in the `runtime.md` row. One host per row; never widen a macOS row
into a "cross-platform" claim.

## 3. Usage-limit evidence

`usage_limit_evidence` stays `NOT_RUN`, and that is a deliberate choice rather
than an oversight. The gate asks whether an exhausted image allowance is
classified correctly, and the only way to observe it is to exhaust the
account's allowance — which would leave the operator unable to generate images
until `resets_at`, and is not something a verification pass may do on the
operator's behalf.

The classification is therefore covered by the offline suite against the event
shape taken from the Codex source, not against a live event. Treat it as
unverified at runtime.

If an operator ever wants the row filled in, they should choose the moment:

1. Confirm the reset time first, in the account's own UI, so the cost is bounded
   and known.
2. Drive a one-item batch to the point where the allowance is already gone.
3. Inspect the ledger `usage_limit` block. The correct outcome is
   `error_category: usage_limit` with `resets_at` carried through, the item left
   **not** retried, and `recover` spending nothing.
4. If a retry happens automatically, or `resets_at` is dropped, that is a real
   defect — record it and stop.

Nothing in the plugin should be changed to make this gate easier to observe.
