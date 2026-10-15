"""AI-generated images: which layouts take them, and the record each one carries.

A project opts in with `social/generated-images.json`, an owner decision naming
the layouts that do not take a generated image; every other layout does. Without
the file no layout takes one. A generated image is a local file checked like a
supplied one, and is always recorded with the prompt and tool that made it, one of
`ALLOWED_TOOLS`, so a package never presents it as approved project imagery or as
a person's own photo.
"""

from __future__ import annotations

import json
from pathlib import Path

from .frames import FRAME_ID_RE


POLICY_FILE = "generated-images.json"
RECORD_FIELDS = {"file", "prompt", "tool"}
# Catalog images the generation started from, by exact file name.
RECORD_OPTIONAL = {"based_on"}
# Owner decision: the only image generators the skill may use, as recorded in 'tool'.
ALLOWED_TOOLS = ("Codex ImageGen",)


class GeneratedImageError(ValueError):
    """Raised when a generated image is not allowed where it is used or lacks its record."""


def load_policy(project_dir: Path | str) -> frozenset[str] | None:
    """Return the layouts that refuse generated images, or None when the project takes none at all."""
    path = Path(project_dir) / "social" / POLICY_FILE
    if not path.is_file():
        return None
    try:
        excluded = json.loads(path.read_text(encoding="utf-8"))["excluded_layouts"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise GeneratedImageError(f"Invalid {POLICY_FILE}: {err}") from err
    if not isinstance(excluded, list) or any(
        not isinstance(layout, str) or not FRAME_ID_RE.fullmatch(layout) for layout in excluded
    ):
        raise GeneratedImageError(f"{POLICY_FILE}: excluded_layouts must be an array of layout ids")
    return frozenset(excluded)


def accepts(excluded: frozenset[str] | None, layout: str) -> bool:
    return excluded is not None and layout not in excluded


def record_problem(record: object) -> str | None:
    """Say what is wrong with a generated-image record, or None when it is complete."""
    if not isinstance(record, dict) or not RECORD_FIELDS <= set(record) or set(record) - RECORD_FIELDS - RECORD_OPTIONAL:
        return "needs 'file', 'prompt', and 'tool', and may add 'based_on'"
    if any(not isinstance(record[field], str) or not record[field].strip() for field in RECORD_FIELDS):
        return "'file', 'prompt', and 'tool' must be non-empty text"
    if record["tool"].strip().casefold() not in {tool.casefold() for tool in ALLOWED_TOOLS}:
        return f"'tool' must be one of: {', '.join(ALLOWED_TOOLS)}; images from any other tool are not accepted"
    based_on = record.get("based_on", [])
    if not isinstance(based_on, list) or any(not isinstance(name, str) or not name for name in based_on):
        return "'based_on' must be a list of catalog file names"
    return None
