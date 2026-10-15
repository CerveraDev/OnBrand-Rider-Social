"""Post brief: the short form a person or a skill writes, expanded into a full social spec.

A brief names the layouts in order and, for each, its images, text, and alt text,
plus the caption and hashtags. Everything else a spec needs is derived here: the
post type the layouts fit, each slide's role, the format, a centred planned crop
for a catalog image that cannot be used as it is, and one draft content unit per
piece of text. A composed spec is always a draft in `composition-preview` mode for
the in-house audience; approving copy, crops, and templates is not this module's job.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from tools.asset_selection.manifest_source import validate_manifest_source_config

from .assets import CROP_ROLE, DIRECT_ROLE, SocialAssetError, load_social_assets
from .catalog import default_output_dir, image_sizes
from .formats import FORMATS_PATH, FormatError, load_formats, require_format
from .frames import FRAMES_FILE, FrameError
from .generated import GeneratedImageError, accepts, load_policy, record_problem
from .schema import SLUG_RE
from .templates import TemplateError, load_template


ROOT = Path(__file__).resolve().parents[2]
BRIEF_FIELDS = {"project", "slug", "slides", "caption"}
BRIEF_OPTIONAL = {"title", "hashtags", "post_type"}
SLIDE_FIELDS = {"layout", "images", "text", "alt_text"}
SLIDE_OPTIONAL = {"hide"}


class BriefError(ValueError):
    """Raised when a post brief cannot be turned into a spec, with what to change."""


def compose_spec(
    brief: object,
    *,
    brief_dir: Path | str,
    project_dir: Path | None = None,
    manifest_path: Path | str | None = None,
    formats_path: Path = FORMATS_PATH,
    output_dir: Path | str | None = None,
    sizes=None,
) -> dict:
    """Return the full social spec for `brief`. `sizes` maps catalog assets to pixel sizes."""
    _fields(brief, BRIEF_FIELDS, BRIEF_OPTIONAL, "The brief")
    for field in ("project", "slug"):
        if not isinstance(brief[field], str) or not SLUG_RE.fullmatch(brief[field]):
            raise BriefError(f"'{field}' must be lowercase words joined by hyphens")
    slides = brief["slides"]
    if not isinstance(slides, list) or not slides:
        raise BriefError("'slides' must list at least one slide")
    for number, slide in enumerate(slides, start=1):
        _fields(slide, SLIDE_FIELDS, SLIDE_OPTIONAL, f"Slide {number}")
        if not isinstance(slide["images"], dict) or not isinstance(slide["text"], dict):
            raise BriefError(f"Slide {number}: 'images' and 'text' must be objects keyed by area name")
    project_dir = Path(project_dir) if project_dir else ROOT / "projects" / brief["project"]
    templates_dir = project_dir / "social" / "templates"
    try:
        template, roles = _post_type(templates_dir, [slide["layout"] for slide in slides], brief.get("post_type"))
        format_id = template["formats"][0]
        fmt = require_format(load_formats(formats_path), format_id)
        if manifest_path is None:
            manifest_path = validate_manifest_source_config(project_dir / "manifest-source.json")["local_cache_path"]
        assets = {
            asset["filename"]: asset
            for asset in load_social_assets(manifest_path, project_dir / "asset-approvals.social.json", audience="in-house")
            if asset.get("social_roles")
        }
    except (OSError, ValueError, TemplateError, FrameError, FormatError, SocialAssetError) as err:
        if isinstance(err, BriefError):
            raise
        raise BriefError(str(err)) from err

    direct_role = DIRECT_ROLE[template["kind"]]
    try:
        generated_policy = load_policy(project_dir)
    except GeneratedImageError as err:
        raise BriefError(str(err)) from err
    # A supplied logo, such as a publication's, is given once and shown on every slide that has room for it.
    shared = {slot: choice for slide in reversed(slides) for slot, choice in slide["images"].items()}
    planned: list[tuple[dict, dict, dict]] = []
    spec_slides = []
    for number, (slide, role) in enumerate(zip(slides, roles), start=1):
        frame = template["frame_definitions"][slide["layout"]]
        areas = {area["slot"]: area for area in frame["image_slots"]}
        slide = {**slide, "images": {
            **{slot: shared[slot] for slot, area in areas.items() if area["fit"] == "contain" and slot in shared},
            **slide["images"],
        }}
        _same_keys(slide["images"], areas, f"Slide {number} ({slide['layout']}) image areas",
                   optional={slot for slot, area in areas.items() if not area["required"]})
        hide = slide.get("hide", [])
        if not isinstance(hide, list) or set(map(str, hide)) - set(frame["optional_marks"]):
            raise BriefError(
                f"Slide {number} ({slide['layout']}) 'hide' may list only: {', '.join(frame['optional_marks']) or 'nothing'}"
            )
        required = {slot for slot, rule in frame["text_slots"].items() if rule["required"]}
        missing = sorted(required - set(slide["text"]))
        unknown = sorted(set(slide["text"]) - set(frame["text_slots"]))
        if missing or unknown:
            raise BriefError(
                f"Slide {number} ({slide['layout']}) text: "
                + "; ".join(part for part in (
                    f"missing {', '.join(missing)}" if missing else "",
                    f"this layout has no {', '.join(unknown)}" if unknown else "",
                ) if part)
            )
        images = {}
        for slot, area in areas.items():
            if slot not in slide["images"]:
                continue
            choice = slide["images"][slot]
            if area["fit"] == "contain" and (not isinstance(choice, dict) or set(choice) != {"file"}):
                raise BriefError(f"Slide {number} '{slot}': give {{\"file\": \"<path>\"}}; this area takes a supplied logo only")
            if isinstance(choice, dict) and "generated" in choice:
                record = {"file" if key == "generated" else key: value for key, value in choice.items()}
                problem = record_problem(record)
                if problem:
                    raise BriefError(
                        f"Slide {number} '{slot}': an AI-generated image is given as {{\"generated\": \"<path>\", "
                        f"\"prompt\": \"...\", \"tool\": \"...\"}}, optionally with \"based_on\": [\"<catalog file name>\"]; {problem}"
                    )
                if not accepts(generated_policy, slide["layout"]):
                    raise BriefError(
                        f"Slide {number}: layout {slide['layout']} does not take AI-generated images; use a catalog "
                        "image or the user's own, or choose another layout"
                    )
                path = Path(record["file"]).expanduser()
                record["file"] = str(path if path.is_absolute() else (Path(brief_dir) / path).resolve())
                images[slot] = {"generated": record}
                continue
            if not isinstance(choice, dict) or len(choice) != 1 or not set(choice) <= {"catalog", "file"} \
                    or not isinstance(next(iter(choice.values())), str):
                raise BriefError(
                    f"Slide {number} '{slot}': give {{\"catalog\": \"<file name>\"}}, {{\"file\": \"<path>\"}}, "
                    "or an AI-generated image with its prompt and tool"
                )
            if "file" in choice:
                path = Path(choice["file"]).expanduser()
                images[slot] = {"supplied": str(path if path.is_absolute() else (Path(brief_dir) / path).resolve())}
                continue
            asset = assets.get(choice["catalog"])
            if asset is None:
                raise BriefError(f"Slide {number} '{slot}': '{choice['catalog']}' is not in the image catalog")
            if asset["orientation"] == area["shape"] and direct_role in asset["social_roles"]:
                images[slot] = {"asset": asset["filename"]}
                continue
            if CROP_ROLE not in asset["social_roles"]:
                raise BriefError(
                    f"Slide {number} '{slot}': '{asset['filename']}' is {asset['orientation']} and this area is "
                    f"{area['shape']}; choose a {area['shape']} image"
                )
            crop = {"id": f"s{number}-{slot}", "source_asset": asset["filename"]}
            planned.append((crop, asset, area))
            images[slot] = {"crop": crop["id"]}
        spec_slides.append({
            "role": role, "frame": slide["layout"], "images": images,
            "text": slide["text"], "alt_text": slide["alt_text"], **({"hide": hide} if hide else {}),
        })

    crops = []
    if planned:
        wanted = list({asset["filename"]: asset for _, asset, _ in planned}.values())
        measured = (sizes or _measure(brief["project"]))(wanted)
        for crop, asset, area in planned:
            if asset["filename"] not in measured:
                raise BriefError(f"'{asset['filename']}' could not be measured for cropping; try again")
            width, height = measured[asset["filename"]]
            crops.append({
                **crop, "format": format_id, "source_dimensions": {"width": width, "height": height},
                "geometry": _centred(width, height, area["width"] / area["height"]),
                "focal_point": {"x": width // 2, "y": height // 2}, "approval_status": "planned",
            })

    hashtags = brief.get("hashtags", [])
    spec = {
        "schema_version": "1.0", "medium": "social",
        "campaign": {
            "slug": brief["slug"], "project": brief["project"],
            "output_dir": str(Path(output_dir) if output_dir else ROOT / "campaign-output" / "social"),
            "title": brief.get("title") or brief["slug"].replace("-", " ").capitalize(),
        },
        "audience": "in-house",
        "build": {"mode": "composition-preview", "representative_variant": "branded"},
        "variants": {"branded": {}},
        "composition": {"template": template["code"], "format": format_id},
        "slides": spec_slides,
        "caption": brief["caption"],
        "copy_allocation": {"version": "1.0", "status": "draft", "content_units": _units(brief, spec_slides, template)},
    }
    if hashtags:
        spec["hashtags"] = hashtags
    if crops:
        spec["crops"] = crops
    return spec


def _post_type(templates_dir: Path, layouts: list, wanted: object) -> tuple[dict, list[str]]:
    """Pick the post type the layouts fit, in order, and the role each slide plays in it."""
    codes = sorted(path.stem for path in templates_dir.glob("*.json") if path.name != FRAMES_FILE)
    if wanted is not None:
        if wanted not in codes:
            raise BriefError(f"Unknown post type '{wanted}'; available: {', '.join(codes)}")
        codes = [wanted]
    fits = []
    for code in codes:
        template = load_template(templates_dir, code)
        steps = _deal(template["sequence"], layouts, 0, 0)
        if steps is not None and template["min_slides"] <= len(layouts) <= template["max_slides"]:
            # The closest match gives the most slides a place only one layout can take, such as a cover.
            fixed = sum(len(step["frames"]) == 1 for step in steps)
            size = len({frame for step in template["sequence"] for frame in step["frames"]})
            fits.append((-fixed, size, code, template, [step["role"] for step in steps]))
    if not fits:
        raise BriefError(
            f"The layouts {', '.join(map(str, layouts))} do not form a post in that order. "
            "Open the layout gallery to see which layouts go together."
        )
    *_, template, roles = min(fits, key=lambda item: item[:3])
    return template, roles


def _deal(sequence: list[dict], layouts: list, step: int, at: int) -> list[dict] | None:
    """The sequence step each layout falls to, in order, or None when they do not fit.

    A layout two steps could take goes to the earlier one, so a carousel's first slide is its opener.
    """
    if step == len(sequence):
        return [] if at == len(layouts) else None
    current = sequence[step]
    cap = current.get("cap", {"frames": (), "max": 0})
    most = capped = 0
    while most < current["max"] and at + most < len(layouts) and layouts[at + most] in current["frames"]:
        capped += layouts[at + most] in cap["frames"]
        if capped > cap["max"]:
            break
        most += 1
    for taken in range(most, current["min"] - 1, -1):
        rest = _deal(sequence, layouts, step + 1, at + taken)
        if rest is not None:
            return [current] * taken + rest
    return None


def _centred(width: int, height: int, ratio: float) -> dict:
    """The largest centred rectangle of the given width-to-height ratio."""
    if width / height > ratio:
        crop_width, crop_height = round(height * ratio), height
    else:
        crop_width, crop_height = width, round(width / ratio)
    return {"x": (width - crop_width) // 2, "y": (height - crop_height) // 2, "width": crop_width, "height": crop_height}


def _units(brief: dict, slides: list[dict], template: dict) -> list[dict]:
    units = [{"id": "caption", "text": brief["caption"], "owner": {"channel": "caption"}}]
    if brief.get("hashtags"):
        units.append({"id": "hashtags", "text": " ".join(brief["hashtags"]), "owner": {"channel": "hashtags"}})
    for number, slide in enumerate(slides, start=1):
        slots = template["frame_definitions"][slide["frame"]]["text_slots"]
        for slot, text in slide["text"].items():
            channel = slots[slot]["channel"] if slot in slots else "on-image-text"
            units.append({"id": f"s{number}-{slot}", "text": text,
                          "owner": {"channel": channel, "slide": number, "slot": slot}})
        units.append({"id": f"s{number}-alt", "text": slide["alt_text"], "owner": {"channel": "alt-text", "slide": number}})
    # A line repeated word for word across slides, such as an event date, is a deliberate refrain.
    seen: dict[str, list[dict]] = {}
    for unit in units:
        if unit["owner"]["channel"] != "hashtags" and isinstance(unit["text"], str):
            seen.setdefault(re.sub(r"\s+", " ", unit["text"]).strip().lower(), []).append(unit)
    for group in seen.values():
        if len(group) > 1:
            for unit in group:
                unit["reuse_policy"] = "intentional-refrain"
    return [{**unit, "approval_status": "draft"} for unit in units]


def _measure(project_slug: str):
    return lambda assets: image_sizes(assets, output_dir=default_output_dir(project_slug))


def _fields(value: object, required: set, optional: set, label: str) -> None:
    if not isinstance(value, dict):
        raise BriefError(f"{label} must be a JSON object")
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing or unknown:
        raise BriefError(
            f"{label}: " + "; ".join(part for part in (
                f"missing {', '.join(missing)}" if missing else "", f"unknown {', '.join(unknown)}" if unknown else "",
            ) if part)
        )


def _same_keys(given: dict, expected: dict, label: str, *, optional: set = frozenset()) -> None:
    missing = sorted(set(expected) - set(given) - optional)
    unknown = sorted(set(given) - set(expected))
    if missing or unknown:
        raise BriefError(
            f"{label}: " + "; ".join(part for part in (
                f"missing {', '.join(missing)}" if missing else "",
                f"this layout has no {', '.join(unknown)}" if unknown else "",
            ) if part)
        )


def describe_layouts(project_dir: Path | str) -> dict:
    """A compact account of a project's post types and layouts, for writing a brief."""
    templates_dir = Path(project_dir) / "social" / "templates"
    try:
        frames = json.loads((templates_dir / FRAMES_FILE).read_text(encoding="utf-8"))["frames"]
        templates = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(templates_dir.glob("*.json")) if path.name != FRAMES_FILE
        ]
        generated_policy = load_policy(project_dir)
    except (OSError, ValueError, KeyError) as err:
        raise BriefError(f"This project has no social layouts: {err}") from err
    return {
        "post_types": [
            {
                "code": template["code"], "label": template["label"],
                "slides": [template["min_slides"], template["max_slides"]],
                "order": [
                    {
                        "count": [step["min"], step["max"]], "layouts": _ranges(step["frames"]),
                        **({"at_most": {_ranges(step["cap"]["frames"]): step["cap"]["max"]}} if "cap" in step else {}),
                    }
                    for step in template["sequence"]
                ],
            }
            for template in templates
        ],
        "layouts": {
            frame_id: {
                "ai_images": accepts(generated_policy, frame_id) and any(a["fit"] == "cover" for a in frame["image_slots"]),
                "images": {
                    area["slot"]: ("a logo file" if area["fit"] == "contain" else area["shape"])
                    + ("" if area["required"] else ", optional")
                    for area in frame["image_slots"]
                },
                "fixed": {slot: text for slot, text in frame["locked"].items() if slot != "logo"},
                "can_hide": list(frame["optional_marks"]),
                "text": {
                    slot: {
                        "max_lines": rule["max_lines"], "about_chars": rule["max_chars"],
                        **({"italic_word": True} if rule["italic_accent"] else {}),
                        **({} if rule["required"] else {"optional": True}),
                    }
                    for slot, rule in frame["text_slots"].items()
                },
            }
            for frame_id, frame in frames.items()
        },
    }


def _ranges(frames: list[str]) -> str:
    """Collapse consecutive layout ids, as in 'SC-01..SC-07, SG-01..SG-08'."""
    runs: list[list[str]] = []
    for frame in sorted(frames):
        prefix, number = frame.split("-")
        if runs and runs[-1][-1].split("-")[0] == prefix and int(runs[-1][-1].split("-")[1]) + 1 == int(number):
            runs[-1].append(frame)
        else:
            runs.append([frame])
    return ", ".join(run[0] if len(run) == 1 else f"{run[0]}..{run[-1]}" for run in runs)
