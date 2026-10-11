"""Crop and reframe provenance. Sources stay unmodified; a crop is a derived output.

This module validates provenance for a crop produced elsewhere. It does not crop
pixels and does not score subject preservation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from .assets import CROP_ROLE, SocialAssetError, resolve_social_asset


CROP_FIELDS = {"id", "source_asset", "format", "source_dimensions", "geometry", "focal_point", "approval_status"}
CROP_STATUSES = ("planned", "approved")
ASPECT_TOLERANCE = 0.005


class CropError(ValueError):
    """Raised when a derived crop's provenance is incomplete or does not verify."""


def validate_crop(crop: dict, *, assets: list[dict], format_id: str, target: dict, max_file_bytes: int,
                  base_dir: Path, mode: str) -> dict:
    """Validate one crop against `target`, the export-pixel size of the image slot it fills."""
    label = f"crop '{crop.get('id')}'"
    if not isinstance(crop.get("id"), str) or not crop["id"]:
        raise CropError("Every crop needs a non-empty id")
    unknown = sorted(set(crop) - CROP_FIELDS - {"output"})
    missing = sorted(CROP_FIELDS - set(crop))
    if unknown or missing:
        raise CropError(f"{label} fields: missing={missing}, unknown={unknown}")
    if crop["format"] != format_id:
        raise CropError(f"{label} was made for format '{crop['format']}', not '{format_id}'")
    try:
        source = resolve_social_asset(assets, crop["source_asset"], role=CROP_ROLE)
    except SocialAssetError as err:
        raise CropError(f"{label} source rejected: {err}") from err

    source_w, source_h = _size(crop["source_dimensions"], f"{label}.source_dimensions")
    geometry = crop["geometry"]
    if not isinstance(geometry, dict) or set(geometry) != {"x", "y", "width", "height"} or any(
        type(v) is not int or v < 0 for v in geometry.values()
    ) or not geometry["width"] or not geometry["height"]:
        raise CropError(f"{label}.geometry must give non-negative integer x, y, width, height")
    if geometry["x"] + geometry["width"] > source_w or geometry["y"] + geometry["height"] > source_h:
        raise CropError(f"{label}.geometry extends outside the declared source dimensions")
    size = f"{target['width']}x{target['height']}"
    if abs(geometry["width"] / geometry["height"] - target["width"] / target["height"]) > ASPECT_TOLERANCE:
        raise CropError(f"{label}.geometry does not match the {size} '{target['slot']}' slot")
    focal = crop["focal_point"]
    if not isinstance(focal, dict) or set(focal) != {"x", "y"} or any(type(v) is not int for v in focal.values()):
        raise CropError(f"{label}.focal_point must give integer source-pixel x and y")
    if not (geometry["x"] <= focal["x"] <= geometry["x"] + geometry["width"]
            and geometry["y"] <= focal["y"] <= geometry["y"] + geometry["height"]):
        raise CropError(f"{label}.focal_point lies outside the crop geometry")

    status = crop["approval_status"]
    if status not in CROP_STATUSES:
        raise CropError(f"{label}.approval_status must be one of {', '.join(CROP_STATUSES)}")
    record = {
        "id": crop["id"],
        "source_asset": source["filename"],
        "source_public_url": source["public_url"],
        "format": format_id,
        "source_dimensions": {"width": source_w, "height": source_h},
        "geometry": dict(geometry),
        "focal_point": dict(focal),
        "target": dict(target),
        "upscaled": geometry["width"] < target["width"],
        "approval_status": status,
        "output": None,
    }
    if status == "planned":
        if mode != "composition-preview":
            raise CropError(f"{label} is only planned; {mode} requires an approved crop with output")
        if "output" in crop:
            raise CropError(f"{label} is planned and must not declare output")
        return record

    output = crop.get("output")
    if not isinstance(output, dict) or set(output) != {"src", "sha256", "width", "height"}:
        raise CropError(f"{label}.output must give src, sha256, width, height")
    path = (base_dir / output["src"]).resolve() if isinstance(output["src"], str) else None
    if path is None or not path.is_file():
        raise CropError(f"{label}.output file is missing")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != output["sha256"]:
        raise CropError(f"{label}.output checksum does not match the local file")
    actual = image_dimensions(data)
    if actual != (output["width"], output["height"]):
        raise CropError(f"{label}.output dimensions do not match the local file")
    if actual != (target["width"], target["height"]):
        raise CropError(
            f"{label}.output is {actual[0]}x{actual[1]}; the '{target['slot']}' slot requires {size}"
        )
    if len(data) > max_file_bytes:
        raise CropError(f"{label}.output exceeds the {format_id} file-size ceiling")
    record["output"] = {
        "path": path, "name": f"{crop['id']}{path.suffix.lower()}", "sha256": digest,
        "width": actual[0], "height": actual[1], "bytes": len(data),
    }
    return record


def image_dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            length = int.from_bytes(data[index : index + 2], "big")
            if length < 2 or index + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[index + 3 : index + 5], "big")
                width = int.from_bytes(data[index + 5 : index + 7], "big")
                return width, height
            index += length
    raise CropError("Unsupported or unreadable image; use PNG or JPEG")


def _size(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, dict) or set(value) != {"width", "height"} or any(
        type(v) is not int or v < 1 for v in value.values()
    ):
        raise CropError(f"{label} must give positive integer width and height")
    return value["width"], value["height"]
