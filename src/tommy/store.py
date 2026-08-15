from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import TommyError

DIRECTORIES = ("templates", "deals", "practices", "attempts", "scorecards")


def now() -> str:
    return datetime.now(UTC).isoformat()


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not result:
        raise TommyError("invalid_id", "The value does not produce a usable identifier.")
    return result


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def read_json(path: Path) -> Any:
    if not path.exists():
        raise TommyError("not_found", f"Artifact not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TommyError("invalid_json", f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "tommy.json").exists():
            return candidate
    raise TommyError("project_not_found", "No Tommy project found.", hint="Run `tommy init PATH`.")


def resolve_output_dir(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not value.strip() or ".." in path.parts:
        raise TommyError(
            "invalid_output_dir",
            "Output directory must be a named path beneath the current working directory.",
        )
    current = Path.cwd().resolve()
    target = (current / path).resolve()
    if target == current or not target.is_relative_to(current):
        raise TommyError(
            "invalid_output_dir",
            "Export into a named output directory beneath the current working directory.",
        )
    target.mkdir(parents=True, exist_ok=True)
    return target


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.base = self.root / ".tommy"

    @classmethod
    def open(cls) -> Store:
        return cls(find_root())

    def initialize(self, name: str) -> None:
        marker = self.root / "tommy.json"
        if marker.exists():
            raise TommyError("already_exists", f"A Tommy project already exists at {self.root}.")
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in DIRECTORIES:
            (self.base / directory).mkdir(parents=True, exist_ok=True)
        write_json(marker, {"schema_version": 1, "project_id": slug(name), "name": name, "created_at": now()})

    def path(self, kind: str, identifier: str) -> Path:
        return self.base / kind / f"{slug(identifier)}.json"

    def add(self, kind: str, identifier: str, value: dict[str, Any]) -> Path:
        path = self.path(kind, identifier)
        if path.exists():
            raise TommyError("already_exists", f"{kind.rstrip('s').title()} `{identifier}` already exists.")
        write_json(path, value)
        return path

    def get(self, kind: str, identifier: str) -> dict[str, Any]:
        value = read_json(self.path(kind, identifier))
        if not isinstance(value, dict):
            raise TommyError("invalid_artifact", f"Expected an object in {self.path(kind, identifier)}.")
        return value

    def list(self, kind: str) -> list[dict[str, Any]]:
        return [read_json(path) for path in sorted((self.base / kind).glob("*.json"))]
