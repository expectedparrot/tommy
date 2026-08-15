from __future__ import annotations

import json
from pathlib import Path

from tommy.cli import main

EXAMPLE = Path(__file__).parents[1] / "examples" / "enterprise-pricing"


def result(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_agent_next_can_start_without_a_project(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["agent", "next"]) == 0
    data = result(capsys)["data"]
    action = data["recommended_action"]
    assert action["id"] == "initialize_project"
    assert action["argv"] == ["tommy", "init", "PROJECT_DIRECTORY", "--name", "PROJECT_NAME"]
    assert action["cwd"] == str(tmp_path)
    assert set(action["unresolved_inputs"]) == {"PROJECT_DIRECTORY", "PROJECT_NAME"}
    assert action["requires_user_approval"] is False
    assert data["ready"] is False
    assert data["blockers"][0]["code"] == "INPUT_REQUIRED"


def test_agent_next_guides_component_construction(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "practice"
    main(["init", str(project)])
    result(capsys)
    monkeypatch.chdir(project)
    assert main(["agent", "next"]) == 0
    action = result(capsys)["data"]["recommended_action"]
    assert action["id"] == "create_scorecard"
    assert action["argv"][:3] == ["tommy", "scorecard", "create"]
    assert action["expected_transition"]
    assert isinstance(action["mutates_local_state"], bool)
    assert isinstance(action["requires_network"], bool)
    assert isinstance(action["spends_money"], bool)


def test_agent_next_reaches_practice_preparation(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "practice"
    main(["init", str(project)])
    result(capsys)
    monkeypatch.chdir(project)
    for kind in ("scorecard", "template", "deal"):
        main([kind, "add", str(EXAMPLE / f"{kind}.json")])
        result(capsys)
    assert main(["agent", "next"]) == 0
    action = result(capsys)["data"]["recommended_action"]
    assert action["id"] == "prepare_practice"
    assert action["argv"] == [
        "tommy",
        "practice",
        "prepare",
        "--template",
        "enterprise-pricing",
        "--deal",
        "acme-research",
        "--id",
        "PRACTICE_ID",
    ]
    assert set(action["unresolved_inputs"]) == {"PRACTICE_ID"}


def test_top_level_next_is_agent_alias(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["next"]) == 0
    data = result(capsys)["data"]
    assert data["alias_for"] == "tommy agent next"
    assert data["recommended_action"]["id"] == "initialize_project"
