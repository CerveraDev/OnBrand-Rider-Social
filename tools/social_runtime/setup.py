"""First-run setup and updates for a workspace that builds social posts.

`setup` checks what the social runtime needs on this machine and installs the
browser tooling it renders with. `update` fetches the latest published version
of the workspace, which is how a user receives new layouts and a refreshed
image list together with the approvals that match it.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

from tools.asset_selection.manifest_source import validate_manifest_source_config

from .assets import load_social_assets


ROOT = Path(__file__).resolve().parents[2]
# Where the Playwright package is declared: the workspace root in a social-only
# workspace, the email render matrix in the full repository.
NODE_DIRS = (ROOT, ROOT / "tools" / "email_render_matrix")
MIN_PYTHON = (3, 10)


def node_dir() -> Path | None:
    return next((path for path in NODE_DIRS if (path / "package.json").is_file()), None)


def run_setup(project_dir: Path, *, out=sys.stdout) -> int:
    """Check and install what rendering needs. Returns 0 when the workspace is ready."""
    def say(message: str) -> None:
        print(message, file=out, flush=True)

    if sys.version_info < MIN_PYTHON:
        say(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is needed; this is {sys.version.split()[0]}.")
        return 1
    say(f"Python {sys.version.split()[0]}: ok")
    if not shutil.which("node") or not shutil.which("npm"):
        say("Node.js is not installed. Install the LTS version from https://nodejs.org, then run setup again.")
        return 1
    say(f"Node.js {_output(['node', '--version'])}: ok")
    packages = node_dir()
    if packages is None:
        say("This workspace has no package.json for the slide renderer; it is incomplete.")
        return 1
    if not (packages / "node_modules" / "playwright").is_dir():
        say("Installing the slide renderer (one time)...")
        if not _run(["npm", "ci", "--no-audit", "--no-fund"], packages, say):
            return 1
    say("Slide renderer: ok")
    say("Checking the browser used to render slides (the first run downloads about 150 MB)...")
    if not _run(["npx", "playwright", "install", "chromium"], packages, say):
        return 1
    say("Browser: ok")
    try:
        manifest = validate_manifest_source_config(project_dir / "manifest-source.json")["local_cache_path"]
        load_social_assets(manifest, project_dir / "asset-approvals.social.json", audience="in-house")
    except Exception as err:  # any failure here means the same thing to the user
        say(f"The image catalog is not usable: {err}")
        say("Posts made only from your own images still work. Run update to fetch the current image list.")
        return 1
    say("Image catalog: ok")
    say("Ready.")
    return 0


def run_update(project_dir: Path, *, out=sys.stdout) -> int:
    """Fetch the latest published workspace, then confirm it is still ready."""
    def say(message: str) -> None:
        print(message, file=out, flush=True)

    if not (ROOT / ".git").exists() or not shutil.which("git"):
        say("This copy was not installed with git, so it cannot update itself. Download the current version again.")
        return 1
    before = _output(["git", "rev-parse", "HEAD"], ROOT)
    if not _run(["git", "pull", "--ff-only"], ROOT, say):
        say("The update did not apply. If you changed files in this folder, move your changes aside and try again.")
        return 1
    after = _output(["git", "rev-parse", "HEAD"], ROOT)
    say("Already up to date." if before == after else f"Updated to {after[:7]}.")
    return run_setup(project_dir, out=out)


def _run(command: list[str], cwd: Path, say) -> bool:
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as err:
        say(f"Could not run {' '.join(command)}: {err}")
        return False
    if done.returncode != 0:
        say(f"{' '.join(command)} failed: {(done.stderr or done.stdout).strip()[-600:]}")
    return done.returncode == 0


def _output(command: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
