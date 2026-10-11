"""Frame definitions: one slide layout per scaffold frame, derived from the frame catalog.

A frame names its image areas, its text slots, and its locked content. Templates
sequence frames. Every image area cover-fits its image by owner decision, whatever
background sizing the scaffold happens to use. Definitions are generated from the project's scaffold catalog and
committed, so a build never reads the scaffold itself.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re


FRAMES_VERSION = "1.0"
FRAMES_FILE = "frames.json"
# Owner-set text limits that replace the estimates; regenerating definitions keeps them.
LIMITS_FILE = "text-limits.json"
LIMIT_FIELDS = {"max_lines", "max_chars"}
FRAME_ID_RE = re.compile(r"[A-Z]{2}-\d{2}")
SHAPES = ("landscape", "portrait", "square")
# A contain-fitted area, such as another organisation's logo, takes an image of any shape.
ANY_SHAPE = "any"
FITS = ("cover", "contain")
# The widest a contain-fitted logo may grow from its left edge, in canvas pixels.
CONTAIN_MAX_WIDTH = 220
TEXT_CHANNELS = ("on-image-text", "slide-text")
FRAME_FIELDS = {"family", "canvas", "image_slots", "text_slots", "locked", "optional_marks"}
IMAGE_SLOT_FIELDS = {"slot", "width", "height", "shape", "fit", "required"}
TEXT_SLOT_FIELDS = {"channel", "required", "max_lines", "max_chars", "italic_accent"}
# Average glyph advance as a share of font size, used only to estimate draft limits.
GLYPH_ADVANCE = {
    ("sans", True): 0.62, ("sans", False): 0.50,
    ("serif", True): 0.66, ("serif", False): 0.50,
}
SERIF_FAMILIES = ("Playfair Display",)
LIMIT_BASIS = (
    "Estimated from each slot's rendered line count, available width, and font size in the "
    "scaffold, except where the project's text-limits.json sets an owner-decided limit. "
    "Estimates are draft pending owner review."
)


class FrameError(ValueError):
    """Raised when frame definitions are malformed or out of date."""


def build_frame_definitions(catalog: dict, *, logo_label: str, limits: dict | None = None) -> dict:
    """Derive frame definitions from a scaffold frame catalog, applying owner-set text limits."""
    frames = {}
    for entry in catalog["frames"]:
        observed = entry["observed"]
        rules = entry.get("rules", {"locked": [], "optional": []})
        text_slots = {}
        locked = {"logo": logo_label} if observed["logo"] else {}
        for slot in observed["text_slots"]:
            if slot["slot"] in rules["locked"]:
                locked[slot["slot"]] = " ".join(slot["sample"])
                continue
            max_chars = _estimate_max_chars(slot)
            text_slots[slot["slot"]] = {
                "channel": "on-image-text",
                "required": slot["slot"] not in rules["optional"],
                "max_lines": slot["rendered_lines"],
                "max_chars": max(max_chars, sum(len(line) for line in slot["sample"]) + len(slot["sample"]) - 1),
                "italic_accent": slot["italic_accent"],
            }
        frames[entry["id"]] = {
            "family": entry["family"],
            "canvas": {"width": entry["canvas"]["width"], "height": entry["canvas"]["height"]},
            "image_slots": [
                {
                    "slot": slot["slot"],
                    "width": CONTAIN_MAX_WIDTH if slot.get("element") == "img" else slot["box"]["width"],
                    "height": slot["box"]["height"],
                    "shape": slot["shape"],
                    "fit": "contain" if slot.get("element") == "img" else "cover",
                    "required": slot["slot"] not in rules["optional"],
                }
                for slot in observed["image_slots"]
            ],
            "text_slots": text_slots,
            "locked": locked,
            # Fixed marks, such as a small logo on the photo, that a post may leave out.
            "optional_marks": [mark["slot"] for mark in observed.get("marks", []) if mark["slot"] in rules["optional"]],
        }
    for frame_id, slots in (limits or {}).items():
        for slot, rule in slots.items():
            if slot not in frames.get(frame_id, {}).get("text_slots", {}):
                raise FrameError(f"{LIMITS_FILE} sets a limit for '{slot}' on {frame_id}, which has no such text slot")
            frames[frame_id]["text_slots"][slot].update(rule)
    return {
        "schema_version": FRAMES_VERSION,
        "generated_from": {
            "scaffold_html_sha256": catalog["files"]["scaffold.html"]["sha256"],
            "scaffold_css_sha256": catalog["files"]["scaffold.css"]["sha256"],
        },
        "limit_basis": LIMIT_BASIS,
        "frames": frames,
    }


def load_frames(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FrameError(f"Frame definitions are missing: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise FrameError(f"Invalid frame definition JSON: {err}") from err
    if not isinstance(data, dict) or data.get("schema_version") != FRAMES_VERSION:
        raise FrameError(f"Frame definitions schema_version must be {FRAMES_VERSION}")
    frames = data.get("frames")
    if not isinstance(frames, dict) or not frames:
        raise FrameError("Frame definitions must define at least one frame")
    for frame_id, frame in frames.items():
        _validate_frame(frame_id, frame)
    return data


def load_text_limits(path: Path | str) -> dict:
    """Read a project's owner-set text limits: frame id to slot to max_lines and/or max_chars."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        frames = json.loads(path.read_text(encoding="utf-8"))["frames"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise FrameError(f"Invalid {LIMITS_FILE}: {err}") from err
    for frame_id, slots in frames.items():
        for slot, rule in slots.items():
            if not rule or set(rule) - LIMIT_FIELDS or not all(_positive_int(value) for value in rule.values()):
                raise FrameError(f"{LIMITS_FILE}: '{slot}' on {frame_id} takes positive integer max_lines and/or max_chars")
    return frames


def catalog_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _estimate_max_chars(slot: dict) -> int:
    font_size = float(slot["font_size"].removesuffix("px"))
    spacing = 0.0 if slot["letter_spacing"] == "normal" else float(slot["letter_spacing"].removesuffix("px"))
    family = "serif" if slot["font_family"] in SERIF_FAMILIES else "sans"
    advance = font_size * GLYPH_ADVANCE[(family, slot["text_transform"] == "uppercase")] + spacing
    return slot["rendered_lines"] * math.floor(slot["available_width"] / advance)


def _validate_frame(frame_id: str, frame: object) -> None:
    label = f"frame {frame_id}"
    if not FRAME_ID_RE.fullmatch(frame_id):
        raise FrameError(f"Invalid frame id: {frame_id!r}")
    if not isinstance(frame, dict) or set(frame) != FRAME_FIELDS:
        raise FrameError(f"{label} must define exactly: {', '.join(sorted(FRAME_FIELDS))}")
    canvas = frame["canvas"]
    if not isinstance(canvas, dict) or set(canvas) != {"width", "height"} or not all(_positive_int(v) for v in canvas.values()):
        raise FrameError(f"{label} canvas must give positive integer width and height")
    images = frame["image_slots"]
    if not isinstance(images, list):
        raise FrameError(f"{label} image_slots must be an array")
    for slot in images:
        if not isinstance(slot, dict) or set(slot) != IMAGE_SLOT_FIELDS:
            raise FrameError(f"{label} image slots must define exactly: {', '.join(sorted(IMAGE_SLOT_FIELDS))}")
        if not isinstance(slot["slot"], str) or not slot["slot"] or slot["shape"] not in SHAPES + (ANY_SHAPE,):
            raise FrameError(f"{label} image slot has an invalid name or shape")
        if type(slot["required"]) is not bool or (slot["shape"] == ANY_SHAPE) != (slot["fit"] == "contain"):
            raise FrameError(f"{label} image slot '{slot['slot']}' has an invalid required flag or fit for its shape")
        if slot["fit"] not in FITS or not _positive_int(slot["width"]) or not _positive_int(slot["height"]):
            raise FrameError(f"{label} image slot '{slot['slot']}' has an invalid fit or size")
    names = [slot["slot"] for slot in images]
    if len(set(names)) != len(names):
        raise FrameError(f"{label} image slot names must be unique")
    slots = frame["text_slots"]
    if not isinstance(slots, dict):
        raise FrameError(f"{label} text_slots must be an object")
    for name, slot in slots.items():
        if not isinstance(slot, dict) or set(slot) != TEXT_SLOT_FIELDS:
            raise FrameError(f"{label} text slot '{name}' must define exactly: {', '.join(sorted(TEXT_SLOT_FIELDS))}")
        if slot["channel"] not in TEXT_CHANNELS or type(slot["required"]) is not bool or type(slot["italic_accent"]) is not bool:
            raise FrameError(f"{label} text slot '{name}' has an invalid channel or flag")
        if not _positive_int(slot["max_lines"]) or not _positive_int(slot["max_chars"]):
            raise FrameError(f"{label} text slot '{name}' limits must be positive integers")
    marks = frame["optional_marks"]
    if not isinstance(marks, list) or any(not isinstance(mark, str) or not mark for mark in marks):
        raise FrameError(f"{label} optional_marks must be an array of names")
    locked = frame["locked"]
    if not isinstance(locked, dict) or any(
        not isinstance(v, str) or not v for v in locked.values()
    ) or set(locked) & set(slots):
        raise FrameError(f"{label} locked must map names distinct from text slots to non-empty strings")


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0
