"""AI-generated images through Codex ImageGen, the only image generator the skill uses.

Codex has the image tool built in. Any other assistant, such as Claude Code, reaches
the same tool through the Codex command line: `codex exec` runs one turn that makes
the image with the built-in tool and saves it. It signs in with the user's ChatGPT
account, so no API key is involved. `setup` installs the command line into the
workspace when the machine has none and asks for the one-time sign-in.

Codex runs with `--ignore-user-config` so a model pinned in the user's own Codex
settings, which a ChatGPT sign-in may not allow from the command line, cannot stop it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from .crops import CropError, image_dimensions


ROOT = Path(__file__).resolve().parents[2]
TOOL_NAME = "Codex ImageGen"
# Where setup installs the Codex command line when the machine has none.
LOCAL_DIR = ROOT / ".cache" / "codex-cli"
LOCAL_BIN = LOCAL_DIR / "node_modules" / ".bin" / "codex"
# The command line bundled with the ChatGPT desktop app on a Mac.
APP_BINS = (
    Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"),
    Path("/Applications/Codex.app/Contents/Resources/codex"),
)
PACKAGE = "@openai/codex"
SHAPES = {"portrait": "4:5 portrait", "landscape": "3:2 landscape", "square": "1:1 square"}
TIMEOUT = 600


class ImageGenError(RuntimeError):
    """Raised when Codex ImageGen cannot run or did not save an image."""


def codex_binary() -> Path | None:
    """The Codex command line to use: the user's own, the workspace's, or the ChatGPT app's."""
    found = shutil.which("codex")
    for candidate in (Path(found) if found else None, LOCAL_BIN, *APP_BINS):
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def signed_in(binary: Path) -> bool:
    try:
        done = subprocess.run([str(binary), "login", "status"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and "logged in" in (done.stdout + done.stderr).lower()


def generate_image(prompt: str, *, output: Path, shape: str, based_on: list[str] | None = None,
                   project_dir: Path | None = None, runner=None) -> dict:
    """Make one image with Codex ImageGen and save it at `output`; return its record fields and size."""
    if shape not in SHAPES:
        raise ImageGenError(f"Shape must be one of: {', '.join(SHAPES)}")
    if output.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ImageGenError("Save the image as a .png or .jpg file")
    binary = codex_binary()
    if binary is None:
        raise ImageGenError("Codex is not installed. Run: python3 -m tools.social_runtime.cli setup --project <slug>")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        sources = [_download(name, Path(tmp), project_dir) for name in based_on or []]
        instruction = (
            f"Use your built-in image generation tool to {'edit the attached image' if sources else 'create one image'}. "
            f"{prompt.strip()} Make it {SHAPES[shape]}. "
            f"Save the result in the current directory as {output.name}. Do not write code, run scripts, or call any "
            "API: use only the built-in image generation tool, then copy the generated file here. "
            "Reply with only the file name."
        )
        command = [str(binary), "exec", "--ignore-user-config", "--skip-git-repo-check", "--ephemeral",
                   "-s", "workspace-write", "-C", str(output.parent), "--json"]
        for source in sources:
            command += ["-i", str(source)]
        # The prompt goes in on stdin: '-i' takes several files and would swallow a prompt after it.
        command.append("-")
        error = (runner or _run_codex)(command, instruction)
    if not output.is_file():
        raise ImageGenError(f"Codex ImageGen did not save an image{': ' + error if error else ''}")
    try:
        width, height = image_dimensions(output.read_bytes())
    except CropError as err:
        raise ImageGenError("Codex ImageGen saved a file that is not a PNG or JPEG") from err
    return {"generated": str(output), "prompt": prompt.strip(), "tool": TOOL_NAME,
            **({"based_on": list(based_on)} if based_on else {}), "width": width, "height": height}


def _run_codex(command: list[str], instruction: str) -> str | None:
    """Run one Codex turn; return its error message, or None when it finished."""
    try:
        done = subprocess.run(command, input=instruction, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ImageGenError(f"Codex ImageGen could not run: {err}") from err
    for line in reversed(done.stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") in ("turn.failed", "error"):
            message = (event.get("error") or {}).get("message") or event.get("message") or "unknown error"
            if "not logged in" in message.lower() or "401" in message:
                message += ". Sign in once with: python3 -m tools.social_runtime.cli setup --project <slug>"
            return message
    return None if done.returncode == 0 else (done.stderr.strip()[-400:] or "Codex exited with an error")


def _download(name: str, folder: Path, project_dir: Path | None) -> Path:
    """Fetch an approved catalog image by its exact file name, to give Codex as the base."""
    from .catalog import CatalogError, list_catalog

    try:
        matches = [image for image in list_catalog(project_dir, find=name) if image["name"] == name]
    except CatalogError as err:
        raise ImageGenError(f"The image catalog is not usable: {err}") from err
    if not matches or not matches[0]["link"]:
        raise ImageGenError(f"'{name}' is not an image in the catalog")
    target = folder / name
    try:
        with urllib.request.urlopen(matches[0]["link"], timeout=120) as response:
            target.write_bytes(response.read())
    except OSError as err:
        raise ImageGenError(f"Could not download '{name}' from the catalog: {err}") from err
    return target
