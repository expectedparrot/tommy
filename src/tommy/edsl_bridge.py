from __future__ import annotations

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
