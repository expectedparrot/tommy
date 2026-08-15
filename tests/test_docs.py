from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_documentation_is_self_contained_and_complete() -> None:
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert (ROOT / "docs/assets/tommy-artwork.png").exists()
    assert 'src="assets/tommy-artwork.png"' in page
    assert 'class="language-bash"' in page
    assert 'class="language-json"' in page
    assert "<details>" in page and "Show JSON" in page
    assert "voice interview AI" in page
    assert "--output-dir runs/" in page
    assert "--jobs .tommy" not in page
    assert "tommy scorecard create" in page
    assert "tommy template add-objection" in page
    assert "We are making up the IDs" in page
    assert "ep-practice" in page and "directory name we chose" in page
    assert "tommy practice instructions" in page
    assert "exact guide the sales target will follow" in page
    for command in (
        "tommy init",
        "tommy practice prepare",
        "tommy practice build",
        "tommy practice instructions",
        "tommy practice preview",
        "tommy practice deploy",
        "tommy attempt fetch",
        "tommy attempt import",
        "tommy review prepare",
        "tommy review register",
        "tommy report",
        "tommy drill prepare",
        "tommy compare",
    ):
        assert command in page
    assert "http://" not in page
    assert "https://github.com/expectedparrot/tommy#copyable-agent-instructions" in page
