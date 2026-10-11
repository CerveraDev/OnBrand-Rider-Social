"""Blocking QA over a written social package."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re


PRIVATE_PATTERNS = (
    ("dropbox-id", re.compile(r"dropbox_id|\"id:[A-Za-z0-9_-]{6,}")),
    ("dropbox-path", re.compile(r"dropbox_path")),
    ("local-path", re.compile(r"file://|/Users/|/home/|/private/|/tmp/|[A-Za-z]:\\\\")),
    ("agent-data", re.compile(r"data/agents")),
)


@dataclass(frozen=True)
class QAResult:
    passed: bool
    checks: list[dict]
    warnings: list[str] = field(default_factory=list)
    build: dict | None = None
    copy_allocation: dict | None = None


def run_qa(
    package_dir: Path,
    *,
    package: dict,
    template: dict,
    steps: list[dict],
    fmt: dict,
    resolved_assets: list[dict],
    crops: list[dict],
    supplied: list[dict],
    never_social_roles: list[str],
    allocation: dict,
    warnings: list[str],
) -> QAResult:
    checks: list[dict] = []
    audience = package["audience"]
    limits = fmt["text_limits"]

    for name, variant in sorted(package["variants"].items()):
        slides = variant["slides"]
        _check(checks, f"{name}:slide-count",
               fmt["min_slides"] <= len(slides) <= fmt["max_slides"]
               and template["min_slides"] <= len(slides) <= template["max_slides"],
               f"{len(slides)} slides within format and template limits")
        for slide, step in zip(slides, steps):
            label = f"{name}:slide-{slide['index']}"
            missing = sorted(slot for slot, rule in step["slots"].items()
                             if rule["required"] and slot not in slide["text"])
            _check(checks, f"{label}:slots", not missing,
                   "required slots filled" if not missing else "missing: " + ", ".join(missing))
            for image in slide["images"]:
                _check(checks, f"{label}:image:{image['slot']}", bool(image.get("src")) or image.get("pending") is True,
                       "image resolved to an approved record, a crop, or a supplied file")
            for slot, text in slide["text"].items():
                limit = step["slots"][slot]["max_chars"]
                _check(checks, f"{label}:text:{slot}", measured_length(text) <= limit,
                       f"{measured_length(text)} of {limit} characters")
            _check(checks, f"{label}:alt-text", measured_length(slide["alt_text"]) <= limits["alt-text"],
                   f"{measured_length(slide['alt_text'])} of {limits['alt-text']} characters")
        _check(checks, f"{name}:caption", measured_length(variant["caption"]) <= limits["caption"],
               f"{measured_length(variant['caption'])} of {limits['caption']} characters")
        _check(checks, f"{name}:hashtags", len(variant["hashtags"]) <= limits["hashtags"],
               f"{len(variant['hashtags'])} of {limits['hashtags']} hashtags")

    for crop in crops:
        output = crop["output"]
        if output is None:
            continue
        _check(checks, f"crop:{crop['id']}:output",
               (output["width"], output["height"]) == (crop["target"]["width"], crop["target"]["height"])
               and output["bytes"] <= fmt["max_file_bytes"]
               and (package_dir / "images" / output["name"]).is_file(),
               f"{output['width']}x{output['height']}, {output['bytes']} bytes, packaged")

    for image in supplied:
        _check(checks, f"supplied:{image['name']}:packaged", (package_dir / "images" / image["name"]).is_file(),
               f"{image['width']}x{image['height']}, {image['bytes']} bytes, user-supplied")

    never = set(never_social_roles)
    restricted = sorted(a["filename"] for a in resolved_assets if set(a.get("approved_for") or []) & never)
    _check(checks, "restricted-assets-absent", not restricted,
           "no agent-footer or likeness-reference record is used" if not restricted
           else "restricted record(s) used: " + ", ".join(restricted))
    unapproved = sorted(a["filename"] for a in resolved_assets if not a.get("social_roles"))
    _check(checks, "assets-social-approved", not unapproved,
           "every image resolves to a social-approved record" if not unapproved
           else "not social-approved: " + ", ".join(unapproved))

    leaks = []
    for path in sorted(package_dir.rglob("*")):
        if path.suffix not in {".json", ".html"} or path.name == "qa-report.json":
            continue
        text = path.read_text(encoding="utf-8")
        leaks.extend(f"{path.name}:{name}" for name, pattern in PRIVATE_PATTERNS if pattern.search(text))
    _check(checks, "private-data-absent", not leaks,
           "no Dropbox identifier, Dropbox path, local path, or agent data in delivered files" if not leaks
           else "found: " + ", ".join(leaks))

    checks.extend(allocation["checks"])
    _check(checks, "audience-template", audience in template["audiences"],
           f"template {template['code']} is available to {audience}")
    return QAResult(
        passed=all(check["passed"] for check in checks),
        checks=checks,
        warnings=list(warnings),
        build=package["build"],
        copy_allocation={k: v for k, v in allocation.items() if k != "checks"},
    )


def write_qa_report(path: Path, result: QAResult) -> Path:
    path.write_text(
        json.dumps(
            {
                "passed": result.passed,
                "build": result.build or {},
                "copy_allocation": result.copy_allocation or {},
                "warnings": result.warnings,
                "checks": result.checks,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def measured_length(text: str) -> int:
    """Length after whitespace normalization, as the platform would count it."""
    return len(re.sub(r"\s+", " ", text).strip())


def _check(checks: list[dict], name: str, passed: bool, message: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "message": message})
