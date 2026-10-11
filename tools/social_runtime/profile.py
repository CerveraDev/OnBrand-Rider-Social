"""Project profile: the facts about a project that an admin records once.

`projects/<project>/profile.json` holds the official name, nickname, contact
details, addresses, and social account settings. It is medium-neutral, so any runtime may
read it; here it supplies the simulator's account handle and picture. Fields an
admin has not filled in are null, and fields this module does not know are kept.
"""

from __future__ import annotations

import json
from pathlib import Path
import re


PROFILE_FILE = "profile.json"
SCHEMA_VERSION = 1
TEXT_FIELDS = ("official_name", "nickname", "phone", "email")
# Addresses are lists of lines, written as they should appear.
ADDRESS_FIELDS = ("sales_gallery_address", "project_site_address")
SOCIAL_FIELDS = ("instagram_handle", "avatar", "logo_on_light")
AVATAR_SUFFIXES = (".png", ".jpg", ".jpeg")
HANDLE = re.compile(r"[A-Za-z0-9._]{1,30}")


class ProfileError(ValueError):
    """Raised when a project profile is unreadable or holds an unusable value."""


def load_profile(project_dir: Path) -> dict:
    """Return the project's profile with every known field present; a missing file is an empty profile."""
    project_dir = Path(project_dir)
    path = project_dir / PROFILE_FILE
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            raise ProfileError(f"{PROFILE_FILE} is not readable JSON") from err
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            raise ProfileError(f"{PROFILE_FILE} must be an object with schema_version {SCHEMA_VERSION}")
    social = data.get("social") or {}
    if not isinstance(social, dict):
        raise ProfileError(f"{PROFILE_FILE}: 'social' must be an object")
    for field, value in [(f, data.get(f)) for f in TEXT_FIELDS] + [(f"social.{f}", social.get(f)) for f in SOCIAL_FIELDS]:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ProfileError(f"{PROFILE_FILE}: '{field}' must be text or null")
    for field in ADDRESS_FIELDS:
        lines = data.get(field)
        if lines is not None and not (
            isinstance(lines, list) and lines and all(isinstance(line, str) and line.strip() for line in lines)
        ):
            raise ProfileError(f"{PROFILE_FILE}: '{field}' must be a list of address lines or null")
    handle = social.get("instagram_handle")
    if handle is not None and not HANDLE.fullmatch(handle):
        raise ProfileError(f"{PROFILE_FILE}: 'social.instagram_handle' is the handle alone, without @ or a link")
    profile = {**data, **{field: data.get(field) for field in TEXT_FIELDS + ADDRESS_FIELDS}}
    profile["social"] = {**social, **{field: social.get(field) for field in SOCIAL_FIELDS}}
    return profile


def avatar_path(project_dir: Path, profile: dict) -> Path | None:
    """Resolve the profile's avatar, a PNG or JPEG path relative to the project directory."""
    reference = profile["social"]["avatar"]
    if reference is None:
        return None
    root = Path(project_dir).resolve()
    path = (root / reference).resolve()
    if root not in path.parents:
        raise ProfileError(f"{PROFILE_FILE}: 'social.avatar' must be a path inside the project")
    if path.suffix.lower() not in AVATAR_SUFFIXES:
        raise ProfileError(f"{PROFILE_FILE}: 'social.avatar' must be a PNG or JPEG")
    if not path.is_file():
        raise ProfileError(f"{PROFILE_FILE}: avatar '{reference}' was not found")
    return path


def logo_on_light(project_dir: Path, profile: dict) -> str | None:
    """Resolve the logo used over light images: an https link, or a PNG path inside the project, as a URL."""
    reference = profile["social"]["logo_on_light"]
    if reference is None or reference.startswith("https://"):
        return reference
    root = Path(project_dir).resolve()
    path = (root / reference).resolve()
    if root not in path.parents or path.suffix.lower() != ".png" or not path.is_file():
        raise ProfileError(f"{PROFILE_FILE}: 'social.logo_on_light' must be an https link or a PNG inside the project")
    return path.as_uri()
