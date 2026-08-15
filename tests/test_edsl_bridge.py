from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tommy.edsl_bridge import _parse_json_object, fetch_human_transcript
from tommy.errors import TommyError


def test_parse_review_from_plain_or_fenced_json() -> None:
    value = {"outcome": "advanced", "criteria": []}
    assert _parse_json_object(json.dumps(value)) == value
    assert _parse_json_object("```json\n" + json.dumps(value) + "\n```") == value


def test_fetch_normalizes_interviewer_and_respondent(monkeypatch, tmp_path: Path) -> None:
    class Git:
        def save(self, path: str, message: str):
            Path(path).write_text(message)

    class Responses:
        git = Git()

        def to_dict(self):
            return {
                "data": [
                    {
                        "answer": {
                            "sales_roleplay": [
                                {"role": "interviewer", "message": "Walk me through the ROI."},
                                {"role": "respondent", "message": "Let me start with your current queue."},
                            ]
                        }
                    }
                ]
            }

    class Coop:
        def get_human_survey_responses(self, uuid: str):
            assert uuid == "survey-1"
            return Responses()

    monkeypatch.setattr("tommy.edsl_bridge.edsl_module", lambda: SimpleNamespace(Coop=Coop))
    turns, metadata = fetch_human_transcript("survey-1", tmp_path / "responses.ep")
    assert [turn["role"] for turn in turns] == ["buyer", "seller"]
    assert metadata["response_count"] == 1


def test_fetch_rejects_unavailable_response_index(monkeypatch, tmp_path: Path) -> None:
    class Responses:
        def to_dict(self):
            return {"answer": {"sales_roleplay": [{"role": "interviewer", "text": "Hello"}]}}

    class Coop:
        def get_human_survey_responses(self, uuid: str):
            return Responses()

    monkeypatch.setattr("tommy.edsl_bridge.edsl_module", lambda: SimpleNamespace(Coop=Coop))
    with pytest.raises(TommyError, match="index 2"):
        fetch_human_transcript("survey-1", tmp_path / "responses.ep", 2)
