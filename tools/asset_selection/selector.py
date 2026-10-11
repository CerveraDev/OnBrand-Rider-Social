"""Validate OnBrand master manifests and rank campaign asset candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
PDF_EXTENSIONS = {".pdf"}
REQUIRED_FIELDS = (
    "filename",
    "dropbox_id",
    "dropbox_path",
    "category",
    "approved_for",
    "public_url",
)
ARRAY_FIELDS = ("category", "approved_for")
STRING_FIELDS = ("filename", "dropbox_id", "dropbox_path", "public_url")
REVIEW_SCORE_WINDOW = 10


class ManifestError(ValueError):
    """Raised when a manifest cannot be safely consumed."""


@dataclass(frozen=True)
class SelectionNeeds:
    media_type: str = "any"
    approved_for: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    orientation: str = ""
    limit: int = 6

    def __post_init__(self):
        if self.media_type not in {"any", "image", "pdf"}:
            raise ValueError("media_type must be one of: any, image, pdf")
        if self.limit < 1:
            raise ValueError("limit must be at least 1")


def load_manifest(source):
    """Load and validate a manifest from a local JSON file."""

    source_text = str(source)
    parsed = urlparse(source_text)
    if parsed.scheme in {"http", "https"}:
        raise ManifestError(
            "HTTP(S) manifests require project configuration with a validated "
            "local cache; no safe URL/cache configuration is defined yet."
        )
    if parsed.scheme and parsed.scheme != "file":
        raise ManifestError(f"Unsupported manifest source scheme: {parsed.scheme}")

    path = Path(parsed.path if parsed.scheme == "file" else source_text).expanduser()
    if not path.exists():
        raise ManifestError(f"Manifest not found: {path}")
    if not path.is_file():
        raise ManifestError(f"Manifest source is not a file: {path}")

    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as err:
        raise ManifestError(f"Invalid JSON in {path}: {err}") from err

    return validate_manifest(raw, source=str(path))


def validate_manifest(raw, source="<manifest>"):
    if not isinstance(raw, list):
        raise ManifestError(f"{source} must contain a JSON array")

    seen_identity = {}
    filename_identities = {}
    assets = []
    for index, item in enumerate(raw):
        label = f"{source} entry {index}"
        if not isinstance(item, dict):
            raise ManifestError(f"{label} must be a JSON object")

        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            raise ManifestError(f"{label} is missing required field(s): {', '.join(missing)}")

        for field in STRING_FIELDS:
            if not isinstance(item[field], str):
                raise ManifestError(f"{label} field '{field}' must be a string")
        if not item["filename"].strip():
            raise ManifestError(f"{label} field 'filename' must not be empty")
        if not item["dropbox_path"].strip():
            raise ManifestError(f"{label} field 'dropbox_path' must not be empty")
        if not item["public_url"].strip():
            raise ManifestError(f"{label} field 'public_url' must not be empty")

        for field in ARRAY_FIELDS:
            if not isinstance(item[field], list):
                raise ManifestError(
                    f"{label} ({item['filename']}) has non-array {field}; "
                    "fix curated metadata instead of coercing it"
                )
            if any(not isinstance(value, str) for value in item[field]):
                raise ManifestError(
                    f"{label} ({item['filename']}) field '{field}' must contain only strings"
                )

        orientation = item.get("orientation", "")
        if orientation is None:
            orientation = ""
        if not isinstance(orientation, str):
            raise ManifestError(f"{label} ({item['filename']}) field 'orientation' must be a string")

        normalized = {
            "filename": item["filename"],
            "dropbox_id": item["dropbox_id"],
            "dropbox_path": item["dropbox_path"],
            "category": list(item["category"]),
            "orientation": orientation,
            "approved_for": list(item["approved_for"]),
            "public_url": item["public_url"],
            "media_type": media_type_for(item["filename"]),
            "stable_identity": stable_identity(item),
        }
        if normalized["media_type"] == "other":
            raise ManifestError(
                f"{label} ({item['filename']}) has unsupported media type; "
                "expected an image or PDF filename"
            )

        if normalized["stable_identity"] in seen_identity:
            other = seen_identity[normalized["stable_identity"]]
            raise ManifestError(
                f"{label} ({item['filename']}) duplicates stable identity from entry {other}"
            )
        seen_identity[normalized["stable_identity"]] = index
        filename_identities.setdefault(item["filename"], set()).add(normalized["stable_identity"])
        assets.append(normalized)

    for filename, identities in filename_identities.items():
        if len(identities) > 1 and any(not identity for identity in identities):
            raise ManifestError(
                f"{source} has duplicate filename '{filename}' without stable Dropbox identity/path"
            )

    return assets


def select_candidates(assets, needs):
    required_approvals = normalize_values(needs.approved_for)
    wanted_categories = normalize_values(needs.categories)
    wanted_orientation = normalize_value(needs.orientation)

    candidates = []
    excluded = []
    for asset in assets:
        exclusion = exclusion_reason(
            asset,
            media_type=needs.media_type,
            required_approvals=required_approvals,
            wanted_categories=wanted_categories,
            wanted_orientation=wanted_orientation,
        )
        if exclusion:
            excluded.append({"filename": asset["filename"], "reason": exclusion})
            continue

        score, reasons = score_asset(
            asset,
            media_type=needs.media_type,
            required_approvals=required_approvals,
            wanted_categories=wanted_categories,
            wanted_orientation=wanted_orientation,
        )
        candidates.append(candidate_record(asset, score, reasons))

    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["filename"].lower(),
            item["dropbox_path"].lower(),
            item["dropbox_id"].lower(),
        )
    )

    shortlisted = candidates[: needs.limit]
    for rank, item in enumerate(shortlisted, 1):
        item["rank"] = rank

    return {
        "needs": {
            "media_type": needs.media_type,
            "approved_for": list(needs.approved_for),
            "categories": list(needs.categories),
            "orientation": needs.orientation,
            "limit": needs.limit,
        },
        "total_assets": len(assets),
        "matched_assets": len(candidates),
        "excluded_assets": len(excluded),
        "review_required": review_required(shortlisted),
        "candidates": shortlisted,
    }


def resolve_manifest_asset(
    assets,
    asset_id,
    *,
    media_type="any",
    required_approval="",
    required_path_prefix="",
):
    """Resolve one manifest asset and enforce its intended runtime boundary."""

    matches = [asset for asset in assets if asset["dropbox_id"] == asset_id]
    if not matches:
        raise ManifestError(f"Manifest asset not found: {asset_id}")
    if len(matches) > 1:
        raise ManifestError(f"Manifest asset identity is ambiguous: {asset_id}")

    asset = matches[0]
    if media_type != "any" and asset["media_type"] != media_type:
        raise ManifestError(
            f"Manifest asset {asset_id} has media type {asset['media_type']}, not {media_type}"
        )

    if required_approval:
        approval = normalize_value(required_approval)
        if approval not in normalize_values(asset["approved_for"]):
            raise ManifestError(
                f"Manifest asset {asset_id} is not approved for {required_approval}"
            )

    if required_path_prefix:
        prefix = required_path_prefix.rstrip("/").lower() + "/"
        if not asset["dropbox_path"].lower().startswith(prefix):
            raise ManifestError(
                f"Manifest asset {asset_id} is outside required path {required_path_prefix}"
            )

    return asset


def exclusion_reason(asset, media_type, required_approvals, wanted_categories, wanted_orientation):
    if media_type != "any" and asset["media_type"] != media_type:
        return f"media type is {asset['media_type']}, not {media_type}"

    approvals = normalize_values(asset["approved_for"])
    missing_approvals = sorted(required_approvals - approvals)
    if missing_approvals:
        return "missing required approved_for value(s): " + ", ".join(missing_approvals)

    categories = normalize_values(asset["category"])
    if wanted_categories and not categories.intersection(wanted_categories):
        return "no required category overlap"

    orientation = normalize_value(asset["orientation"])
    if wanted_orientation and orientation and orientation != wanted_orientation:
        return f"orientation is {orientation}, not {wanted_orientation}"

    return ""


def score_asset(asset, media_type, required_approvals, wanted_categories, wanted_orientation):
    score = 0
    reasons = []

    if media_type != "any":
        score += 3
        reasons.append(f"matches media type '{media_type}'")

    approvals = normalize_values(asset["approved_for"])
    if required_approvals:
        score += 50
        reasons.append(
            "contains required approved_for value(s): "
            + ", ".join(sorted(required_approvals.intersection(approvals)))
        )

    categories = normalize_values(asset["category"])
    category_matches = sorted(categories.intersection(wanted_categories))
    if category_matches:
        score += 10 * len(category_matches)
        reasons.append("category overlap: " + ", ".join(category_matches))
    elif wanted_categories:
        reasons.append("no category score; category metadata is missing")

    orientation = normalize_value(asset["orientation"])
    if wanted_orientation and orientation == wanted_orientation:
        score += 6
        reasons.append(f"matches orientation '{wanted_orientation}'")
    elif wanted_orientation and not orientation:
        reasons.append("orientation metadata unavailable; no orientation score")

    if not reasons:
        reasons.append("included by manifest order-independent fallback ranking")

    return score, reasons


def candidate_record(asset, score, reasons):
    return {
        "rank": None,
        "score": score,
        "filename": asset["filename"],
        "dropbox_id": asset["dropbox_id"],
        "dropbox_path": asset["dropbox_path"],
        "media_type": asset["media_type"],
        "category": asset["category"],
        "orientation": asset["orientation"],
        "approved_for": asset["approved_for"],
        "public_url": asset["public_url"],
        "reasons": reasons,
    }


def review_required(candidates):
    if len(candidates) < 2:
        return False
    top = candidates[0]
    for candidate in candidates[1:]:
        if top["score"] - candidate["score"] > REVIEW_SCORE_WINDOW:
            continue
        if materially_different(top, candidate):
            return True
    return False


def materially_different(left, right):
    return any(
        left[field] != right[field]
        for field in ("dropbox_path", "media_type", "orientation", "category")
    )


def media_type_for(filename):
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    return "other"


def stable_identity(item):
    dropbox_id = item.get("dropbox_id", "").strip()
    if dropbox_id:
        return f"id:{dropbox_id}"
    return "path:" + item.get("dropbox_path", "").strip().lower()


def normalize_values(values):
    return {normalize_value(value) for value in values if normalize_value(value)}


def normalize_value(value):
    return str(value).strip().lower()
