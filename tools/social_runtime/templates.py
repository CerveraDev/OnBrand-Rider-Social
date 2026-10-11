"""Social composition templates: frame sequences stored as project data.

A template says which scaffold frames may appear at each position of a post or
carousel. The frames themselves, with their image areas and text slots, live in
the project's frame definitions.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from .frames import FRAME_ID_RE, FRAMES_FILE, load_frames


TEMPLATE_VERSION = "2.0"
AUDIENCES = ("in-house", "outside-broker")
SLIDE_ROLES = ("opener", "feature", "detail", "proof", "call-to-action", "closer")
TEMPLATE_FIELDS = {
    "schema_version", "code", "label", "kind", "formats", "approval_status",
    "audiences", "image_sources", "min_slides", "max_slides", "sequence",
}
IMAGE_SOURCES = ("approved", "user-supplied")
STEP_FIELDS = {"role", "min", "max", "frames"}


class TemplateError(ValueError):
    """Raised when a social template is malformed, unknown, or does not fit a spec."""


def load_template(templates_dir: Path | str, code: str) -> dict:
    """Return the template with the definitions of its frames attached."""
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}-\d{2}", code):
        raise TemplateError(f"Invalid social template code: {code!r}")
    path = Path(templates_dir) / f"{code}.json"
    if not path.is_file():
        raise TemplateError(f"Unknown social template: {code}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise TemplateError(f"Invalid social template JSON ({code}): {err}") from err
    template = validate_template(data, code=code)
    frames = load_frames(Path(templates_dir) / FRAMES_FILE)["frames"]
    wanted = {frame for step in template["sequence"] for frame in step["frames"]}
    unknown = sorted(wanted - set(frames))
    if unknown:
        raise TemplateError(f"template {code} names undefined frame(s): {', '.join(unknown)}")
    return {**template, "frame_definitions": {frame: frames[frame] for frame in sorted(wanted)}}


def validate_template(data: object, *, code: str) -> dict:
    label = f"template {code}"
    if not isinstance(data, dict) or set(data) != TEMPLATE_FIELDS:
        raise TemplateError(f"{label} must define exactly: {', '.join(sorted(TEMPLATE_FIELDS))}")
    if data["schema_version"] != TEMPLATE_VERSION:
        raise TemplateError(f"{label} schema_version must be {TEMPLATE_VERSION}")
    if data["code"] != code:
        raise TemplateError(f"{label} declares a different code: {data['code']!r}")
    if not isinstance(data["label"], str) or not data["label"]:
        raise TemplateError(f"{label} label must be a non-empty string")
    if data["kind"] not in ("post", "carousel"):
        raise TemplateError(f"{label} kind must be post or carousel")
    if data["approval_status"] not in ("draft", "approved"):
        raise TemplateError(f"{label} approval_status must be draft or approved")
    for field, allowed in (("formats", None), ("audiences", AUDIENCES), ("image_sources", IMAGE_SOURCES)):
        values = data[field]
        if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
            raise TemplateError(f"{label} {field} must be a non-empty string array")
        if allowed and set(values) - set(allowed):
            raise TemplateError(f"{label} {field} has unknown value(s)")
    sequence = data["sequence"]
    if not isinstance(sequence, list) or not sequence:
        raise TemplateError(f"{label} sequence must be a non-empty array")
    for index, step in enumerate(sequence):
        _validate_step(step, f"{label} sequence[{index}]")
    low = sum(step["min"] for step in sequence)
    high = sum(step["max"] for step in sequence)
    for field in ("min_slides", "max_slides"):
        if type(data[field]) is not int or data[field] < 1:
            raise TemplateError(f"{label} {field} must be a positive integer")
    if not low <= data["min_slides"] <= data["max_slides"] <= high:
        raise TemplateError(f"{label} slide limits are not satisfiable by its sequence")
    return data


def match_slides(template: dict, slides: list[dict]) -> list[dict]:
    """Return the resolved frame governing each slide, or fail with the first mismatch.

    Each returned step carries the slide's role and frame id plus that frame's
    `images`, text `slots`, `locked` content, optional `marks`, and `canvas`.
    """
    code = template["code"]
    if not template["min_slides"] <= len(slides) <= template["max_slides"]:
        raise TemplateError(
            f"Template {code} takes {template['min_slides']}-{template['max_slides']} slides; "
            f"got {len(slides)}"
        )
    steps = []
    position = 0
    for step in template["sequence"]:
        count = 0
        while position < len(slides) and slides[position]["role"] == step["role"] and count < step["max"]:
            frame_id = slides[position]["frame"]
            if frame_id not in step["frames"]:
                raise TemplateError(
                    f"Template {code} does not allow frame '{frame_id}' for role '{step['role']}' "
                    f"at slide {position + 1}; allowed: {', '.join(step['frames'])}"
                )
            frame = template["frame_definitions"][frame_id]
            steps.append({
                "role": step["role"], "frame": frame_id, "canvas": frame["canvas"],
                "images": frame["image_slots"], "slots": frame["text_slots"], "locked": frame["locked"],
                "marks": frame["optional_marks"],
            })
            position += 1
            count += 1
        if count < step["min"]:
            found = slides[position]["role"] if position < len(slides) else "end of slides"
            raise TemplateError(
                f"Template {code} expects role '{step['role']}' at slide {position + 1}; found {found}"
            )
    if position != len(slides):
        raise TemplateError(
            f"Template {code} has no place for role '{slides[position]['role']}' at slide {position + 1}"
        )
    return steps


def _validate_step(step: object, label: str) -> None:
    if not isinstance(step, dict) or set(step) != STEP_FIELDS:
        raise TemplateError(f"{label} must define exactly: {', '.join(sorted(STEP_FIELDS))}")
    if step["role"] not in SLIDE_ROLES:
        raise TemplateError(f"{label} role must be one of {', '.join(SLIDE_ROLES)}")
    if type(step["min"]) is not int or type(step["max"]) is not int or not 0 <= step["min"] <= step["max"] or step["max"] < 1:
        raise TemplateError(f"{label} min/max must satisfy 0 <= min <= max and max >= 1")
    frames = step["frames"]
    if not isinstance(frames, list) or not frames or any(
        not isinstance(frame, str) or not FRAME_ID_RE.fullmatch(frame) for frame in frames
    ) or len(set(frames)) != len(frames):
        raise TemplateError(f"{label} frames must be a non-empty array of unique frame ids")
