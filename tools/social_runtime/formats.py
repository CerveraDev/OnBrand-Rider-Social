"""Pinned platform-format sidecar: dimensions, slide limits, and text limits as data."""

from __future__ import annotations

import json
from pathlib import Path
import re


FORMATS_PATH = Path(__file__).with_name("platform-formats.json")
FORMATS_VERSION = "1.0"
KINDS = ("post", "carousel")
FORMAT_FIELDS = {
    "kind", "aspect_ratio", "width", "height", "min_slides", "max_slides",
    "safe_area", "text_limits", "max_file_bytes", "verified_date", "source",
}
TEXT_LIMIT_SURFACES = ("caption", "hashtags", "alt-text")


class FormatError(ValueError):
    """Raised when the format sidecar is malformed or a format is not pinned."""


def load_formats(path: Path | str = FORMATS_PATH) -> dict:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise FormatError(f"Invalid platform format JSON: {err}") from err
    if not isinstance(data, dict) or data.get("schema_version") != FORMATS_VERSION:
        raise FormatError(f"Platform format sidecar schema_version must be {FORMATS_VERSION}")
    for field in ("sidecar_version", "platform"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise FormatError(f"Platform format sidecar field '{field}' must be a non-empty string")
    formats = data.get("formats")
    if not isinstance(formats, dict) or not formats:
        raise FormatError("Platform format sidecar must pin at least one format")
    for format_id, entry in formats.items():
        _validate_format(format_id, entry)
    return data


def require_format(sidecar: dict, format_id: str) -> dict:
    """Return the pinned format, failing rather than falling back to a default."""
    entry = sidecar["formats"].get(format_id)
    if entry is None:
        raise FormatError(
            f"Format '{format_id}' is not pinned in platform format sidecar "
            f"{sidecar['sidecar_version']}; pinned formats: {', '.join(sorted(sidecar['formats']))}"
        )
    return entry


def _validate_format(format_id: str, entry: object) -> None:
    label = f"format '{format_id}'"
    if not isinstance(entry, dict) or set(entry) != FORMAT_FIELDS:
        raise FormatError(f"{label} must define exactly: {', '.join(sorted(FORMAT_FIELDS))}")
    if entry["kind"] not in KINDS:
        raise FormatError(f"{label} kind must be one of {', '.join(KINDS)}")
    ratio = entry["aspect_ratio"]
    if not isinstance(ratio, list) or len(ratio) != 2 or not all(_positive_int(v) for v in ratio):
        raise FormatError(f"{label} aspect_ratio must be two positive integers")
    for field in ("width", "height", "min_slides", "max_slides", "max_file_bytes"):
        if not _positive_int(entry[field]):
            raise FormatError(f"{label} {field} must be a positive integer")
    if entry["width"] * ratio[1] != entry["height"] * ratio[0]:
        raise FormatError(f"{label} pixel dimensions do not match its aspect ratio")
    if entry["min_slides"] > entry["max_slides"]:
        raise FormatError(f"{label} min_slides exceeds max_slides")
    safe = entry["safe_area"]
    if not isinstance(safe, dict) or set(safe) != {"top", "right", "bottom", "left"} or any(
        type(v) is not int or v < 0 for v in safe.values()
    ):
        raise FormatError(f"{label} safe_area must give non-negative top/right/bottom/left insets")
    limits = entry["text_limits"]
    if not isinstance(limits, dict) or set(limits) != set(TEXT_LIMIT_SURFACES) or not all(
        _positive_int(v) for v in limits.values()
    ):
        raise FormatError(f"{label} text_limits must give {', '.join(TEXT_LIMIT_SURFACES)}")
    verified = entry["verified_date"]
    if verified is not None and (
        not isinstance(verified, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified)
    ):
        raise FormatError(f"{label} verified_date must be null or YYYY-MM-DD")
    if verified is not None and (not isinstance(entry["source"], str) or not entry["source"]):
        raise FormatError(f"{label} is marked verified but records no source")


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0
