from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import TommyError
from .report import generate_report
from .store import Store, now, read_json, write_json
from .workflows import (
    build_practice,
    compare_attempts,
    import_artifact,
    import_attempt,
    prepare_drill,
    prepare_practice,
    record_fetched_attempt,
    register_review,
    register_review_value,
)


def emit(
    command: str,
    data: dict[str, Any] | None = None,
    *,
    warnings: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    warnings = warnings or []
    return {
        "schema_version": 1,
        "status": "warning" if warnings else "ok",
        "command": command,
        "data": data or {},
        "warnings": warnings,
        "errors": [],
        "next_steps": next_steps or [],
    }


def cmd_guide(_: argparse.Namespace) -> dict[str, Any]:
    return emit(
        "tommy guide",
        {
            "lifecycle": ["template", "optional deal", "practice", "attempt", "review", "report", "drill"],
            "workflow": [
                "tommy init <path>",
                "tommy scorecard add <scorecard.json>",
                "tommy template add <template.json>",
                "tommy deal add <deal.json>  # optional",
                "tommy practice prepare --template <id> [--deal <id>] --id <id>",
                "tommy practice build --practice <id>",
                "tommy practice preview --practice <id>",
                "tommy practice deploy --practice <id> --confirm",
                "tommy attempt fetch --practice <id> --uuid <uuid> --rep <name> --id <id>",
                "tommy attempt import --practice <id> --transcript <file> --rep <name> --id <id>",
                "tommy review prepare --attempt <id> --model <model>",
                "ep run --jobs <review.jobs.ep> --output <review.results.ep>",
                "tommy review register --attempt <id> --results <review.results.ep>",
                "tommy report --attempt <id>",
                "tommy drill prepare --attempt <id> --id <drill-id>",
                "tommy compare --attempt <id> --attempt <id>",
            ],
            "boundaries": {
                "preview": "Read-only preview; no respondent study is launched.",
                "deploy": "Creates a private Expected Parrot respondent study and requires --confirm.",
                "review": "Prepare creates Jobs; `ep run` performs visible model inference; register imports Results.",
            },
        },
    )


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.path).resolve()
    Store(root).initialize(args.name or root.name)
    return emit(
        "tommy init",
        {"project": str(root), "marker": str(root / "tommy.json")},
        next_steps=[f"cd {root}", "tommy guide"],
    )


def cmd_add(args: argparse.Namespace) -> dict[str, Any]:
    result = import_artifact(Store.open(), args.kind, Path(args.file), args.id)
    return emit(f"tommy {args.kind[:-1]} add", result)


def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    values = Store.open().list(args.kind)
    summary = [{key: item.get(key) for key in ("id", "name", "call_type", "created_at")} for item in values]
    return emit(f"tommy {args.kind[:-1]} list", {args.kind: summary, "count": len(summary)})


def parse_overrides(args: argparse.Namespace) -> dict[str, Any]:
    value: dict[str, Any] = {}
    if args.overrides:
        raw = read_json(Path(args.overrides))
        if not isinstance(raw, dict):
            raise TommyError("invalid_override", "Overrides file must contain a JSON object.")
        value.update(raw)
    for key in ("mode", "duration_minutes", "difficulty", "opening", "buyer_name", "buyer_role"):
        item = getattr(args, key, None)
        if item is not None:
            value[key] = item
    if args.focus:
        value["focus"] = args.focus
    return value


def cmd_practice_prepare(args: argparse.Namespace) -> dict[str, Any]:
    data = prepare_practice(Store.open(), args.id, args.template, args.deal, parse_overrides(args))
    return emit("tommy practice prepare", data, next_steps=[f"tommy practice build --practice {data['id']}"])


def cmd_practice_build(args: argparse.Namespace) -> dict[str, Any]:
    from .edsl_bridge import save_survey

    store = Store.open()
    manifest = build_practice(store, args.practice)
    practice = store.get("practices", args.practice)
    template = store.get("templates", practice["template_id"])
    guide = Path(manifest["guide"]).read_text(encoding="utf-8")
    survey = store.base / "practices" / practice["id"] / "survey.ep"
    save_survey(practice, template, guide, survey)
    manifest["survey"] = str(survey)
    write_json(store.base / "practices" / practice["id"] / "build.json", manifest)
    return emit(
        "tommy practice build", manifest, next_steps=[f"tommy practice preview --practice {practice['id']}"]
    )


def built_context(store: Store, practice_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    practice = store.get("practices", practice_id)
    template = store.get("templates", practice["template_id"])
    guide = store.base / "practices" / practice["id"] / "buyer-guide.md"
    if not guide.exists():
        raise TommyError(
            "build_required",
            "Practice has not been built.",
            hint=f"Run `tommy practice build --practice {practice_id}`.",
        )
    return practice, template, guide.read_text(encoding="utf-8")


def cmd_preview(args: argparse.Namespace) -> dict[str, Any]:
    from .edsl_bridge import preview

    practice, template, guide = built_context(Store.open(), args.practice)
    return emit(
        "tommy practice preview",
        {
            "practice_id": practice["id"],
            "preview_url": preview(practice, template, guide),
            "external_state_created": False,
        },
    )


def cmd_deploy(args: argparse.Namespace) -> dict[str, Any]:
    from .edsl_bridge import deploy

    if not args.confirm:
        raise TommyError(
            "confirmation_required",
            "Deployment creates an external respondent study.",
            hint="Review the preview, then re-run with --confirm.",
        )
    store = Store.open()
    practice, template, guide = built_context(store, args.practice)
    info = deploy(practice, template, guide)
    uuid = str(info.get("uuid") or info.get("human_survey_uuid") or "unknown")
    record = {
        "practice_id": practice["id"],
        "uuid": uuid,
        "respondent_url": info.get("respondent_url"),
        "deployed_at": now(),
        "raw": info,
    }
    path = store.base / "practices" / practice["id"] / "deployments" / f"{uuid}.json"
    write_json(path, record)
    return emit(
        "tommy practice deploy",
        {**record, "record": str(path)},
        next_steps=[f"Share {record['respondent_url']}"],
    )


def cmd_attempt_import(args: argparse.Namespace) -> dict[str, Any]:
    data = import_attempt(Store.open(), args.id, args.practice, Path(args.transcript), args.rep, args.buyer)
    return emit(
        "tommy attempt import",
        data,
        next_steps=[
            f"tommy review prepare --attempt {data['id']} --model <model>",
        ],
    )


def cmd_attempt_fetch(args: argparse.Namespace) -> dict[str, Any]:
    from .edsl_bridge import fetch_human_transcript

    store = Store.open()
    responses_path = store.base / "attempts" / args.id / "responses.ep"
    turns, metadata = fetch_human_transcript(args.uuid, responses_path, args.response_index)
    data = record_fetched_attempt(
        store,
        args.id,
        args.practice,
        turns,
        args.rep,
        args.buyer,
        args.uuid,
        responses_path,
        args.response_index,
    )
    data.update(
        {
            "uuid": args.uuid,
            "response_index": args.response_index,
            "available_responses": metadata["response_count"],
            "responses": str(responses_path),
        }
    )
    return emit(
        "tommy attempt fetch",
        data,
        next_steps=[f"tommy review prepare --attempt {data['id']} --model <model>"],
    )


def cmd_review_prepare(args: argparse.Namespace) -> dict[str, Any]:
    from .edsl_bridge import build_review_jobs

    store = Store.open()
    attempt = store.get("attempts", args.attempt)
    practice = store.get("practices", attempt["practice_id"])
    scorecard = store.get("scorecards", practice["scorecard_id"])
    base = store.base / "attempts" / attempt["id"]
    output = Path(args.output).resolve() if args.output else base / "review.jobs.ep"
    details = build_review_jobs(attempt, scorecard, args.model, args.service, output)
    expected = output.with_name(output.name.replace(".jobs.ep", ".results.ep"))
    command = f"ep run --jobs {output} --output {expected}"
    manifest = {
        "attempt_id": attempt["id"],
        "jobs": str(output),
        "expected_results": str(expected),
        "run_command": command,
        "prepared_at": now(),
        **details,
    }
    write_json(base / "review-job.json", manifest)
    return emit(
        "tommy review prepare",
        manifest,
        next_steps=[
            "Obtain approval before paid inference.",
            command,
            f"tommy review register --attempt {attempt['id']} --results {expected}",
        ],
    )


def cmd_review_register(args: argparse.Namespace) -> dict[str, Any]:
    store = Store.open()
    if args.results:
        from .edsl_bridge import review_from_results

        source = Path(args.results).resolve()
        data = register_review_value(store, args.attempt, review_from_results(source), str(source))
    else:
        data = register_review(store, args.attempt, Path(args.file))
    return emit("tommy review register", data, next_steps=[f"tommy report --attempt {args.attempt}"])


def cmd_report(args: argparse.Namespace) -> dict[str, Any]:
    data = generate_report(Store.open(), args.attempt, Path(args.output) if args.output else None)
    return emit("tommy report", data, next_steps=[f"Open {data['report']}"])


def cmd_drill_prepare(args: argparse.Namespace) -> dict[str, Any]:
    data = prepare_drill(Store.open(), args.attempt, args.id, args.criterion)
    return emit("tommy drill prepare", data, next_steps=[f"tommy practice build --practice {data['id']}"])


def cmd_compare(args: argparse.Namespace) -> dict[str, Any]:
    return emit("tommy compare", compare_attempts(Store.open(), args.attempt))


def cmd_status(_: argparse.Namespace) -> dict[str, Any]:
    store = Store.open()
    practices = []
    for practice in store.list("practices"):
        base = store.base / "practices" / practice["id"]
        practices.append(
            {
                "id": practice["id"],
                "kind": practice.get("kind", "practice"),
                "built": (base / "build.json").exists(),
                "deployment_count": len(list((base / "deployments").glob("*.json"))),
            }
        )
    attempts = []
    for attempt in store.list("attempts"):
        base = store.base / "attempts" / attempt["id"]
        attempts.append(
            {
                "id": attempt["id"],
                "practice_id": attempt["practice_id"],
                "review_prepared": (base / "review-job.json").exists(),
                "reviewed": (base / "review.json").exists(),
                "reported": (base / "report.html").exists(),
            }
        )
    return emit("tommy status", {"practices": practices, "attempts": attempts})


def cmd_next(_: argparse.Namespace) -> dict[str, Any]:
    store = Store.open()
    exists = {
        kind: len(store.list(kind)) for kind in ("scorecards", "templates", "deals", "practices", "attempts")
    }
    if not exists["scorecards"]:
        stage, recommendation = "empty", "tommy scorecard add <scorecard.json>"
    elif not exists["templates"]:
        stage, recommendation = "scorecard-ready", "tommy template add <template.json>"
    elif not exists["practices"]:
        stage, recommendation = "template-ready", "tommy practice prepare --template <id> --id <id>"
    elif not exists["attempts"]:
        stage, recommendation = "practice-ready", "tommy practice build --practice <id>"
    else:
        attempts = store.list("attempts")
        unreviewed = [a for a in attempts if not (store.base / "attempts" / a["id"] / "review.json").exists()]
        unreported = [
            a
            for a in attempts
            if (store.base / "attempts" / a["id"] / "review.json").exists()
            and not (store.base / "attempts" / a["id"] / "report.html").exists()
        ]
        if unreviewed:
            stage, recommendation = (
                "attempt-awaiting-review",
                f"tommy review prepare --attempt {unreviewed[0]['id']} --model <model>",
            )
        elif unreported:
            stage, recommendation = "reviewed", f"tommy report --attempt {unreported[0]['id']}"
        else:
            stage, recommendation = (
                "complete",
                f"tommy drill prepare --attempt {attempts[-1]['id']} --id <drill-id>",
            )
    return emit(
        "tommy next",
        {"stage": stage, "counts": exists, "recommendation": recommendation},
        next_steps=[recommendation],
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tommy")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("guide").set_defaults(func=cmd_guide)
    q = sub.add_parser("init")
    q.add_argument("path")
    q.add_argument("--name")
    q.set_defaults(func=cmd_init)
    for singular, kind in (("scorecard", "scorecards"), ("template", "templates"), ("deal", "deals")):
        group = sub.add_parser(singular).add_subparsers(dest=f"{singular}_command", required=True)
        q = group.add_parser("add")
        q.add_argument("file")
        q.add_argument("--id")
        q.set_defaults(func=cmd_add, kind=kind)
        q = group.add_parser("list")
        q.set_defaults(func=cmd_list, kind=kind)
    practice = sub.add_parser("practice").add_subparsers(dest="practice_command", required=True)
    q = practice.add_parser("prepare")
    q.add_argument("--template", required=True)
    q.add_argument("--deal")
    q.add_argument("--id", required=True)
    q.add_argument("--overrides")
    q.add_argument("--mode", choices=["voice", "text"])
    q.add_argument("--duration-minutes", type=int)
    q.add_argument("--difficulty")
    q.add_argument("--opening")
    q.add_argument("--focus", action="append")
    q.add_argument("--buyer-name")
    q.add_argument("--buyer-role")
    q.set_defaults(func=cmd_practice_prepare)
    for name, func in (("build", cmd_practice_build), ("preview", cmd_preview), ("deploy", cmd_deploy)):
        q = practice.add_parser(name)
        q.add_argument("--practice", required=True)
        if name == "deploy":
            q.add_argument("--confirm", action="store_true")
        q.set_defaults(func=func)
    attempt = sub.add_parser("attempt").add_subparsers(dest="attempt_command", required=True)
    q = attempt.add_parser("fetch")
    q.add_argument("--practice", required=True)
    q.add_argument("--uuid", required=True)
    q.add_argument("--response-index", type=int, default=0)
    q.add_argument("--rep", required=True)
    q.add_argument("--buyer", required=True)
    q.add_argument("--id", required=True)
    q.set_defaults(func=cmd_attempt_fetch)
    q = attempt.add_parser("import")
    q.add_argument("--practice", required=True)
    q.add_argument("--transcript", required=True)
    q.add_argument("--rep", required=True)
    q.add_argument("--buyer")
    q.add_argument("--id", required=True)
    q.set_defaults(func=cmd_attempt_import)
    review = sub.add_parser("review").add_subparsers(dest="review_command", required=True)
    q = review.add_parser("prepare")
    q.add_argument("--attempt", required=True)
    q.add_argument("--model", required=True)
    q.add_argument("--service")
    q.add_argument("--output")
    q.set_defaults(func=cmd_review_prepare)
    q = review.add_parser("register")
    q.add_argument("--attempt", required=True)
    source = q.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--results")
    q.set_defaults(func=cmd_review_register)
    q = sub.add_parser("report")
    q.add_argument("--attempt", required=True)
    q.add_argument("--output")
    q.set_defaults(func=cmd_report)
    drill = sub.add_parser("drill").add_subparsers(dest="drill_command", required=True)
    q = drill.add_parser("prepare")
    q.add_argument("--attempt", required=True)
    q.add_argument("--id", required=True)
    q.add_argument("--criterion")
    q.set_defaults(func=cmd_drill_prepare)
    q = sub.add_parser("compare")
    q.add_argument("--attempt", action="append", required=True)
    q.set_defaults(func=cmd_compare)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("next").set_defaults(func=cmd_next)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result, code = args.func(args), 0
    except TommyError as exc:
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.hint:
            error["hint"] = exc.hint
        if exc.context:
            error["context"] = exc.context
        result = {
            "schema_version": 1,
            "status": "error",
            "command": "tommy " + " ".join((argv or sys.argv[1:])[:2]),
            "data": {},
            "warnings": [],
            "errors": [error],
            "next_steps": [],
        }
        code = 1
    except (OSError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": 1,
            "status": "error",
            "command": "tommy",
            "data": {},
            "warnings": [],
            "errors": [{"code": "io_error", "message": str(exc)}],
            "next_steps": [],
        }
        code = 1
    except Exception as exc:  # noqa: BLE001 - preserve the one-envelope CLI contract
        result = {
            "schema_version": 1,
            "status": "error",
            "command": "tommy",
            "data": {},
            "warnings": [],
            "errors": [{"code": "unexpected_error", "message": str(exc)}],
            "next_steps": [],
        }
        code = 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
