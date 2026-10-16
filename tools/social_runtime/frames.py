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

from tools.layout_labels import VOCABULARY_VERSION, LabelError, check_labels, computed_content


FRAMES_VERSION = "1.0"
FRAMES_FILE = "frames.json"
# Owner-set text limits that replace the estimates; regenerating definitions keeps them.
LIMITS_FILE = "text-limits.json"
LIMIT_FIELDS = {"max_lines", "max_chars"}
# Owner labels (purpose, content, tone) merged into each frame; regenerating definitions keeps them.
LABELS_FILE = "layout-labels.json"
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
# A photo area may follow its photo's shape: its height becomes the photo's, kept between these.
FLUID_FIELDS = {"min_height", "max_height"}
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


def build_frame_definitions(catalog: dict, *, logo_label: str, limits: dict | None = None,
                            labels: dict | None = None) -> dict:
    """Derive frame definitions from a scaffold frame catalog, applying owner-set text limits and labels."""
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
                    **({"fluid": rules["fluid"][slot["slot"]]} if slot["slot"] in rules.get("fluid", {}) else {}),
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
    if labels:
        unknown = sorted(set(labels) - set(frames))
        missing = sorted(set(frames) - set(labels))
        if unknown:
            raise FrameError(f"{LABELS_FILE} labels {', '.join(unknown)}, which the scaffold does not have")
        if missing:
            raise FrameError(f"{LABELS_FILE} has no labels for {', '.join(missing)}; every layout needs them")
        for frame_id, frame in frames.items():
            frame["labels"] = _check_frame_labels(frame_id, frame, labels[frame_id], LABELS_FILE)
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
    labeled = [frame_id for frame_id, frame in frames.items() if "labels" in frame]
    if labeled and len(labeled) != len(frames):
        raise FrameError(f"Frame definitions label some layouts but not {', '.join(sorted(set(frames) - set(labeled)))}")
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


def load_layout_labels(path: Path | str) -> dict:
    """Read a project's owner labels: layout id to purpose, content, and tone. No file means no labels yet."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        layouts = data["layouts"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise FrameError(f"Invalid {LABELS_FILE}: {err}") from err
    if data.get("vocabulary") != VOCABULARY_VERSION:
        raise FrameError(f"{LABELS_FILE} must use vocabulary {VOCABULARY_VERSION}")
    if not isinstance(layouts, dict) or not layouts:
        raise FrameError(f"{LABELS_FILE} must label at least one layout")
    return layouts


def frame_content(frame: dict) -> list[str]:
    """The content values a frame's image areas decide: its photo count and any outlet logo area."""
    areas = frame["image_slots"]
    return computed_content(sum(area["fit"] == "cover" for area in areas),
                            any(area["fit"] == "contain" for area in areas))


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
    if not isinstance(frame, dict) or set(frame) - {"labels"} != FRAME_FIELDS:
        raise FrameError(f"{label} must define exactly: {', '.join(sorted(FRAME_FIELDS))}, and may add labels")
    canvas = frame["canvas"]
    if not isinstance(canvas, dict) or set(canvas) != {"width", "height"} or not all(_positive_int(v) for v in canvas.values()):
        raise FrameError(f"{label} canvas must give positive integer width and height")
    images = frame["image_slots"]
    if not isinstance(images, list):
        raise FrameError(f"{label} image_slots must be an array")
    for slot in images:
        if not isinstance(slot, dict) or set(slot) - {"fluid"} != IMAGE_SLOT_FIELDS:
            raise FrameError(f"{label} image slots must define exactly: {', '.join(sorted(IMAGE_SLOT_FIELDS))}, and may add fluid")
        fluid = slot.get("fluid")
        if fluid is not None and (not isinstance(fluid, dict) or set(fluid) != FLUID_FIELDS
                                  or not all(_positive_int(v) for v in fluid.values())
                                  or fluid["min_height"] > fluid["max_height"] or slot.get("fit") != "cover"):
            raise FrameError(f"{label} image slot '{slot.get('slot')}' fluid must give min_height <= max_height on a cover area")
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
    if "labels" in frame and _check_frame_labels(frame_id, frame, frame["labels"], FRAMES_FILE) != frame["labels"]:
        raise FrameError(f"{label} labels must list content in vocabulary order; re-run the frames command")


def _check_frame_labels(frame_id: str, frame: dict, labels: object, source: str) -> dict:
    try:
        return check_labels(labels, frame_content(frame), f"{source} {frame_id}")
    except LabelError as err:
        raise FrameError(str(err)) from err


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0
