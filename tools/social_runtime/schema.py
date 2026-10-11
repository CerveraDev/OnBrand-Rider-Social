"""Shape validation for a canonical social campaign spec. Performs no file access."""

from __future__ import annotations

import re

from .frames import FRAME_ID_RE
from .templates import AUDIENCES, SLIDE_ROLES


SCHEMA_VERSION = "1.0"
BUILD_MODES = ("composition-preview", "smoke-test", "release")
VARIANTS = ("branded", "broker-customizable")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
HASHTAG_RE = re.compile(r"#\w+")
REQUIRED = {
    "schema_version", "medium", "campaign", "audience", "build", "composition",
    "slides", "caption", "copy_allocation",
}
OPTIONAL = {"hashtags", "variants", "crops", "cross_medium"}
CONTACT_FIELDS = {"name", "phone", "email", "brokerage"}


class SocialSpecError(ValueError):
    """Raised when a social campaign spec is malformed."""


def validate_social_spec(spec: object) -> dict:
    _fields(spec, REQUIRED, OPTIONAL, "social spec")
    if spec["schema_version"] != SCHEMA_VERSION:
        raise SocialSpecError(f"schema_version must be {SCHEMA_VERSION}")
    if spec["medium"] != "social":
        raise SocialSpecError("medium must be 'social'")

    campaign = spec["campaign"]
    _fields(campaign, {"slug", "project", "output_dir"}, {"campaign_id", "title"}, "campaign")
    for field in ("slug", "project"):
        if not isinstance(campaign[field], str) or not SLUG_RE.fullmatch(campaign[field]):
            raise SocialSpecError(f"campaign.{field} must be a lowercase hyphenated slug")
    _text(campaign, "output_dir", "campaign")

    if spec["audience"] not in AUDIENCES:
        raise SocialSpecError(f"audience must be one of {', '.join(AUDIENCES)}")

    build = spec["build"]
    _fields(build, {"mode"}, {"representative_variant"}, "build")
    if build["mode"] not in BUILD_MODES:
        raise SocialSpecError(f"build.mode must be one of {', '.join(BUILD_MODES)}")

    variants = spec.get("variants", {"branded": {}})
    if not isinstance(variants, dict) or not variants or set(variants) - set(VARIANTS):
        raise SocialSpecError(f"variants must be a non-empty object keyed by {', '.join(VARIANTS)}")
    for name, variant in variants.items():
        if name == "branded":
            _fields(variant, set(), set(), "variants.branded")
            continue
        _fields(variant, {"contact"}, set(), f"variants.{name}")
        contact = variant["contact"]
        _fields(contact, {"name"}, CONTACT_FIELDS - {"name"}, f"variants.{name}.contact")
        for field in contact:
            _text(contact, field, f"variants.{name}.contact")
    representative = build.get("representative_variant", sorted(variants)[0])
    if representative not in variants:
        raise SocialSpecError("build.representative_variant must name a declared variant")

    composition = spec["composition"]
    _fields(composition, {"template", "format"}, set(), "composition")
    _text(composition, "template", "composition")
    _text(composition, "format", "composition")

    slides = spec["slides"]
    if not isinstance(slides, list) or not slides:
        raise SocialSpecError("slides must be a non-empty array")
    for index, slide in enumerate(slides):
        label = f"slides[{index}]"
        _fields(slide, {"role", "frame", "images", "text", "alt_text"}, {"hide"}, label)
        if slide["role"] not in SLIDE_ROLES:
            raise SocialSpecError(f"{label}.role must be one of {', '.join(SLIDE_ROLES)}")
        if not isinstance(slide["frame"], str) or not FRAME_ID_RE.fullmatch(slide["frame"]):
            raise SocialSpecError(f"{label}.frame must be a frame id such as 'SP-01'")
        images = slide["images"]
        if not isinstance(images, dict):
            raise SocialSpecError(f"{label}.images must map each image slot to an asset, crop, or supplied image")
        hide = slide.get("hide", [])
        if not isinstance(hide, list) or any(not isinstance(mark, str) or not mark for mark in hide) or len(set(hide)) != len(hide):
            raise SocialSpecError(f"{label}.hide must be an array of unique names")
        for slot, image in images.items():
            if not isinstance(image, dict) or len(image) != 1 or not set(image) <= {"asset", "crop", "supplied"}:
                raise SocialSpecError(f"{label}.images.{slot} must give exactly one of 'asset', 'crop', or 'supplied'")
            _text(image, next(iter(image)), f"{label}.images.{slot}")
        if not isinstance(slide["text"], dict):
            raise SocialSpecError(f"{label}.text must be an object")
        for slot in slide["text"]:
            _text(slide["text"], slot, f"{label}.text")
        _text(slide, "alt_text", label)

    _text(spec, "caption", "social spec")
    hashtags = spec.get("hashtags", [])
    if not isinstance(hashtags, list) or any(
        not isinstance(tag, str) or not HASHTAG_RE.fullmatch(tag) for tag in hashtags
    ):
        raise SocialSpecError("hashtags must be an array of '#word' strings")
    if len({tag.lower() for tag in hashtags}) != len(hashtags):
        raise SocialSpecError("hashtags must not repeat")

    crops = spec.get("crops", [])
    if not isinstance(crops, list) or any(not isinstance(crop, dict) for crop in crops):
        raise SocialSpecError("crops must be an array of objects")
    crop_ids = [crop.get("id") for crop in crops]
    if len(set(crop_ids)) != len(crop_ids):
        raise SocialSpecError("crops must have unique ids")

    if not isinstance(spec["copy_allocation"], dict):
        raise SocialSpecError("copy_allocation must be an object")

    if "cross_medium" in spec:
        if spec["audience"] == "outside-broker":
            raise SocialSpecError(
                "cross_medium is not available to the outside-broker audience; "
                "the email medium is absent from a broker bundle"
            )
        cross = spec["cross_medium"]
        _fields(cross, {"surfaces"}, {"exemptions"}, "cross_medium")
        if not isinstance(cross["surfaces"], list) or not cross["surfaces"]:
            raise SocialSpecError("cross_medium.surfaces must be a non-empty array")
        for index, surface in enumerate(cross["surfaces"]):
            label = f"cross_medium.surfaces[{index}]"
            _fields(surface, {"medium", "campaign_spec"}, set(), label)
            if surface["medium"] != "email":
                raise SocialSpecError(f"{label}.medium must be 'email'")
            _text(surface, "campaign_spec", label)
        exemptions = cross.get("exemptions", [])
        if not isinstance(exemptions, list):
            raise SocialSpecError("cross_medium.exemptions must be an array")
        for index, exemption in enumerate(exemptions):
            label = f"cross_medium.exemptions[{index}]"
            _fields(exemption, {"social", "other", "reason"}, set(), label)
            for field in exemption:
                _text(exemption, field, label)
    return spec


def _fields(value: object, required: set, optional: set, label: str) -> None:
    if not isinstance(value, dict):
        raise SocialSpecError(f"{label} must be a JSON object")
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing or unknown:
        raise SocialSpecError(f"{label} fields: missing={missing}, unknown={unknown}")


def _text(obj: dict, field: str, label: str) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SocialSpecError(f"{label}.{field} must be a non-empty string")
    return value
