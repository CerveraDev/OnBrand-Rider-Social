#!/usr/bin/env python3
"""CLI for selecting campaign asset candidates from an OnBrand manifest."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from .selector import ManifestError, SelectionNeeds, load_manifest, select_candidates
except ImportError:  # Allow direct execution: python tools/asset_selection/select_assets.py
    from selector import ManifestError, SelectionNeeds, load_manifest, select_candidates


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Local master manifest JSON path.")
    parser.add_argument(
        "--media-type",
        choices=("any", "image", "pdf"),
        default="any",
        help="Required asset media type.",
    )
    parser.add_argument(
        "--approved-for",
        action="append",
        default=[],
        help="Required approved_for value. Repeat or comma-separate for multiple values.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Desired category. Repeat or comma-separate for overlap matching.",
    )
    parser.add_argument(
        "--orientation",
        default="",
        help="Desired orientation when metadata is available, such as landscape or portrait.",
    )
    parser.add_argument("--limit", type=int, default=6, help="Maximum shortlist size.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)

    try:
        needs = SelectionNeeds(
            media_type=args.media_type,
            approved_for=split_values(args.approved_for),
            categories=split_values(args.category),
            orientation=args.orientation.strip().lower(),
            limit=args.limit,
        )
        assets = load_manifest(args.manifest)
        result = select_candidates(assets, needs)
    except (ManifestError, ValueError) as err:
        print(f"asset selection error: {err}", file=sys.stderr)
        return 3

    json.dump(result, sys.stdout, indent=2 if args.pretty else None, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result["matched_assets"] else 4


def split_values(values):
    split = []
    for value in values:
        split.extend(part.strip() for part in value.split(","))
    return tuple(part for part in split if part)


if __name__ == "__main__":
    raise SystemExit(main())
