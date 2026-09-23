# Runtime reliability and attempt recovery

Image Factory 0.5.0 records every external generation as a durable attempt next
to the job ledger. The ledger remains the batch state authority; the attempt
directory is streaming evidence that can be observed while Codex is still
running and used to attribute a late artifact without issuing another call.

## Evidence layout

For `job.json` and attempt `<attempt-id>`:

```text
job.json.attempts/<attempt-id>/
├── events.jsonl
└── progress.json
```

`events.jsonl` is append-only. `progress.json` is atomically replaced and follows
`schemas/attempt_progress.schema.json`. It records the item, status, session,
candidate files, attributed files, the pre-attempt generation-directory snapshot,
and the exact generation directory used by the attempt.

## Attribution rules

1. If Codex reports a session id, only files below that session directory belong
   to the attempt. A simultaneous file from another process is ignored.
2. If an older event stream reports no session, exactly one new file is accepted
   as a compatibility fallback. Zero or multiple files are ambiguous.
3. Timeout and interruption keep the attempt in `Unknown`; they never retry.
4. `recover` searches the original attempt evidence. A valid late artifact from
   the recorded session is collected and receipted without invoking Codex.

## Observe a long run

```bash
bin/image-factory status --job job.json --watch --watch-timeout 30 --json
```

The command returns when the ledger revision, attempt event count, or attempt
status changes. It is read-only and never starts or retries generation.

## Capacity gate

An approved run checks the work, generation, and destination filesystems before
the first external call. The conservative budget is the larger of 256 MiB per
batch or 64 MiB per pending image. Failure reports required and available bytes,
writes no new job ledger, invokes no generator, and deletes nothing.
