"""Images supplied by the person building a post, outside the approved catalog.

Event photography has no shared filing system, so a template may let a slide take
a local file directly. The file is checked for format and orientation, copied into
the package under a content-derived name, and recorded as user-supplied. It is
never treated as an owner-approved record.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .crops import CropError, image_dimensions


SHAPE_TOLERANCE = 0.05
SUFFIXES = {b"\x89PNG": ".png", b"\xff\xd8": ".jpg"}


class SuppliedImageError(ValueError):
    """Raised when a user-supplied image is missing, unreadable, or the wrong shape."""


def load_supplied_image(reference: str, *, base_dir: Path, slot: dict) -> dict:
    """Read one supplied image and check that its orientation fits the image slot."""
    path = Path(reference).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    path = path.resolve()
    label = f"Supplied image '{path.name}'"
    if not path.is_file():
        raise SuppliedImageError(f"{label} was not found")
    data = path.read_bytes()
    try:
        width, height = image_dimensions(data)
    except CropError as err:
        raise SuppliedImageError(f"{label} is not a readable PNG or JPEG") from err
    if _exif_orientation(data) in (5, 6, 7, 8):
        width, height = height, width
    shape = image_shape(width, height)
    if slot["shape"] != "any" and shape != slot["shape"]:
        raise SuppliedImageError(
            f"{label} is {shape} ({width}x{height}) and cannot fill the {slot['shape']} '{slot['slot']}' slot"
        )
    digest = hashlib.sha256(data).hexdigest()
    suffix = next(value for magic, value in SUFFIXES.items() if data.startswith(magic))
    return {
        "path": path, "name": f"supplied-{digest[:12]}{suffix}", "source_name": path.name,
        "sha256": digest, "width": width, "height": height, "bytes": len(data),
    }


def image_shape(width: int, height: int) -> str:
    ratio = width / height
    if ratio > 1 + SHAPE_TOLERANCE:
        return "landscape"
    if ratio < 1 - SHAPE_TOLERANCE:
        return "portrait"
    return "square"


def _exif_orientation(data: bytes) -> int:
    """Return the JPEG EXIF orientation tag, or 1 when absent. Phone photos rely on it."""
    if not data.startswith(b"\xff\xd8"):
        return 1
    index = 2
    while index + 4 <= len(data) and data[index] == 0xFF:
        marker = data[index + 1]
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        segment = data[index + 4 : index + 2 + length]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            return _tiff_orientation(segment[6:])
        if marker == 0xDA or length < 2:
            break
        index += 2 + length
    return 1


def _tiff_orientation(tiff: bytes) -> int:
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return 1
    order = "little" if tiff[:2] == b"II" else "big"
    offset = int.from_bytes(tiff[4:8], order)
    if offset + 2 > len(tiff):
        return 1
    for entry in range(int.from_bytes(tiff[offset : offset + 2], order)):
        start = offset + 2 + entry * 12
        if start + 12 > len(tiff):
            break
        if int.from_bytes(tiff[start : start + 2], order) == 0x0112:
            value = int.from_bytes(tiff[start + 8 : start + 10], order)
            return value if 1 <= value <= 8 else 1
    return 1
