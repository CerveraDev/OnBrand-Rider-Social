"""Command-line entry point.

python3 -m tools.social_runtime.cli build --spec <path>
python3 -m tools.social_runtime.cli frames --project <slug>
python3 -m tools.social_runtime.cli render --package <directory>
python3 -m tools.social_runtime.cli gallery --project <slug>
python3 -m tools.social_runtime.cli images --project <slug> [--list] [--find <text>]
python3 -m tools.social_runtime.cli layouts --project <slug>
python3 -m tools.social_runtime.cli post --brief <path>
python3 -m tools.social_runtime.cli press-logo --url <article address>
python3 -m tools.social_runtime.cli setup --project <slug>
python3 -m tools.social_runtime.cli update --project <slug>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from .assets import SocialAssetError
from .brief import BriefError, compose_spec, describe_layouts
from .catalog import CatalogError, list_catalog, write_catalog
from .frames import FRAMES_FILE, LIMITS_FILE, FrameError, build_frame_definitions, load_text_limits
from .gallery import GalleryError, write_gallery
from .press_logo import LOGO_DIR, PressLogoError, find_press_logo
from .render import RenderError, render_package
from .runtime import ROOT, SocialRuntimeError, build_social
from .schema import SocialSpecError
from .setup import run_setup, run_update


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build an OnBrand social post or carousel package.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Validate a social spec and build its package.")
    build.add_argument("--spec", required=True, help="Path to the canonical social spec JSON.")
    frames = commands.add_parser("frames", help="Regenerate frame definitions from a project's scaffold catalog.")
    frames.add_argument("--project", required=True, help="Project slug under projects/.")
    render = commands.add_parser("render", help="Render a built package's slides from the project scaffold.")
    render.add_argument("--package", required=True, help="Path to a built social package directory.")
    gallery = commands.add_parser("gallery", help="Write a project's layout gallery and open it in the browser.")
    gallery.add_argument("--project", required=True, help="Project slug under projects/.")
    gallery.add_argument("--no-open", action="store_true", help="Write the gallery without opening it.")
    images = commands.add_parser("images", help="Write a project's image catalog page and open it in the browser.")
    images.add_argument("--project", required=True, help="Project slug under projects/.")
    images.add_argument("--no-open", action="store_true", help="Write the page without opening it.")
    images.add_argument("--list", action="store_true", help="Print the catalog as text instead of writing the page.")
    images.add_argument("--find", help="With --list, keep images whose name or subject contains this text.")
    images.add_argument("--links", action="store_true", help="With --list, add each image's download link.")
    layouts = commands.add_parser("layouts", help="Print a project's post types and layouts, for writing a brief.")
    layouts.add_argument("--project", required=True, help="Project slug under projects/.")
    post = commands.add_parser("post", help="Build and render a post from a brief, then open its feed preview.")
    post.add_argument("--brief", required=True, help="Path to a post brief JSON.")
    post.add_argument("--no-open", action="store_true", help="Do not open the feed preview.")
    press_logo = commands.add_parser("press-logo", help="Find a publication's logo on one of its article pages.")
    press_logo.add_argument("--url", required=True, help="The article's web address.")
    press_logo.add_argument("--output", help=f"Folder to save the logo in (default: {LOGO_DIR}).")
    setup = commands.add_parser("setup", help="Check this machine and install what rendering needs.")
    setup.add_argument("--project", required=True, help="Project slug under projects/.")
    update = commands.add_parser("update", help="Fetch the latest published layouts, image list, and approvals.")
    update.add_argument("--project", required=True, help="Project slug under projects/.")
    args = parser.parse_args(argv)
    if args.command == "setup":
        return run_setup(ROOT / "projects" / args.project)
    if args.command == "update":
        return run_update(ROOT / "projects" / args.project)
    if args.command == "images":
        if args.list:
            return _list_images(ROOT / "projects" / args.project, args.find, args.links)
        return _images(ROOT / "projects" / args.project, show=not args.no_open)
    if args.command == "layouts":
        return _layouts(ROOT / "projects" / args.project)
    if args.command == "post":
        return _post(Path(args.brief), show=not args.no_open)
    if args.command == "press-logo":
        return _press_logo(args.url, Path(args.output) if args.output else ROOT / LOGO_DIR)
    if args.command == "gallery":
        return _gallery(ROOT / "projects" / args.project, show=not args.no_open)
    if args.command == "frames":
        return _write_frames(ROOT / "projects" / args.project)
    if args.command == "render":
        return _render(args.package)
    try:
        result = build_social(args.spec)
    except (SocialSpecError, SocialRuntimeError, OSError, json.JSONDecodeError) as err:
        print(f"social build refused: {err}", file=sys.stderr)
        return 2
    json.dump(
        {
            "passed": result.qa.passed,
            "package_dir": str(result.package_dir),
            "zip_path": str(result.zip_path) if result.zip_path else None,
            "qa_report": str(result.qa_report),
            "warnings": result.qa.warnings,
            "failed_checks": [c["name"] for c in result.qa.checks if not c["passed"]],
        },
        sys.stdout, indent=2,
    )
    sys.stdout.write("\n")
    return 0 if result.qa.passed else 1


def _press_logo(url: str, output_dir: Path) -> int:
    try:
        result = find_press_logo(url, output_dir=output_dir)
    except PressLogoError as err:
        print(f"press logo search refused: {err}", file=sys.stderr)
        return 2
    if result["found"]:
        print(f"Found the {result['outlet']} logo in the {result['where']}.")
        print(f"Logo file: {result['file']}")
        print(f"Look at it first: {result['preview']}")
        return 0
    print(f"No logo found for {result['outlet']}: {result['reason']}. Leave the logo area empty.")
    return 1


def _render(package: str) -> int:
    try:
        result = render_package(package)
    except RenderError as err:
        print(f"social render refused: {err}", file=sys.stderr)
        return 2
    json.dump(
        {
            "passed": result.passed,
            "slides": [str(path) for path in result.slides],
            "zip_path": str(result.zip_path) if result.zip_path else None,
            "render_report": str(result.report),
            "simulator": str(result.simulator) if result.simulator else None,
            "warnings": result.warnings,
            "failed_checks": [f"{c['name']}: {c['message']}" for c in result.checks if not c["passed"]],
        },
        sys.stdout, indent=2,
    )
    sys.stdout.write("\n")
    return 0 if result.passed else 1


def _gallery(project_dir: Path, *, show: bool) -> int:
    try:
        path = write_gallery(project_dir)
    except GalleryError as err:
        print(f"layout gallery refused: {err}", file=sys.stderr)
        return 2
    if show:
        webbrowser.open(path.resolve().as_uri())
    print(f"Layout gallery written to {path.relative_to(ROOT)}" + (" and opened in the browser" if show else ""))
    return 0


def _images(project_dir: Path, *, show: bool) -> int:
    try:
        result = write_catalog(project_dir)
    except CatalogError as err:
        print(f"image catalog refused: {err}", file=sys.stderr)
        return 2
    if show:
        webbrowser.open(result.path.resolve().as_uri())
    print(f"Image catalog with {result.images} images written to {result.path.relative_to(ROOT)}"
          + (" and opened in the browser" if show else ""))
    if result.without_preview:
        print(f"{len(result.without_preview)} image(s) have no preview yet; run the command again to retry: "
              + ", ".join(result.without_preview), file=sys.stderr)
    return 0


def _list_images(project_dir: Path, find: str | None, links: bool = False) -> int:
    try:
        images = list_catalog(project_dir, find=find)
    except CatalogError as err:
        print(f"image catalog refused: {err}", file=sys.stderr)
        return 2
    for image in images:
        print(f"{image['name']}\t{image['subject']}\t{image['shape']}\t{image['use']}" + (f"\t{image['link']}" if links else ""))
    print(f"{len(images)} image(s)", file=sys.stderr)
    return 0


def _layouts(project_dir: Path) -> int:
    try:
        described = describe_layouts(project_dir)
    except BriefError as err:
        print(f"layouts refused: {err}", file=sys.stderr)
        return 2
    print("POST TYPES")
    for post_type in described["post_types"]:
        low, high = post_type["slides"]
        order = ", then ".join(
            f"{step['count'][0]}-{step['count'][1]} of {step['layouts']}" + "".join(
                f" (at most {most} of {layouts})" for layouts, most in step.get("at_most", {}).items()
            ) for step in post_type["order"]
        )
        print(f"{post_type['code']}  {post_type['label']}: {low}-{high} slide(s); in order: {order}")
    print("\nLAYOUTS  (image areas with the shape each needs; text with max lines and approximate characters)")
    for layout, parts in described["layouts"].items():
        images = ", ".join(f"{slot} ({shape})" for slot, shape in parts["images"].items()) or "none"
        text = ", ".join(
            f"{slot} ({rule['max_lines']} lines, ~{rule['about_chars']} chars"
            + (", *italic* allowed" if rule.get("italic_word") else "") + (", optional" if rule.get("optional") else "") + ")"
            for slot, rule in parts["text"].items()
        ) or "none"
        extras = "".join(
            f"  |  {label}: {value}" for label, value in (
                ("fixed text", ", ".join(f"{slot} \"{words}\"" for slot, words in parts["fixed"].items())),
                ("can hide", ", ".join(parts["can_hide"])),
                ("AI-generated image", "yes" if parts["ai_images"] else "no" if parts["images"] else ""),
            ) if value
        )
        print(f"{layout}  images: {images}  |  text: {text}{extras}")
    return 0


def _post(brief_path: Path, *, show: bool) -> int:
    """Brief to spec, build, render, and feed preview, stopping at the first step that fails."""
    try:
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        spec = compose_spec(brief, brief_dir=brief_path.resolve().parent)
        spec_path = ROOT / "campaign-output" / "social" / "specs" / f"{spec['campaign']['slug']}.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        built = build_social(spec_path)
    except (BriefError, CatalogError, SocialSpecError, SocialRuntimeError, SocialAssetError, OSError,
            json.JSONDecodeError) as err:
        print(f"post refused: {err}", file=sys.stderr)
        return 2
    summary = {
        "passed": built.qa.passed, "package_dir": str(built.package_dir), "spec": str(spec_path),
        "post_type": spec["composition"]["template"], "slides": [], "simulator": None, "zip_path": None,
        "warnings": list(built.qa.warnings), "adjustments": [],
        "failed_checks": [c["name"] for c in built.qa.checks if not c["passed"]],
    }
    if built.qa.passed:
        try:
            rendered = render_package(built.package_dir)
        except RenderError as err:
            print(f"post refused: {err}", file=sys.stderr)
            return 2
        summary.update(
            passed=rendered.passed, slides=[str(path) for path in rendered.slides],
            simulator=str(rendered.simulator) if rendered.simulator else None,
            zip_path=str(rendered.zip_path) if rendered.zip_path else None,
            warnings=summary["warnings"] + rendered.warnings, adjustments=rendered.adjustments,
            failed_checks=[f"{c['name']}: {c['message']}" for c in rendered.checks if not c["passed"]],
        )
        if show and rendered.simulator:
            webbrowser.open(rendered.simulator.resolve().as_uri())
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if summary["passed"] else 1


def _write_frames(project_dir: Path) -> int:
    try:
        catalog = json.loads((project_dir / "social" / "scaffold" / "frame-catalog.json").read_text(encoding="utf-8"))
        project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"frame generation refused: {err}", file=sys.stderr)
        return 2
    path = project_dir / "social" / "templates" / FRAMES_FILE
    try:
        definitions = build_frame_definitions(catalog, logo_label=f"{project['project_name']} logo",
                                              limits=load_text_limits(project_dir / "social" / "scaffold" / LIMITS_FILE))
    except FrameError as err:
        print(f"frame generation refused: {err}", file=sys.stderr)
        return 2
    path.write_text(json.dumps(definitions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(definitions['frames'])} frame definitions written to {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
