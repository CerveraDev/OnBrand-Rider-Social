"""A publication's logo, found on one of its article pages.

Press posts show the outlet's logo. Rather than ask for a file, the skill gives the
article's address: the page is opened in the slide renderer's browser, the logo is
taken from its header or navigation, and saved under `campaign-output/social/logos/`.
When the page has no usable logo, nothing is saved and the logo area stays empty.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlparse


FINDER = Path(__file__).with_name("find_press_logo.cjs")
LOGO_DIR = Path("campaign-output") / "social" / "logos"


class PressLogoError(RuntimeError):
    """Raised when the logo finder cannot run."""


def find_press_logo(url: str, *, output_dir: Path, finder=None) -> dict:
    """Look for the publication's logo on an article page; return what was found and where it was saved."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PressLogoError(f"Not a web address: {url}")
    host = re.sub(r"^www\.", "", parsed.hostname.lower())
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob(f"{host}.*"):
        old.unlink()
    for old in output_dir.glob(f"{host}-preview.png"):
        old.unlink()
    job = {"url": url, "output_stem": str(output_dir / host)}
    result = (finder or _run_finder)(job)
    result["outlet"] = host
    return result


def _run_finder(job: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        job_path = Path(tmp) / "job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        try:
            done = subprocess.run(["node", str(FINDER), "--job", str(job_path)],
                                  capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise PressLogoError(f"The logo finder could not run: {err}") from err
    if done.returncode != 0:
        raise PressLogoError(f"The logo finder failed: {done.stderr.strip() or 'no error output'}")
    return json.loads(done.stdout)
