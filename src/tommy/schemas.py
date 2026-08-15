from __future__ import annotations

from typing import Any

from .errors import TommyError


def require(value: dict[str, Any], fields: tuple[str, ...], artifact: str) -> None:
    missing = [field for field in fields if value.get(field) in (None, "", [])]
    if missing:
        raise TommyError("invalid_artifact", f"{artifact} is missing required fields: {', '.join(missing)}")


def validate_scorecard(value: dict[str, Any]) -> None:
    require(value, ("name", "groups"), "Scorecard")
    if not isinstance(value["groups"], list) or not value["groups"]:
        raise TommyError("invalid_scorecard", "Scorecard `groups` must be a non-empty list.")
    seen: set[str] = set()
    for group in value["groups"]:
        require(group, ("id", "name", "criteria"), "Scorecard group")
        for criterion in group["criteria"]:
            require(criterion, ("id", "name", "description", "max_score"), "Scorecard criterion")
            if criterion["id"] in seen:
                raise TommyError("invalid_scorecard", f"Duplicate criterion id: {criterion['id']}")
            seen.add(criterion["id"])
            if not isinstance(criterion["max_score"], int) or criterion["max_score"] < 1:
                raise TommyError(
                    "invalid_scorecard", f"Criterion `{criterion['id']}` needs a positive integer max_score."
                )


def validate_template(value: dict[str, Any]) -> None:
    require(value, ("name", "call_type", "buyer", "objections", "success_condition", "scorecard"), "Template")
    require(value["buyer"], ("role", "behavior"), "Template buyer")
    if not isinstance(value["objections"], list) or not value["objections"]:
        raise TommyError("invalid_template", "Template requires at least one objection.")


def validate_deal(value: dict[str, Any]) -> None:
    require(value, ("name", "seller", "prospect", "deal"), "Deal")
    require(value["seller"], ("company", "offering"), "Deal seller")
    require(value["prospect"], ("company",), "Deal prospect")


def validate_review(value: dict[str, Any], scorecard: dict[str, Any]) -> None:
    require(value, ("outcome", "recommendations", "strengths", "criteria", "objections"), "Review")
    expected = {c["id"]: c for g in scorecard["groups"] for c in g["criteria"]}
    actual = {c.get("criterion_id"): c for c in value["criteria"]}
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise TommyError("invalid_review", f"Review is missing scorecard criteria: {', '.join(missing)}")
    for identifier, item in actual.items():
        if identifier not in expected:
            raise TommyError("invalid_review", f"Unknown review criterion: {identifier}")
        score = item.get("score")
        if not isinstance(score, (int, float)) or not 0 <= score <= expected[identifier]["max_score"]:
            raise TommyError("invalid_review", f"Invalid score for `{identifier}`.")
        for evidence in item.get("evidence", []):
            if not isinstance(evidence.get("turn_id"), str):
                raise TommyError("invalid_review", f"Evidence for `{identifier}` requires a string turn_id.")
