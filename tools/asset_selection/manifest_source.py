"""Project manifest-source configuration and local-cache validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from .selector import ManifestError, load_manifest


ROOT = Path(__file__).resolve().parents[2]
CONFIG_VERSION = "1.0"


class ManifestSourceError(ValueError):
    """Raised when a project manifest-source configuration is unsafe."""


def validate_manifest_source_config(config_path: Path | str) -> dict:
    path = Path(config_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ManifestSourceError(f"Invalid manifest source JSON: {err}") from err
    if not isinstance(data, dict):
        raise ManifestSourceError("Manifest source config must be a JSON object")

    allowed = {
        "schema_version",
        "project_slug",
        "public_url",
        "local_cache_path",
        "active_source",
        "notes",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ManifestSourceError("Manifest source config has unknown field(s): " + ", ".join(unknown))
    if data.get("schema_version") != CONFIG_VERSION:
        raise ManifestSourceError(f"schema_version must be {CONFIG_VERSION}")
    project_slug = _require_str(data, "project_slug")
    public_url = data.get("public_url", "")
    if not isinstance(public_url, str):
        raise ManifestSourceError("public_url must be a string")
    if public_url:
        parsed = urlparse(public_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ManifestSourceError("public_url must be an http(s) URL when configured")

    local_cache = _resolve_repo_path(_require_str(data, "local_cache_path"), base_dir=path.parent)
    assets = load_manifest(local_cache)
    active_source = _require_str(data, "active_source")
    if active_source not in {"local-cache", "public-url"}:
        raise ManifestSourceError("active_source must be local-cache or public-url")
    if active_source == "public-url" and not public_url:
        raise ManifestSourceError("active_source public-url requires public_url")

    return {
        "schema_version": CONFIG_VERSION,
        "project_slug": project_slug,
        "active_source": active_source,
        "public_url_configured": bool(public_url),
        "local_cache_path": str(local_cache),
        "validated_asset_count": len(assets),
    }


def _resolve_repo_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    if str(path).startswith(("tools/", "projects/", "templates/", "docs/")):
        return (ROOT / path).resolve()
    return (base_dir / path).resolve()


def _require_str(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise ManifestSourceError(f"{field} must be a non-empty string")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate an OnBrand project manifest-source config.")
    parser.add_argument("--config", required=True, help="Path to manifest-source.json.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the validation summary.")
    args = parser.parse_args(argv)
    try:
        summary = validate_manifest_source_config(args.config)
    except (ManifestSourceError, ManifestError) as err:
        print(f"manifest source error: {err}", file=sys.stderr)
        return 3
    json.dump(summary, sys.stdout, indent=2 if args.pretty else None, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
