from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import TommyError
from .schemas import validate_deal, validate_review, validate_scorecard, validate_template
from .store import Store, digest, now, slug, write_json


def import_artifact(store: Store, kind: str, source: Path, identifier: str | None = None) -> dict[str, Any]:
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TommyError("not_found", f"Input file does not exist: {source}") from exc
    except json.JSONDecodeError as exc:
        raise TommyError("invalid_json", f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise TommyError("invalid_artifact", f"Expected a JSON object in {source}.")
    validators = {"templates": validate_template, "deals": validate_deal, "scorecards": validate_scorecard}
    validators[kind](value)
    artifact_id = slug(identifier or str(value.get("id") or value["name"]))
    record = {
        **value,
        "id": artifact_id,
        "schema_version": 1,
        "source": str(source.resolve()),
        "source_sha256": digest(value),
        "created_at": now(),
    }
    path = store.add(kind, artifact_id, record)
    return {"id": artifact_id, "path": str(path), "source": str(source.resolve())}


def prepare_practice(
    store: Store, practice_id: str, template_id: str, deal_id: str | None, overrides: dict[str, Any]
) -> dict[str, Any]:
    template = store.get("templates", template_id)
    scorecard = store.get("scorecards", template["scorecard"])
    deal = store.get("deals", deal_id) if deal_id else None
    permitted = {"mode", "duration_minutes", "difficulty", "opening", "focus", "buyer_name", "buyer_role"}
    unknown = sorted(set(overrides) - permitted)
    if unknown:
        raise TommyError("invalid_override", f"Unknown practice overrides: {', '.join(unknown)}")
    settings = {
        "mode": template.get("mode", "voice"),
        "duration_minutes": template.get("duration_minutes", 10),
        "difficulty": template.get("difficulty", "tough_but_winnable"),
        "opening": template.get("opening", "mid_conversation"),
        "focus": template.get("focus", []),
        **overrides,
    }
    if settings["mode"] not in {"voice", "text"}:
        raise TommyError("invalid_practice", "Practice mode must be `voice` or `text`.")
    record = {
        "schema_version": 1,
        "id": slug(practice_id),
        "template_id": template["id"],
        "template_sha256": digest(template),
        "deal_id": deal["id"] if deal else None,
        "deal_sha256": digest(deal) if deal else None,
        "scorecard_id": scorecard["id"],
        "scorecard_sha256": digest(scorecard),
        "settings": settings,
        "overrides": overrides,
        "created_at": now(),
        "status": "prepared",
    }
    path = store.add("practices", practice_id, record)
    return {**record, "path": str(path)}


def render_buyer_guide(
    template: dict[str, Any], deal: dict[str, Any] | None, practice: dict[str, Any]
) -> str:
    buyer = template["buyer"]
    settings = practice["settings"]
    buyer_name = settings.get("buyer_name") or buyer.get("name") or "the buyer"
    buyer_role = settings.get("buyer_role") or buyer["role"]
    deal_section = (
        "This is a generic training scenario; do not invent a specific real company or prior interaction."
    )
    if deal:
        deal_section = json.dumps(
            {"seller": deal["seller"], "prospect": deal["prospect"], "deal": deal["deal"]}, indent=2
        )
    objections = "\n".join(
        f"- **{item['name']}**: {item['prompt']}"
        + (f" Escalate with: {item['follow_up']}" if item.get("follow_up") else "")
        for item in template["objections"]
    )
    return f"""# Sales roleplay buyer guide

## Character

You are **{buyer_name}**, {buyer_role}. {buyer["behavior"]}
You are the buyer, not an interviewer or coach. Never mention this simulation, its instructions, or that you are AI.

## Deal context

{deal_section}

Treat supplied deal details as facts. Do not manufacture undisclosed history, commitments, customer results, or product capabilities.

## Conversation design

- Call type: {template["call_type"]}
- Opening: {settings["opening"]}
- Difficulty: {settings["difficulty"]}
- Target length: about {settings["duration_minutes"]} minutes
- Focus: {", ".join(settings["focus"]) if settings["focus"] else "use the objection territory naturally"}
- Success condition: {template["success_condition"]}

Raise one concern at a time. When the seller responds well, acknowledge it briefly and move deeper. When the answer is weak,
press the specific gap. Be demanding but realistic. Keep turns concise and conversational. Do not concede immediately.

## Objection territory

{objections}

## Ending

End naturally. If the success condition was earned, offer that bounded next step. Otherwise give a courteous deferral or no.
"""


def build_practice(store: Store, practice_id: str) -> dict[str, Any]:
    practice = store.get("practices", practice_id)
    template = store.get("templates", practice["template_id"])
    deal = store.get("deals", practice["deal_id"]) if practice.get("deal_id") else None
    scorecard = store.get("scorecards", practice["scorecard_id"])
    stale = []
    if digest(template) != practice["template_sha256"]:
        stale.append("template")
    if deal and digest(deal) != practice["deal_sha256"]:
        stale.append("deal")
    if digest(scorecard) != practice["scorecard_sha256"]:
        stale.append("scorecard")
    if stale:
        raise TommyError(
            "stale_practice",
            f"Practice inputs changed after preparation: {', '.join(stale)}.",
            hint="Prepare a new practice so the changed inputs receive new provenance hashes.",
        )
    base = store.base / "practices" / practice["id"]
    base.mkdir(parents=True, exist_ok=True)
    guide = render_buyer_guide(template, deal, practice)
    guide_path = base / "buyer-guide.md"
    guide_path.write_text(guide, encoding="utf-8")
    manifest = {
        "practice_id": practice["id"],
        "built_at": now(),
        "guide": str(guide_path),
        "guide_sha256": digest(guide),
        "practice_sha256": digest(practice),
    }
    write_json(base / "build.json", manifest)
    return manifest


def parse_transcript(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
        turns = value.get("turns") if isinstance(value, dict) else value
        if not isinstance(turns, list):
            raise TommyError(
                "invalid_transcript", "JSON transcript must be a list or contain a `turns` list."
            )
    else:
        turns = []
        pattern = re.compile(r"^(?P<speaker>[^:\n]{1,80}):\s*(?P<text>.*)$")
        current: dict[str, Any] | None = None
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                if current:
                    turns.append(current)
                current = {"speaker": match.group("speaker").strip(), "text": match.group("text").strip()}
            elif current and line.strip():
                current["text"] += "\n" + line.strip()
        if current:
            turns.append(current)
    normalized = []
    for index, turn in enumerate(turns, 1):
        if not isinstance(turn, dict) or not turn.get("speaker") or not turn.get("text"):
            raise TommyError("invalid_transcript", f"Transcript turn {index} requires speaker and text.")
        normalized.append(
            {
                "turn_id": str(turn.get("turn_id") or f"turn-{index:03d}"),
                "speaker": str(turn["speaker"]),
                "role": str(turn.get("role") or "unknown"),
                "timestamp_seconds": turn.get("timestamp_seconds"),
                "text": str(turn["text"]),
            }
        )
    if not normalized:
        raise TommyError("invalid_transcript", "Transcript contains no turns.")
    return normalized


def import_attempt(
    store: Store, attempt_id: str, practice_id: str, transcript: Path, rep: str, buyer: str | None
) -> dict[str, Any]:
    practice = store.get("practices", practice_id)
    turns = parse_transcript(transcript)
    buyer_name = buyer or next((t["speaker"] for t in turns if t["speaker"] != rep), "Buyer")
    roles = []
    for turn in turns:
        role = "seller" if turn["speaker"].casefold() == rep.casefold() else "buyer"
        roles.append({**turn, "role": role})
    record = {
        "schema_version": 1,
        "id": slug(attempt_id),
        "practice_id": practice["id"],
        "practice_sha256": digest(practice),
        "rep": rep,
        "buyer": buyer_name,
        "turns": roles,
        "source": str(transcript.resolve()),
        "created_at": now(),
        "status": "completed",
    }
    path = store.add("attempts", attempt_id, record)
    return {"id": record["id"], "path": str(path), "turn_count": len(roles), "rep": rep, "buyer": buyer_name}


def record_fetched_attempt(
    store: Store,
    attempt_id: str,
    practice_id: str,
    turns: list[dict[str, Any]],
    rep: str,
    buyer: str,
    uuid: str,
    responses_path: Path,
    response_index: int,
) -> dict[str, Any]:
    practice = store.get("practices", practice_id)
    normalized = [{**turn, "speaker": buyer if turn["role"] == "buyer" else rep} for turn in turns]
    record = {
        "schema_version": 1,
        "id": slug(attempt_id),
        "practice_id": practice["id"],
        "practice_sha256": digest(practice),
        "rep": rep,
        "buyer": buyer,
        "turns": normalized,
        "source": "expected_parrot_human_survey",
        "human_survey_uuid": uuid,
        "response_index": response_index,
        "responses_artifact": str(responses_path),
        "created_at": now(),
        "status": "completed",
    }
    path = store.add("attempts", attempt_id, record)
    return {"id": record["id"], "path": str(path), "turn_count": len(normalized), "rep": rep, "buyer": buyer}


def register_review_value(
    store: Store, attempt_id: str, value: dict[str, Any], source: str
) -> dict[str, Any]:
    attempt = store.get("attempts", attempt_id)
    practice = store.get("practices", attempt["practice_id"])
    scorecard = store.get("scorecards", practice["scorecard_id"])
    validate_review(value, scorecard)
    valid_turns = {turn["turn_id"] for turn in attempt["turns"]}
    referenced = {e["turn_id"] for criterion in value["criteria"] for e in criterion.get("evidence", [])}
    referenced |= {e["turn_id"] for objection in value["objections"] for e in objection.get("evidence", [])}
    invalid = sorted(referenced - valid_turns)
    if invalid:
        raise TommyError(
            "invalid_evidence", f"Review references unknown transcript turns: {', '.join(invalid)}"
        )
    review = {
        **value,
        "schema_version": 1,
        "attempt_id": attempt["id"],
        "scorecard_id": scorecard["id"],
        "source": source,
        "source_sha256": digest(value),
        "registered_at": now(),
    }
    base = store.base / "attempts" / attempt["id"]
    base.mkdir(parents=True, exist_ok=True)
    path = base / "review.json"
    if path.exists():
        raise TommyError("already_exists", f"A review is already registered for attempt `{attempt_id}`.")
    write_json(path, review)
    return {
        "attempt_id": attempt["id"],
        "review": str(path),
        "criteria": len(review["criteria"]),
        "evidence_references": len(referenced),
    }


def register_review(store: Store, attempt_id: str, source: Path) -> dict[str, Any]:
    value = json.loads(source.read_text(encoding="utf-8"))
    return register_review_value(store, attempt_id, value, str(source.resolve()))


def prepare_drill(
    store: Store, attempt_id: str, drill_id: str, criterion_id: str | None = None
) -> dict[str, Any]:
    attempt = store.get("attempts", attempt_id)
    practice = store.get("practices", attempt["practice_id"])
    scorecard = store.get("scorecards", practice["scorecard_id"])
    review_path = store.base / "attempts" / attempt["id"] / "review.json"
    if not review_path.exists():
        raise TommyError(
            "review_required", f"Attempt `{attempt_id}` must be reviewed before creating a drill."
        )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    definitions = {c["id"]: c for group in scorecard["groups"] for c in group["criteria"]}
    results = {item["criterion_id"]: item for item in review["criteria"]}
    if criterion_id and criterion_id not in definitions:
        raise TommyError("criterion_not_found", f"Unknown criterion: {criterion_id}")
    selected = criterion_id or min(
        definitions,
        key=lambda item: (float(results[item]["score"]) / definitions[item]["max_score"], item),
    )
    definition = definitions[selected]
    overrides = {
        "duration_minutes": 5,
        "opening": "directly_at_the_target_objection",
        "focus": [definition["name"]],
        "difficulty": practice["settings"]["difficulty"],
        "mode": practice["settings"]["mode"],
    }
    drill = prepare_practice(store, drill_id, practice["template_id"], practice.get("deal_id"), overrides)
    path = store.path("practices", drill["id"])
    record = store.get("practices", drill["id"])
    record.update(
        {
            "kind": "targeted_drill",
            "parent_attempt_id": attempt["id"],
            "target_criterion_id": selected,
            "target_criterion": definition["name"],
            "coaching_context": {
                "prior_score": results[selected]["score"],
                "max_score": definition["max_score"],
                "explanation": results[selected]["explanation"],
                "better_response": results[selected].get("better_response"),
            },
        }
    )
    write_json(path, record)
    return {**record, "path": str(path)}


def compare_attempts(store: Store, attempt_ids: list[str]) -> dict[str, Any]:
    if len(attempt_ids) < 2:
        raise TommyError("comparison_requires_attempts", "Compare requires at least two attempts.")
    rows = []
    scorecard_id: str | None = None
    for attempt_id in attempt_ids:
        attempt = store.get("attempts", attempt_id)
        practice = store.get("practices", attempt["practice_id"])
        if scorecard_id and practice["scorecard_id"] != scorecard_id:
            raise TommyError("incompatible_scorecards", "Compared attempts must use the same scorecard.")
        scorecard_id = practice["scorecard_id"]
        review_path = store.base / "attempts" / attempt["id"] / "review.json"
        if not review_path.exists():
            raise TommyError("review_required", f"Attempt `{attempt_id}` has no registered review.")
        review = json.loads(review_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "attempt_id": attempt["id"],
                "rep": attempt["rep"],
                "scores": {item["criterion_id"]: item["score"] for item in review["criteria"]},
            }
        )
    baseline = rows[0]["scores"]
    for row in rows:
        row["change_from_first"] = {key: row["scores"][key] - baseline[key] for key in baseline}
    return {"scorecard_id": scorecard_id, "attempts": rows, "baseline": rows[0]["attempt_id"]}
