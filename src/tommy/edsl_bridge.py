from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import TommyError


def edsl_module():
    try:
        import edsl

        return edsl
    except ImportError as exc:
        raise TommyError(
            "edsl_unavailable",
            "This command requires EDSL.",
            hint="Install with `pip install 'tommy[edsl]'`.",
        ) from exc


def make_survey(practice: dict[str, Any], template: dict[str, Any], guide: str):
    edsl = edsl_module()
    question = edsl.QuestionInterview(
        question_name="sales_roleplay",
        question_text=(
            f"Practice a {template['call_type']} conversation. You are speaking with the buyer. "
            "Respond naturally and try to earn the defined next step."
        ),
        interview_guide=guide,
        max_turns=max(4, int(practice["settings"]["duration_minutes"])),
    )
    return edsl.Survey([question])


def save_survey(practice: dict[str, Any], template: dict[str, Any], guide: str, output: Path) -> None:
    edsl = edsl_module()
    output.parent.mkdir(parents=True, exist_ok=True)
    make_survey(practice, template, guide).git.save(str(output), message="Build Tommy sales roleplay")
    edsl.Survey.git.load(str(output))


def preview(practice: dict[str, Any], template: dict[str, Any], guide: str) -> str:
    schema = {"questions": {"sales_roleplay": {"interview_mode": practice["settings"]["mode"]}}}
    return str(make_survey(practice, template, guide).preview(humanize_schema=schema))


def deploy(practice: dict[str, Any], template: dict[str, Any], guide: str) -> dict[str, Any]:
    schema = {"questions": {"sales_roleplay": {"interview_mode": practice["settings"]["mode"]}}}
    return dict(
        make_survey(practice, template, guide).humanize(
            human_survey_name=f"Tommy · {template['name']}",
            humanize_schema=schema,
            survey_visibility="private",
        )
    )


def _walk_for_key(value: Any, target: str, found: list[Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) == target:
                found.append(child)
            _walk_for_key(child, target, found)
    elif isinstance(value, list):
        for child in value:
            _walk_for_key(child, target, found)


def fetch_human_transcript(
    uuid: str, output: Path, response_index: int = 0
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    edsl = edsl_module()
    responses = edsl.Coop().get_human_survey_responses(uuid)
    output.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(responses, "git"):
        responses.git.save(str(output), message=f"Register Tommy human responses for {uuid}")
    data = responses.to_dict()
    found: list[Any] = []
    _walk_for_key(data, "sales_roleplay", found)
    transcripts = [item for item in found if isinstance(item, list) and item]
    if not transcripts:
        raise TommyError(
            "transcript_not_found",
            "No `sales_roleplay` transcript was found in the human responses.",
            hint="Inspect the saved responses artifact or import an exported transcript manually.",
        )
    if response_index < 0 or response_index >= len(transcripts):
        raise TommyError(
            "response_index_out_of_range",
            f"Response index {response_index} is unavailable; found {len(transcripts)} transcript(s).",
        )
    normalized = []
    for index, turn in enumerate(transcripts[response_index], 1):
        if not isinstance(turn, dict):
            continue
        raw_role = str(turn.get("role") or turn.get("speaker") or "unknown").lower()
        role = "buyer" if raw_role in {"interviewer", "assistant", "buyer"} else "seller"
        text = turn.get("text") or turn.get("message") or turn.get("content")
        if text:
            normalized.append(
                {
                    "turn_id": str(turn.get("turn_id") or f"turn-{index:03d}"),
                    "role": role,
                    "text": str(text),
                    "timestamp_seconds": turn.get("timestamp_seconds"),
                }
            )
    if not normalized:
        raise TommyError("invalid_transcript", "The selected human response contains no usable turns.")
    return normalized, {"response_count": len(transcripts), "raw": data}


def _review_prompt(attempt: dict[str, Any], scorecard: dict[str, Any]) -> str:
    expected = {
        "outcome": "One concise, evidence-based outcome statement",
        "recommendations": ["Three highest-leverage improvements"],
        "strengths": ["Specific things that went well"],
        "criteria": [
            {
                "criterion_id": "exact id from scorecard",
                "score": 0,
                "explanation": "Observed evidence and interpretation",
                "evidence": [{"turn_id": "turn-001", "label": "Short label"}],
                "better_response": "A concrete alternative",
                "confidence": "low, medium, or high",
            }
        ],
        "objections": [
            {
                "category": "Objection category",
                "buyer_concern": "Underlying concern",
                "resolved": False,
                "assessment": "How the seller handled it",
                "evidence": [{"turn_id": "turn-001", "label": "Short label"}],
                "better_response": "A stronger talk track",
            }
        ],
    }
    return (
        "Evaluate the sales-roleplay transcript against every scorecard criterion. "
        "Return only one valid JSON object—no Markdown fence or commentary. Do not invent quotations or facts. "
        "Every evidence turn_id must exist in the transcript. Separate observed behavior from interpretation, "
        "and give appropriately calibrated confidence. Use each criterion exactly once.\n\n"
        f"SCORECARD:\n{json.dumps(scorecard, indent=2)}\n\n"
        f"REQUIRED OUTPUT SHAPE:\n{json.dumps(expected, indent=2)}\n\n"
        f"TRANSCRIPT:\n{json.dumps(attempt['turns'], indent=2)}"
    )


def build_review_jobs(
    attempt: dict[str, Any],
    scorecard: dict[str, Any],
    model_name: str,
    service_name: str | None,
    output: Path,
) -> dict[str, Any]:
    edsl = edsl_module()
    question = edsl.QuestionFreeText(
        question_name="tommy_review", question_text=_review_prompt(attempt, scorecard)
    )
    model_kwargs = {"service_name": service_name} if service_name else {}
    model = edsl.Model(model_name, **model_kwargs)
    jobs = edsl.Survey([question]).by(model)
    output.parent.mkdir(parents=True, exist_ok=True)
    jobs.git.save(str(output), message=f"Build Tommy review for {attempt['id']}")
    edsl.Jobs.git.load(str(output))
    return {"model": model_name, "service_name": service_name, "model_calls": 1}


def _parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and {"outcome", "criteria"}.issubset(value):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def review_from_results(path: Path) -> dict[str, Any]:
    edsl = edsl_module()
    results = edsl.Results.git.load(str(path))
    data = results.to_dict()
    found: list[Any] = []
    _walk_for_key(data, "tommy_review", found)
    for value in reversed(found):
        parsed = _parse_json_object(value)
        if parsed:
            return parsed
    raise TommyError(
        "review_not_found",
        "No valid structured `tommy_review` answer was found in the Results artifact.",
        hint="Inspect the raw answer for truncation or invalid JSON.",
    )
