#!/usr/bin/env python3
"""The deterministic command line the Skills call.

Every step of a batch is a subcommand here, and this module is the only place
that decides what a run is allowed to do. It is deliberately unglamorous: no
model is called, no prompt is written, and no image is generated. The CLI
validates, records, verifies, and reports, while Codex supplies the generation
and the wording of any rewrite.

The spend gate lives here. `quote` reports the size of a batch without touching
it, and `run` refuses to start a plan that asks for approval unless `--approve`
is passed. That mirrors the discipline of quoting, approving, and only then
running, which is the cheapest way to keep an unattended batch from becoming an
unattended bill.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import artifact_collector
import capability_probe
import evaluator
import generation_runner
import job_ledger
import optimizer
import plan_validator
import prompt_library

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_APPROVAL_REQUIRED = 3
EXIT_CAPABILITY_UNAVAILABLE = 4

DEFAULT_TIMEOUT_SECONDS = generation_runner.DEFAULT_TIMEOUT_SECONDS

# Collection failures share one vocabulary with the ledger, which is narrower
# because a ledger entry has to mean something a resume can act on.
COLLECT_CATEGORY = {
    "artifact_missing": "artifact_missing",
    "duplicate_artifact": "duplicate_artifact",
    "hash_mismatch": "hash_mismatch",
    "duplicate_content": "duplicate_artifact",
    "not_a_png": "generation_failed",
    "below_min_dimension": "generation_failed",
}


def _emit(payload: dict, as_json: bool, summary: list[str] | None = None) -> str:
    if as_json:
        return json.dumps(payload, indent=2, sort_keys=True)
    lines = summary or [f"{key}: {value}" for key, value in sorted(payload.items())]
    return "\n".join(lines)


def _load_json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_codex_home(args: argparse.Namespace) -> Path:
    if args.codex_home:
        return Path(args.codex_home)
    import os

    override = os.environ.get("CODEX_HOME")
    return Path(override) if override else Path.home() / ".codex"


def _resolve_generation_dir(args: argparse.Namespace, codex_home: Path) -> Path:
    return Path(args.generation_dir) if args.generation_dir else codex_home / "generated_images"


def _receipts_path(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts.json")


def _error_category(code: str) -> str:
    if code in job_ledger.ERROR_CATEGORIES:
        return code
    return COLLECT_CATEGORY.get(code, "unknown")


# --------------------------------------------------------------------------- probe


def command_probe(args: argparse.Namespace) -> tuple[int, str]:
    home = _resolve_codex_home(args)
    binary = Path(args.codex_bin) if args.codex_bin else None
    capability = capability_probe.probe(codex_home=home, binary_override=binary)
    payload = capability_probe.as_report(capability)
    code = EXIT_OK if capability.is_available else EXIT_CAPABILITY_UNAVAILABLE
    summary = [f"verdict: {capability.verdict}", *[f"reason: {item}" for item in capability.reasons]]
    if capability.guidance:
        summary.append(f"guidance: {capability.guidance}")
    return code, _emit(payload, args.json, summary)


# -------------------------------------------------------------------- plan commands


def _validated_plan(args: argparse.Namespace) -> tuple[plan_validator.PlanResult, Path]:
    path = Path(args.plan)
    result = plan_validator.validate_plan(_load_json(path), base_dir=path.parent)
    return result, path


def _plan_error_payload(result: plan_validator.PlanResult) -> dict:
    return {
        "ok": False,
        "batch_id": result.batch_id,
        "errors": [
            {"code": error.code, "message": error.message, "item_id": error.item_id}
            for error in result.errors
        ],
    }


def command_validate_plan(args: argparse.Namespace) -> tuple[int, str]:
    result, _path = _validated_plan(args)
    if not result.ok:
        return EXIT_USAGE, _emit(_plan_error_payload(result), args.json)
    payload = {
        "ok": True,
        "batch_id": result.batch_id,
        "round": result.round,
        "max_images": result.max_images,
        "max_rounds": result.max_rounds,
        "require_approval_before_run": result.require_approval_before_run,
        "plan_sha256": result.plan_sha256,
        "require_human_labels": result.require_human_labels,
        "migration_notes": list(result.migration_notes),
        "items": [
            {
                "item_id": item.id,
                "idempotency_key": item.idempotency_key,
                "reference_images": list(item.reference_images),
            }
            for item in result.items
        ],
    }
    return EXIT_OK, _emit(payload, args.json)


def command_quote(args: argparse.Namespace) -> tuple[int, str]:
    result, _path = _validated_plan(args)
    if not result.ok:
        return EXIT_USAGE, _emit(_plan_error_payload(result), args.json)
    payload = {
        "ok": True,
        "batch_id": result.batch_id,
        "round": result.round,
        "image_count": len(result.items),
        "max_images": result.max_images,
        "approval_required": result.require_approval_before_run,
        "plan_sha256": result.plan_sha256,
        "require_human_labels": result.require_human_labels,
        "migration_notes": list(result.migration_notes),
        # Quoting is free: it reads the plan and spends nothing.
        "spends_allowance_on_quote": False,
        "note": (
            "Each item costs one generation call against the Codex account's image "
            "allowance. Approval is required before the first call."
        ),
    }
    summary = [
        f"batch: {result.batch_id} (round {result.round})",
        f"images to generate: {len(result.items)}",
        f"approval required: {result.require_approval_before_run}",
        f"human labels required: {result.require_human_labels}",
        f"plan sha256: {result.plan_sha256}",
        *[f"migration note: {note}" for note in result.migration_notes],
        "this quote spends nothing",
    ]
    return EXIT_OK, _emit(payload, args.json, summary)


# ------------------------------------------------------------------------- run


def _drive_to_running(ledger: job_ledger.JobLedger, approved: bool) -> job_ledger.JobState:
    state = job_ledger.JobState(ledger.read()["state"])
    if state in (job_ledger.JobState.DRAFT, job_ledger.JobState.OPTIMIZED):
        ledger.transition(job_ledger.JobState.PLAN_VALIDATED)
        state = job_ledger.JobState.PLAN_VALIDATED
    if state is job_ledger.JobState.PLAN_VALIDATED and approved:
        ledger.transition(job_ledger.JobState.APPROVED)
        state = job_ledger.JobState.APPROVED
    if state in (
        job_ledger.JobState.APPROVED,
        job_ledger.JobState.COMPLETED,
        job_ledger.JobState.PARTIAL,
        job_ledger.JobState.EVALUATED,
        job_ledger.JobState.UNKNOWN,
    ):
        ledger.transition(job_ledger.JobState.RUNNING)
        return job_ledger.JobState.RUNNING
    return state


def command_run(args: argparse.Namespace) -> tuple[int, str]:
    home = _resolve_codex_home(args)
    generation_dir = _resolve_generation_dir(args, home)
    destination = Path(args.destination)
    job_path = Path(args.job)

    result, plan_path = _validated_plan(args)
    if not result.ok:
        return EXIT_USAGE, _emit(_plan_error_payload(result), args.json)

    binary = Path(args.codex_bin) if args.codex_bin else None
    capability = capability_probe.probe(codex_home=home, binary_override=binary)
    if not capability.is_available:
        payload = {"ok": False, "stage": "capability", **capability_probe.as_report(capability)}
        return EXIT_CAPABILITY_UNAVAILABLE, _emit(payload, args.json)

    codex_binary = str(binary) if binary else generation_runner.resolved_binary(None)

    ledger = job_ledger.JobLedger(job_path)
    if job_path.is_file():
        ledger.read()
    else:
        ledger.write(job_ledger.new_job(result.batch_id))

    if result.require_approval_before_run and not args.approve:
        state = job_ledger.JobState(ledger.read()["state"])
        if state is job_ledger.JobState.DRAFT:
            ledger.transition(job_ledger.JobState.PLAN_VALIDATED)
        ledger.set_error_category("approval_required")
        payload = {
            "ok": False,
            "stage": "approval",
            "error_category": "approval_required",
            "image_count": len(result.items),
            "message": "this plan requires approval; rerun with --approve to spend the allowance",
        }
        return EXIT_APPROVAL_REQUIRED, _emit(payload, args.json)

    _drive_to_running(ledger, approved=True)

    pending = ledger.pending_items(result.items)
    receipts: list[dict] = []
    failed = 0

    for item in pending:
        outcome = generation_runner.run_item(
            binary=codex_binary,
            item=item,
            round_number=result.round,
            workdir=destination / ".work",
            output_dir=destination / ".last-messages",
            generation_dir=generation_dir,
            timeout_seconds=args.timeout,
        )
        if not outcome.ok:
            assert outcome.failure is not None
            failed += 1
            if outcome.failure.code == "quota_exceeded":
                ledger.note_usage_limit(
                    limit_id=outcome.failure.limit_id or job_ledger.IMAGE_LIMIT_ID,
                    resets_at=outcome.failure.resets_at,
                )
                ledger.record_item(item, state="Failed", error_category="quota_exceeded")
                break
            ledger.record_item(
                item, state="Failed", error_category=_error_category(outcome.failure.code)
            )
            continue

        collected = artifact_collector.collect_artifact(
            item=item,
            batch_id=result.batch_id,
            generation_dir=generation_dir,
            destination_dir=destination,
            before=outcome.before_snapshot,
            min_dimension=result.min_dimension,
            # Judging repeats is the evaluator's job, not the collector's: collection
            # records what exists, evaluation decides whether two files being equal
            # is a problem for this batch.
            reject_duplicates=False,
        )
        if not collected.ok:
            assert collected.failure is not None
            failed += 1
            ledger.record_item(
                item, state="Failed", error_category=_error_category(collected.failure.code)
            )
            continue

        assert collected.receipt is not None
        ledger.record_item(
            item, state="Generated", receipt_id=collected.receipt["artifact_id"]
        )
        receipts.append(collected.receipt)

    if receipts:
        existing: list[dict] = []
        manifest = _receipts_path(job_path)
        if manifest.is_file():
            try:
                existing = json.loads(manifest.read_text(encoding="utf-8"))
            except ValueError:
                existing = []
        manifest.write_text(
            json.dumps(existing + receipts, indent=2, sort_keys=True), encoding="utf-8"
        )

    final = job_ledger.JobState.PARTIAL if failed else job_ledger.JobState.COMPLETED
    ledger.transition(final)

    payload = {
        "ok": failed == 0,
        "batch_id": result.batch_id,
        "round": result.round,
        "state": final.value,
        "attempted": len(pending),
        "failed": failed,
        "receipts": receipts,
        "ledger": str(job_path),
    }
    code = EXIT_OK if failed == 0 else EXIT_FAILURE
    return code, _emit(payload, args.json)


# -------------------------------------------------------------------- evaluate


def _advisory_from_file(path: str | None) -> dict:
    if not path:
        return {}
    raw = _load_json(Path(path))
    if not isinstance(raw, dict):
        raise ValueError("advisory file must be a JSON object of item id to [score, reason]")
    return {key: tuple(value) if isinstance(value, list) else value for key, value in raw.items()}


def command_evaluate(args: argparse.Namespace) -> tuple[int, str]:
    result, _plan_path = _validated_plan(args)
    if not result.ok:
        return EXIT_USAGE, _emit(_plan_error_payload(result), args.json)

    manifest = _receipts_path(Path(args.job))
    receipts = {}
    if manifest.is_file():
        for receipt in json.loads(manifest.read_text(encoding="utf-8")):
            receipts[receipt["item_id"]] = receipt

    try:
        advisory = _advisory_from_file(args.advisory)
        labels = _load_json(Path(args.labels)) if args.labels else {}
    except ValueError as error:
        return EXIT_USAGE, _emit({"ok": False, "error": str(error)}, args.json)

    evaluation = evaluator.evaluate_batch(
        batch_id=result.batch_id,
        round_number=result.round,
        items=result.items,
        receipts=receipts,
        destination_dir=Path(args.destination),
        min_dimension=result.min_dimension,
        reject_duplicates=result.reject_duplicates,
        pass_threshold=result.pass_threshold,
        advisory_enabled=result.advisory_enabled,
        require_human_labels=False,
        advisory=advisory,
        human_labels=labels,
    )
    scores_path = Path(args.scores)
    scores_path.write_text(evaluator.render_scores(evaluation) + "\n", encoding="utf-8")

    payload = {
        "ok": evaluation.ok,
        "decision": evaluation.scores["decision"],
        "all_gates_passed": evaluation.scores["deterministic_gates"]["all_passed"],
        "scores": str(scores_path),
    }
    code = EXIT_FAILURE if evaluation.scores["decision"] == "fail" else EXIT_OK
    return code, _emit(payload, args.json)


# -------------------------------------------------------------------- optimize


def command_optimize(args: argparse.Namespace) -> tuple[int, str]:
    plan = _load_json(Path(args.plan))
    scores = _load_json(Path(args.scores))
    rewrites = _load_json(Path(args.rewrites)) if args.rewrites else {}
    if not isinstance(rewrites, dict):
        return EXIT_USAGE, _emit({"ok": False, "error": "rewrites must be a JSON object"}, args.json)

    outcome = optimizer.plan_next_round(
        current_plan=plan,
        evaluation=scores,
        rewrites=rewrites,
        retry_unchanged=set(args.retry_unchanged or []),
    )
    if outcome.errors:
        payload = {
            "ok": False,
            "errors": [
                {"code": error.code, "message": error.message, "item_id": error.item_id}
                for error in outcome.errors
            ],
        }
        return EXIT_FAILURE, _emit(payload, args.json)

    if outcome.complete:
        payload = {"ok": True, "complete": True, "carried_forward": list(outcome.carried_forward)}
        return EXIT_OK, _emit(payload, args.json)

    assert outcome.next_plan is not None
    Path(args.out).write_text(
        json.dumps(outcome.next_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    payload = {
        "ok": True,
        "complete": False,
        "round": outcome.next_plan["round"],
        "rework": list(outcome.rework),
        "carried_forward": list(outcome.carried_forward),
        "plan": str(args.out),
    }
    return EXIT_OK, _emit(payload, args.json)


# ---------------------------------------------------------------------- status


def command_status(args: argparse.Namespace) -> tuple[int, str]:
    try:
        payload = job_ledger.load_ledger(Path(args.job))
    except job_ledger.LedgerCorruptError as error:
        return EXIT_FAILURE, _emit({"ok": False, "error": str(error)}, args.json)
    report = {
        "ok": True,
        "job_id": payload["job_id"],
        "state": payload["state"],
        "revision": payload["revision"],
        "error_category": payload["error_category"],
        "usage_limit": payload["usage_limit"],
        "items": payload["items"],
    }
    return EXIT_OK, _emit(report, args.json)


# ------------------------------------------------------------------------ wiring


def command_prompt_search(args: argparse.Namespace) -> tuple[int, str]:
    return EXIT_OK, _emit(prompt_library.search(args.query, args.limit), args.json)


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--codex-home", default=None)
    shared.add_argument("--codex-bin", default=None)
    shared.add_argument("--generation-dir", default=None)
    shared.add_argument("--destination", default="image-factory-out")
    shared.add_argument("--json", action="store_true")

    parser = argparse.ArgumentParser(prog="image-factory", parents=[shared])
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("probe", parents=[shared])
    search = subparsers.add_parser("prompt-search", parents=[shared])
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=3)

    validate = subparsers.add_parser("validate-plan", parents=[shared])
    validate.add_argument("plan")

    quote = subparsers.add_parser("quote", parents=[shared])
    quote.add_argument("plan")

    run = subparsers.add_parser("run", parents=[shared])
    run.add_argument("--plan", required=True)
    run.add_argument("--job", required=True)
    run.add_argument("--approve", action="store_true")
    run.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)

    evaluate = subparsers.add_parser("evaluate", parents=[shared])
    evaluate.add_argument("--plan", required=True)
    evaluate.add_argument("--job", required=True)
    evaluate.add_argument("--scores", required=True)
    evaluate.add_argument("--advisory", default=None)
    evaluate.add_argument("--labels", default=None)

    optimize = subparsers.add_parser("optimize", parents=[shared])
    optimize.add_argument("--plan", required=True)
    optimize.add_argument("--scores", required=True)
    optimize.add_argument("--out", required=True)
    optimize.add_argument("--rewrites", default=None)
    optimize.add_argument("--retry-unchanged", action="append", default=None)

    status = subparsers.add_parser("status", parents=[shared])
    status.add_argument("--job", required=True)

    return parser


HANDLERS = {
    "prompt-search": command_prompt_search,
    "probe": command_probe,
    "validate-plan": command_validate_plan,
    "quote": command_quote,
    "run": command_run,
    "evaluate": command_evaluate,
    "optimize": command_optimize,
    "status": command_status,
}


def run_cli(argv: list[str]) -> tuple[int, str]:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:  # argparse exits on bad usage
        return EXIT_USAGE, f"invalid arguments ({error.code})"
    handler = HANDLERS[args.command]
    try:
        return handler(args)
    except (OSError, ValueError, KeyError) as error:
        return EXIT_FAILURE, _emit({"ok": False, "error": str(error)}, args.json)


def main(argv: list[str] | None = None) -> int:
    code, output = run_cli(list(sys.argv[1:] if argv is None else argv))
    stream = sys.stdout if code == EXIT_OK else sys.stderr
    if output:
        stream.write(output + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
