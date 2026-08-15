from __future__ import annotations

import json
from pathlib import Path

from tommy.cli import main

EXAMPLE = Path(__file__).parents[1] / "examples" / "enterprise-pricing"


def output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def setup_project(tmp_path: Path, monkeypatch, capsys, *, with_deal: bool = True) -> Path:
    project = tmp_path / "project"
    assert main(["init", str(project), "--name", "Training"]) == 0
    output(capsys)
    monkeypatch.chdir(project)
    assert main(["scorecard", "add", str(EXAMPLE / "scorecard.json")]) == 0
    output(capsys)
    assert main(["template", "add", str(EXAMPLE / "template.json")]) == 0
    output(capsys)
    if with_deal:
        assert main(["deal", "add", str(EXAMPLE / "deal.json")]) == 0
        output(capsys)
    return project


def test_deal_specific_attempt_review_and_report(tmp_path: Path, monkeypatch, capsys) -> None:
    project = setup_project(tmp_path, monkeypatch, capsys)
    assert (
        main(
            [
                "practice",
                "prepare",
                "--template",
                "enterprise-pricing",
                "--deal",
                "acme-research",
                "--id",
                "jordan-pricing",
                "--focus",
                "validity",
            ]
        )
        == 0
    )
    practice = output(capsys)["data"]
    assert practice["deal_id"] == "acme-research"
    assert practice["settings"]["focus"] == ["validity"]

    assert (
        main(
            [
                "attempt",
                "import",
                "--practice",
                "jordan-pricing",
                "--transcript",
                str(EXAMPLE / "transcript.txt"),
                "--rep",
                "Alex Rivera",
                "--id",
                "round-1",
            ]
        )
        == 0
    )
    attempt = output(capsys)["data"]
    assert attempt["turn_count"] == 7

    assert main(["review", "register", "--attempt", "round-1", "--file", str(EXAMPLE / "review.json")]) == 0
    assert output(capsys)["data"]["evidence_references"] == 6
    assert main(["report", "--attempt", "round-1"]) == 0
    report = Path(output(capsys)["data"]["report"])
    html = report.read_text()
    assert "Recommendations from Tommy" in html
    assert 'href="#turn-006"' in html
    assert "Scorecard" in html and "Objections" in html
    assert "http://" not in html and "https://" not in html
    assert report == project / ".tommy/attempts/round-1/report.html"


def test_generic_practice_needs_no_deal(tmp_path: Path, monkeypatch, capsys) -> None:
    setup_project(tmp_path, monkeypatch, capsys, with_deal=False)
    assert (
        main(
            [
                "practice",
                "prepare",
                "--template",
                "enterprise-pricing",
                "--id",
                "generic",
                "--buyer-role",
                "Chief Financial Officer",
                "--mode",
                "text",
            ]
        )
        == 0
    )
    data = output(capsys)["data"]
    assert data["deal_id"] is None
    assert data["settings"]["buyer_role"] == "Chief Financial Officer"


def test_review_rejects_unknown_evidence(tmp_path: Path, monkeypatch, capsys) -> None:
    setup_project(tmp_path, monkeypatch, capsys)
    main(["practice", "prepare", "--template", "enterprise-pricing", "--id", "generic"])
    output(capsys)
    main(
        [
            "attempt",
            "import",
            "--practice",
            "generic",
            "--transcript",
            str(EXAMPLE / "transcript.txt"),
            "--rep",
            "Alex Rivera",
            "--id",
            "round-1",
        ]
    )
    output(capsys)
    review = json.loads((EXAMPLE / "review.json").read_text())
    review["criteria"][0]["evidence"][0]["turn_id"] = "turn-999"
    invalid = tmp_path / "invalid-review.json"
    invalid.write_text(json.dumps(review))
    assert main(["review", "register", "--attempt", "round-1", "--file", str(invalid)]) == 1
    assert output(capsys)["errors"][0]["code"] == "invalid_evidence"


def test_deploy_requires_confirmation_before_external_action(tmp_path: Path, monkeypatch, capsys) -> None:
    setup_project(tmp_path, monkeypatch, capsys, with_deal=False)
    assert main(["practice", "deploy", "--practice", "anything"]) == 1
    assert output(capsys)["errors"][0]["code"] == "confirmation_required"


def test_next_is_artifact_driven(tmp_path: Path, monkeypatch, capsys) -> None:
    project = tmp_path / "project"
    main(["init", str(project)])
    output(capsys)
    monkeypatch.chdir(project)
    assert main(["next"]) == 0
    assert output(capsys)["data"]["stage"] == "empty"
