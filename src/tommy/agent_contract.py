from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import TommyError
from .store import Store, find_root, read_json

CONTRACT_VERSION = "1.0"


def action(
    identifier: str,
    stage: str,
    cwd: Path,
    argv: list[str],
    reason: str,
    *,
    mutates: bool,
    network: bool = False,
    spends_money: bool = False,
    approval: bool = False,
    prerequisites: list[str] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    unresolved: dict[str, Any] | None = None,
    expected_transition: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "stage": stage,
        "cwd": str(cwd.resolve()),
        "argv": argv,
        "reason": reason,
        "mutates_local_state": mutates,
        "requires_network": network,
        "spends_money": spends_money,
        "requires_user_approval": approval,
        "prerequisites": prerequisites or [],
        "input_artifacts": inputs or [],
        "resulting_artifacts": outputs or [],
        "unresolved_inputs": unresolved or {},
        "expected_transition": expected_transition,
        "safety_warnings": warnings or [],
    }


def _field(description: str, *, example: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "string", "description": description}
    if example:
        value["example"] = example
    return value


def _state(store: Store) -> dict[str, Any]:
    scorecards = store.list("scorecards")
    templates = store.list("templates")
    deals = store.list("deals")
    practices = store.list("practices")
    attempts = store.list("attempts")
    return {
        "project_found": True,
        "project_root": str(store.root),
        "counts": {
            "scorecards": len(scorecards),
            "templates": len(templates),
            "deals": len(deals),
            "practices": len(practices),
            "attempts": len(attempts),
        },
        "scorecards": scorecards,
        "templates": templates,
        "deals": deals,
        "practices": practices,
        "attempts": attempts,
    }


def state_for(start: Path | None = None) -> dict[str, Any]:
    try:
        return _state(Store(find_root(start)))
    except TommyError as exc:
        if exc.code != "project_not_found":
            raise
        return {
            "project_found": False,
            "project_root": None,
            "cwd": str((start or Path.cwd()).resolve()),
            "counts": {kind: 0 for kind in ("scorecards", "templates", "deals", "practices", "attempts")},
        }


def _incomplete_scorecard(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    for scorecard in state["scorecards"]:
        if not scorecard.get("groups"):
            return scorecard, None
        for group in scorecard["groups"]:
            if not group.get("criteria"):
                return scorecard, group
    return None


def _build_record(store: Store, practice_id: str) -> dict[str, Any] | None:
    path = store.base / "practices" / practice_id / "build.json"
    return read_json(path) if path.exists() else None


def recommendation(start: Path | None = None) -> dict[str, Any]:
    state = state_for(start)
    cwd = Path(state.get("project_root") or state["cwd"])
    alternatives: list[dict[str, Any]] = []
    terminal = False
    if not state["project_found"]:
        recommended = action(
            "initialize_project",
            "setup",
            cwd,
            ["tommy", "init", "PROJECT_DIRECTORY", "--name", "PROJECT_NAME"],
            "No Tommy project is discoverable from the current directory.",
            mutates=True,
            outputs=["PROJECT_DIRECTORY/tommy.json"],
            unresolved={
                "PROJECT_DIRECTORY": _field(
                    "A new directory name chosen for this sales-practice project.", example="ep-practice"
                ),
                "PROJECT_NAME": _field(
                    "A human-readable project name.", example="Expected Parrot enterprise practice"
                ),
            },
            expected_transition="A Tommy project exists; rerun `tommy agent next` from its directory.",
        )
    elif not state["scorecards"]:
        recommended = action(
            "create_scorecard",
            "design",
            cwd,
            ["tommy", "scorecard", "create", "--id", "SCORECARD_ID", "--name", "SCORECARD_NAME"],
            "The evaluator needs a scoring standard before buyer behavior can reference it.",
            mutates=True,
            unresolved={
                "SCORECARD_ID": _field("A short stable ID chosen by the agent.", example="enterprise-call"),
                "SCORECARD_NAME": _field(
                    "A readable name for the scoring standard.", example="Enterprise sales call"
                ),
            },
            expected_transition="The scorecard exists and needs at least one group.",
        )
    elif incomplete := _incomplete_scorecard(state):
        scorecard, group = incomplete
        if group is None:
            recommended = action(
                "add_scorecard_group",
                "design",
                cwd,
                [
                    "tommy",
                    "scorecard",
                    "add-group",
                    "--scorecard",
                    scorecard["id"],
                    "--id",
                    "GROUP_ID",
                    "--name",
                    "GROUP_NAME",
                ],
                f"Scorecard `{scorecard['id']}` has no criterion groups.",
                mutates=True,
                unresolved={
                    "GROUP_ID": _field("A short stable ID chosen for this group.", example="conversation"),
                    "GROUP_NAME": _field("A readable group name.", example="Conversation"),
                },
                expected_transition="The scorecard group exists and needs a criterion.",
            )
        else:
            recommended = action(
                "add_scorecard_criterion",
                "design",
                cwd,
                [
                    "tommy",
                    "scorecard",
                    "add-criterion",
                    "--scorecard",
                    scorecard["id"],
                    "--group",
                    group["id"],
                    "--id",
                    "CRITERION_ID",
                    "--name",
                    "CRITERION_NAME",
                    "--description",
                    "CRITERION_DESCRIPTION",
                    "--max-score",
                    "MAX_SCORE",
                ],
                f"Scorecard group `{group['id']}` has no criteria and cannot yet evaluate a call.",
                mutates=True,
                unresolved={
                    "CRITERION_ID": _field(
                        "A short stable ID chosen for the criterion.", example="discovery"
                    ),
                    "CRITERION_NAME": _field("A readable criterion name.", example="Discovery"),
                    "CRITERION_DESCRIPTION": _field("Observable behavior the evaluator should score."),
                    "MAX_SCORE": {"type": "integer", "minimum": 1, "example": 2},
                },
                expected_transition="The scorecard is valid; add more criteria or create a buyer template.",
            )
    elif not state["templates"]:
        scorecard = state["scorecards"][0]
        recommended = action(
            "create_buyer_template",
            "design",
            cwd,
            [
                "tommy",
                "template",
                "create",
                "--id",
                "TEMPLATE_ID",
                "--name",
                "TEMPLATE_NAME",
                "--call-type",
                "CALL_TYPE",
                "--scorecard",
                scorecard["id"],
                "--buyer-name",
                "BUYER_NAME",
                "--buyer-role",
                "BUYER_ROLE",
                "--buyer-behavior",
                "BUYER_BEHAVIOR",
                "--success-condition",
                "SUCCESS_CONDITION",
                "--mode",
                "voice",
            ],
            "No reusable simulated-buyer behavior exists.",
            mutates=True,
            unresolved={
                "TEMPLATE_ID": _field("A stable ID chosen for this reusable buyer pattern."),
                "TEMPLATE_NAME": _field("A readable name for the buyer pattern."),
                "CALL_TYPE": _field("The sales conversation being practiced."),
                "BUYER_NAME": _field("The name the voice AI should use."),
                "BUYER_ROLE": _field("The buyer's role."),
                "BUYER_BEHAVIOR": _field("How the simulated buyer should respond and apply pressure."),
                "SUCCESS_CONDITION": _field("The bounded next step the seller must earn."),
            },
            inputs=[f".tommy/scorecards/{scorecard['id']}.json"],
            expected_transition="The buyer template exists and needs objection territory.",
        )
    elif template := next((item for item in state["templates"] if not item.get("objections")), None):
        recommended = action(
            "add_buyer_objection",
            "design",
            cwd,
            [
                "tommy",
                "template",
                "add-objection",
                "--template",
                template["id"],
                "--name",
                "OBJECTION_NAME",
                "--prompt",
                "OBJECTION_PROMPT",
            ],
            f"Template `{template['id']}` has no objection territory and cannot create a useful practice.",
            mutates=True,
            unresolved={
                "OBJECTION_NAME": _field("A short human-readable label for the concern."),
                "OBJECTION_PROMPT": _field("Instructions for how the AI buyer should raise the concern."),
            },
            expected_transition="The buyer template is valid; add more objections or supply deal context.",
        )
    elif not state["deals"] and not state["practices"]:
        template = state["templates"][0]
        recommended = action(
            "create_deal_context",
            "design",
            cwd,
            [
                "tommy",
                "deal",
                "create",
                "--id",
                "DEAL_ID",
                "--name",
                "DEAL_NAME",
                "--seller-company",
                "SELLER_COMPANY",
                "--offering",
                "OFFERING",
                "--prospect-company",
                "PROSPECT_COMPANY",
                "--stage",
                "DEAL_STAGE",
                "--objective",
                "PRACTICE_OBJECTIVE",
            ],
            "A deal brief will ground the simulated buyer in supplied facts about the upcoming call.",
            mutates=True,
            unresolved={
                "DEAL_ID": _field("A stable ID chosen for this opportunity."),
                "DEAL_NAME": _field("A readable opportunity name."),
                "SELLER_COMPANY": _field("The company the rep represents."),
                "OFFERING": _field("What the rep is selling."),
                "PROSPECT_COMPANY": _field("The prospective customer."),
                "DEAL_STAGE": _field("The current sales stage."),
                "PRACTICE_OBJECTIVE": _field("The bounded outcome the rep wants to practice earning."),
            },
            expected_transition="Deal facts exist; enrich known objections or prepare a practice.",
        )
        alternatives.append(
            action(
                "prepare_generic_practice",
                "design",
                cwd,
                ["tommy", "practice", "prepare", "--template", template["id"], "--id", "PRACTICE_ID"],
                "Use a generic practice when no real opportunity facts should be supplied.",
                mutates=True,
                unresolved={"PRACTICE_ID": _field("A stable ID chosen for this practice.")},
                expected_transition="A generic practice is prepared.",
            )
        )
    elif not state["practices"]:
        template = state["templates"][0]
        deal = state["deals"][0] if state["deals"] else None
        argv = ["tommy", "practice", "prepare", "--template", template["id"]]
        if deal:
            argv.extend(["--deal", deal["id"]])
        argv.extend(["--id", "PRACTICE_ID"])
        recommended = action(
            "prepare_practice",
            "prepare",
            cwd,
            argv,
            "The scoring standard, buyer behavior, and deal context are ready to combine.",
            mutates=True,
            unresolved={
                "PRACTICE_ID": _field("A stable ID chosen for this practice.", example="jordan-pricing")
            },
            expected_transition="A provenance-bound practice is ready to build.",
        )
    else:
        store = Store(cwd)
        practice = state["practices"][-1]
        build = _build_record(store, practice["id"])
        if not build:
            output_dir = f"runs/{practice['id']}"
            recommended = action(
                "build_practice",
                "build",
                cwd,
                ["tommy", "practice", "build", "--practice", practice["id"], "--output-dir", output_dir],
                "The prepared practice has not been compiled into buyer instructions and a native survey.",
                mutates=True,
                inputs=[f".tommy/practices/{practice['id']}.json"],
                outputs=[
                    f"{output_dir}/buyer-guide.md",
                    f"{output_dir}/survey.ep",
                    f"{output_dir}/practice-manifest.json",
                ],
                expected_transition="Runnable artifacts exist; inspect the buyer instructions before preview or deployment.",
            )
        else:
            deployments = sorted((store.base / "practices" / practice["id"] / "deployments").glob("*.json"))
            practice_attempts = [item for item in state["attempts"] if item["practice_id"] == practice["id"]]
            inspection_path = store.base / "practices" / practice["id"] / "instructions-inspected.json"
            preview_path = store.base / "practices" / practice["id"] / "preview.json"
            inspection = read_json(inspection_path) if inspection_path.exists() else None
            preview = read_json(preview_path) if preview_path.exists() else None
            inspection_current = bool(inspection and inspection.get("guide_sha256") == build["guide_sha256"])
            preview_current = bool(preview and preview.get("guide_sha256") == build["guide_sha256"])
            if not deployments:
                if not inspection_current:
                    recommended = action(
                        "inspect_buyer_instructions",
                        "review",
                        cwd,
                        ["tommy", "practice", "instructions", "--practice", practice["id"]],
                        "The exact generated instructions should be read before creating an external respondent study.",
                        mutates=True,
                        inputs=[build["guide"]],
                        outputs=[f".tommy/practices/{practice['id']}/instructions-inspected.json"],
                        expected_transition="The current guide is marked inspected; rerun agent next to obtain preview.",
                    )
                elif not preview_current:
                    recommended = action(
                        "preview_practice",
                        "preview",
                        cwd,
                        ["tommy", "practice", "preview", "--practice", practice["id"]],
                        "The inspected buyer guide has not been previewed as a voice experience.",
                        mutates=True,
                        network=True,
                        inputs=[build["guide"], build.get("survey", "")],
                        outputs=[f".tommy/practices/{practice['id']}/preview.json"],
                        expected_transition="The current guide has a preview record; request deployment approval.",
                    )
                else:
                    recommended = action(
                        "deploy_practice",
                        "deploy",
                        cwd,
                        ["tommy", "practice", "deploy", "--practice", practice["id"], "--confirm"],
                        "The current buyer instructions were inspected and previewed; deployment is the next boundary.",
                        mutates=True,
                        network=True,
                        approval=True,
                        inputs=[build["guide"], build.get("survey", ""), preview["preview_url"]],
                        expected_transition="A respondent URL exists for the sales rep.",
                        warnings=["Deployment creates external state and requires explicit user approval."],
                    )
            elif not practice_attempts:
                deployment = read_json(deployments[-1])
                recommended = action(
                    "complete_and_fetch_attempt",
                    "attempt",
                    cwd,
                    [
                        "tommy",
                        "attempt",
                        "fetch",
                        "--practice",
                        practice["id"],
                        "--uuid",
                        deployment["uuid"],
                        "--rep",
                        "REP_NAME",
                        "--buyer",
                        "BUYER_NAME",
                        "--id",
                        "ATTEMPT_ID",
                        "--output-dir",
                        "runs/ATTEMPT_ID",
                    ],
                    "The study is deployed; after the rep completes the voice call, fetch it as a preserved attempt.",
                    mutates=True,
                    network=True,
                    unresolved={
                        "REP_NAME": _field("The sales representative who completed the practice."),
                        "BUYER_NAME": _field("The displayed buyer name."),
                        "ATTEMPT_ID": _field("A unique ID for this round.", example="alex-round-1"),
                    },
                    inputs=[deployment.get("respondent_url", "")],
                    outputs=["runs/ATTEMPT_ID/responses.ep"],
                    expected_transition="The transcript is preserved and ready for evaluator-job preparation.",
                )
            else:
                attempt = practice_attempts[-1]
                base = store.base / "attempts" / attempt["id"]
                review_job = (
                    read_json(base / "review-job.json") if (base / "review-job.json").exists() else None
                )
                review = (base / "review.json").exists()
                report = (
                    read_json(base / "report-export.json") if (base / "report-export.json").exists() else None
                )
                if not review_job:
                    recommended = action(
                        "prepare_review_jobs",
                        "review",
                        cwd,
                        [
                            "tommy",
                            "review",
                            "prepare",
                            "--attempt",
                            attempt["id"],
                            "--model",
                            "MODEL",
                            "--output-dir",
                            f"runs/{attempt['id']}",
                        ],
                        "The transcript has not been packaged for scorecard evaluation.",
                        mutates=True,
                        unresolved={"MODEL": _field("The EDSL model identifier selected for evaluation.")},
                        outputs=[
                            f"runs/{attempt['id']}/review.jobs.ep",
                            f"runs/{attempt['id']}/review-manifest.json",
                        ],
                        expected_transition="Native evaluator Jobs exist; inspect cost and obtain approval before inference.",
                    )
                elif not Path(review_job["expected_results"]).exists():
                    recommended = action(
                        "run_review_inference",
                        "review",
                        cwd,
                        [
                            "ep",
                            "run",
                            "--jobs",
                            review_job["jobs"],
                            "--output",
                            review_job["expected_results"],
                        ],
                        "Evaluator Jobs exist but their Results do not.",
                        mutates=True,
                        network=True,
                        spends_money=True,
                        approval=True,
                        inputs=[review_job["jobs"]],
                        outputs=[review_job["expected_results"]],
                        expected_transition="Native Results exist and can be registered.",
                        warnings=[
                            "Show the model and estimated cost, then obtain explicit approval before paid inference."
                        ],
                    )
                elif not review:
                    recommended = action(
                        "register_review_results",
                        "review",
                        cwd,
                        [
                            "tommy",
                            "review",
                            "register",
                            "--attempt",
                            attempt["id"],
                            "--results",
                            review_job["expected_results"],
                        ],
                        "Completed evaluator Results have not been validated and registered.",
                        mutates=True,
                        inputs=[review_job["expected_results"]],
                        expected_transition="A scorecard-valid, evidence-linked review exists.",
                    )
                elif not report:
                    recommended = action(
                        "render_coaching_report",
                        "report",
                        cwd,
                        [
                            "tommy",
                            "report",
                            "--attempt",
                            attempt["id"],
                            "--output-dir",
                            f"runs/{attempt['id']}",
                        ],
                        "The registered review has not been rendered as a standalone coaching report.",
                        mutates=True,
                        inputs=[f".tommy/attempts/{attempt['id']}/review.json"],
                        outputs=[f"runs/{attempt['id']}/report.html"],
                        expected_transition="The practice round is complete and ready for coaching handoff.",
                    )
                else:
                    recommended = action(
                        "handoff_coaching",
                        "complete",
                        cwd,
                        [],
                        "The attempt, evidence-linked review, and standalone coaching report are complete.",
                        mutates=False,
                        inputs=[report["report"]],
                        expected_transition="The supervising agent presents the report and proposes a focused drill if useful.",
                    )
                    alternatives.append(
                        action(
                            "prepare_targeted_drill",
                            "drill",
                            cwd,
                            ["tommy", "drill", "prepare", "--attempt", attempt["id"], "--id", "DRILL_ID"],
                            "Turn the weakest criterion into a short follow-up practice.",
                            mutates=True,
                            unresolved={"DRILL_ID": _field("A unique ID chosen for the drill.")},
                            expected_transition="A provenance-linked drill is ready to build.",
                        )
                    )
                    terminal = True
    public_state = {
        "project_found": state["project_found"],
        "project_root": state.get("project_root"),
        "counts": state["counts"],
    }
    blockers = []
    if recommended["unresolved_inputs"]:
        blockers.append(
            {
                "code": "INPUT_REQUIRED",
                "message": "Resolve the action's structured inputs before execution.",
                "fields": sorted(recommended["unresolved_inputs"]),
            }
        )
    if recommended["requires_user_approval"]:
        blockers.append(
            {
                "code": "USER_APPROVAL_REQUIRED",
                "message": "Obtain explicit user approval before executing this action.",
            }
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "terminal": terminal,
        "ready": not blockers,
        "stage": recommended["stage"],
        "blockers": blockers,
        "state": public_state,
        "recommended_action": recommended,
        "alternative_actions": alternatives[:3],
    }


def guide() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "purpose": "Help a coding agent construct, launch, and evaluate a voice sales practice.",
        "control_loop": [
            "Run `tommy agent next`.",
            "Resolve only the returned `unresolved_inputs`, preferably from existing user context.",
            "Run the returned argv without shell interpolation.",
            "Rerun `tommy agent next` after every material mutation.",
        ],
        "rules": [
            "Treat IDs as stable labels the agent chooses; do not ask the user to invent IDs.",
            "Ask the user only for consequential missing facts, not CLI or EDSL implementation details.",
            "Keep reusable simulated-buyer behavior separate from supplied deal facts.",
            "Inspect generated buyer instructions before preview or deployment.",
            "Obtain explicit approval for deployment and paid model inference.",
            "Never pass `.tommy` paths to `ep run`; use named output directories beneath cwd.",
            "Rerun agent next instead of inferring workflow state from chat memory.",
        ],
    }
