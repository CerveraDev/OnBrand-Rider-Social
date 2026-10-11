"""Project social approval overlay: validation and deterministic merge.

Social approvals are human decisions, so they live in a committed project overlay
rather than in the generated Dropbox manifest. This module validates that overlay
and merges it over already-validated manifest assets.

It never mutates `approved_for`. Email role semantics stay exactly as the manifest
records them; social roles are attached under a separate `social_roles` key.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


OVERLAY_VERSION = "1.0"
SOCIAL_ROLES = ("social-post", "social-carousel", "social-crop-source")

OVERLAY_FIELDS = {
    "schema_version",
    "project_slug",
    "medium",
    "approver",
    "approved_date",
    "basis",
    "role_vocabulary",
    "never_social_roles",
    "source_manifest",
    "entries",
    "excluded",
}
ENTRY_FIELDS = {
    "filename",
    "dropbox_id",
    "cluster",
    "orientation",
    "approved_for_social",
    "third_party_rights",
}
EXCLUDED_FIELDS = {"filename", "dropbox_id", "reason"}


class SocialApprovalError(ValueError):
    """Raised when a social approval overlay is malformed or unsafe."""


def load_social_approvals(path: Path | str) -> dict:
    """Read and validate a social approval overlay."""
    path = Path(path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise SocialApprovalError(f"Invalid social approval JSON: {err}") from err
    return validate_social_approvals(data, source=str(path))


def validate_social_approvals(data: object, source: str = "<overlay>") -> dict:
    if not isinstance(data, dict):
        raise SocialApprovalError(f"{source} must be a JSON object")

    unknown = sorted(set(data) - OVERLAY_FIELDS)
    if unknown:
        raise SocialApprovalError(f"{source} has unknown field(s): " + ", ".join(unknown))
    if data.get("schema_version") != OVERLAY_VERSION:
        raise SocialApprovalError(f"{source} schema_version must be {OVERLAY_VERSION}")
    for field in ("project_slug", "medium", "approver", "approved_date"):
        value = data.get(field)
        if not isinstance(value, str) or not value:
            raise SocialApprovalError(f"{source} field '{field}' must be a non-empty string")
    if data["medium"] != "social":
        raise SocialApprovalError(f"{source} medium must be 'social'")

    vocabulary = data.get("role_vocabulary")
    if not isinstance(vocabulary, list) or sorted(vocabulary) != sorted(SOCIAL_ROLES):
        raise SocialApprovalError(
            f"{source} role_vocabulary must be exactly {sorted(SOCIAL_ROLES)}"
        )

    never = data.get("never_social_roles")
    if not isinstance(never, list) or not never or any(not isinstance(v, str) for v in never):
        raise SocialApprovalError(f"{source} never_social_roles must be a non-empty string array")

    manifest_ref = data.get("source_manifest")
    if not isinstance(manifest_ref, dict):
        raise SocialApprovalError(f"{source} source_manifest must be an object")
    for field in ("path", "sha256"):
        if not isinstance(manifest_ref.get(field), str) or not manifest_ref[field]:
            raise SocialApprovalError(f"{source} source_manifest.{field} must be a non-empty string")
    if not isinstance(manifest_ref.get("record_count"), int):
        raise SocialApprovalError(f"{source} source_manifest.record_count must be an integer")

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SocialApprovalError(f"{source} entries must be a non-empty array")

    seen: dict[str, str] = {}
    validated = []
    for index, entry in enumerate(entries):
        label = f"{source} entry {index}"
        if not isinstance(entry, dict):
            raise SocialApprovalError(f"{label} must be a JSON object")
        unknown = sorted(set(entry) - ENTRY_FIELDS)
        if unknown:
            raise SocialApprovalError(f"{label} has unknown field(s): " + ", ".join(unknown))
        for field in ("filename", "dropbox_id", "cluster"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                raise SocialApprovalError(f"{label} field '{field}' must be a non-empty string")
        roles = entry.get("approved_for_social")
        if not isinstance(roles, list) or not roles:
            raise SocialApprovalError(f"{label} approved_for_social must be a non-empty array")
        bad = sorted(set(roles) - set(SOCIAL_ROLES))
        if bad:
            raise SocialApprovalError(f"{label} has unknown social role(s): " + ", ".join(bad))
        if len(set(roles)) != len(roles):
            raise SocialApprovalError(f"{label} repeats a social role")
        if entry["dropbox_id"] in seen:
            raise SocialApprovalError(
                f"{label} duplicates dropbox_id already approved for "
                f"'{seen[entry['dropbox_id']]}'"
            )
        seen[entry["dropbox_id"]] = entry["filename"]
        validated.append(entry)

    excluded = data.get("excluded", [])
    if not isinstance(excluded, list):
        raise SocialApprovalError(f"{source} excluded must be an array")
    for index, item in enumerate(excluded):
        label = f"{source} excluded {index}"
        if not isinstance(item, dict):
            raise SocialApprovalError(f"{label} must be a JSON object")
        unknown = sorted(set(item) - EXCLUDED_FIELDS)
        if unknown:
            raise SocialApprovalError(f"{label} has unknown field(s): " + ", ".join(unknown))
        for field in ("filename", "reason"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise SocialApprovalError(f"{label} field '{field}' must be a non-empty string")
        if item["dropbox_id"] in seen:
            raise SocialApprovalError(
                f"{label} ('{item['filename']}') is both approved and excluded"
            )

    return {
        "schema_version": OVERLAY_VERSION,
        "project_slug": data["project_slug"],
        "medium": "social",
        "approver": data["approver"],
        "approved_date": data["approved_date"],
        "basis": data.get("basis", ""),
        "role_vocabulary": list(vocabulary),
        "never_social_roles": list(never),
        "source_manifest": dict(manifest_ref),
        "entries": validated,
        "excluded": list(excluded),
    }


def apply_social_approvals(assets: list[dict], overlay: dict) -> list[dict]:
    """Return a copy of `assets` with validated `social_roles` attached.

    Blocks when an approval targets a record that does not exist, or a record whose
    email `approved_for` carries a role that may never be used on social.
    """
    never = set(overlay["never_social_roles"])
    by_id = {}
    for asset in assets:
        identity = asset.get("dropbox_id") or ""
        if identity:
            by_id.setdefault(identity, []).append(asset)

    approvals = {entry["dropbox_id"]: entry for entry in overlay["entries"]}
    missing = sorted(i for i in approvals if i not in by_id)
    if missing:
        raise SocialApprovalError(
            "Social approval references record(s) absent from the manifest: "
            + ", ".join(f"{approvals[i]['filename']} ({i})" for i in missing[:5])
        )

    merged = []
    for asset in assets:
        record = dict(asset)
        entry = approvals.get(record.get("dropbox_id") or "")
        if entry is None:
            record["social_roles"] = []
            merged.append(record)
            continue
        blocked = sorted(set(record.get("approved_for") or []) & never)
        if blocked:
            raise SocialApprovalError(
                f"'{record['filename']}' is approved for social but carries restricted "
                f"role(s) {blocked}; restricted records may never resolve to a social role"
            )
        record["social_roles"] = list(entry["approved_for_social"])
        record["social_cluster"] = entry["cluster"]
        if "third_party_rights" in entry:
            record["third_party_rights"] = entry["third_party_rights"]
        merged.append(record)
    return merged


def social_candidates(assets: list[dict], role: str) -> list[dict]:
    """Return assets carrying `role`, in deterministic filename order."""
    if role not in SOCIAL_ROLES:
        raise SocialApprovalError(f"Unknown social role: {role}")
    return sorted(
        (a for a in assets if role in (a.get("social_roles") or [])),
        key=lambda a: a["filename"],
    )


def manifest_matches(overlay: dict, manifest_path: Path | str) -> bool:
    """Whether the overlay was approved against the manifest's current bytes."""
    path = Path(manifest_path).expanduser()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == overlay["source_manifest"]["sha256"]
