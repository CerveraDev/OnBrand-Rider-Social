"""The photos of a press article, saved for its press carousel.

A press carousel shows the article's own pictures. Rather than pick from the catalog,
the skill gives the article's address: the page is opened in the slide renderer's
browser, the pictures in the article body and its share image are downloaded, and
saved under `campaign-output/social/article-images/`. Each saved picture is reported
with its size and shape, so the skill can match it to an image area. When the article
has no usable pictures, nothing is saved and the skill asks the user what to use.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlparse

from .crops import CropError, image_dimensions
from .supplied import image_shape


FINDER = Path(__file__).with_name("find_article_images.cjs")
ARTICLE_IMAGE_DIR = Path("campaign-output") / "social" / "article-images"
# A picture whose longer side is shorter than this is a thumbnail or an icon, too
# small for any image area.
MIN_SIDE = 600


class PressImagesError(RuntimeError):
    """Raised when the article image finder cannot run."""


def find_article_images(url: str, *, output_dir: Path, finder=None) -> dict:
    """Save an article's pictures; return each one's file, size, shape, and caption."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PressImagesError(f"Not a web address: {url}")
    host = re.sub(r"^www\.", "", parsed.hostname.lower())
    last = [part for part in parsed.path.split("/") if part]
    slug = re.sub(r"[^a-z0-9]+", "-", (last[-1] if last else "front-page").lower()).strip("-")[:60] or "article"
    folder = output_dir / f"{host}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("image-*"):
        old.unlink()
    job = {"url": url, "output_stem": str(folder / "image")}
    result = (finder or _run_finder)(job)
    images = []
    for image in result.get("images", []):
        path = Path(image["file"])
        try:
            width, height = image_dimensions(path.read_bytes())
        except (OSError, CropError):
            path.unlink(missing_ok=True)
            continue
        if max(width, height) < MIN_SIDE:
            path.unlink(missing_ok=True)
            continue
        images.append({**image, "width": width, "height": height, "shape": image_shape(width, height)})
    return {"outlet": host, "folder": str(folder), "images": images,
            "reason": None if images else result.get("reason") or "no usable pictures were found"}


def _run_finder(job: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        job_path = Path(tmp) / "job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        try:
            done = subprocess.run(["node", str(FINDER), "--job", str(job_path)],
                                  capture_output=True, text=True, timeout=240)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise PressImagesError(f"The article image finder could not run: {err}") from err
    if done.returncode != 0:
        raise PressImagesError(f"The article image finder failed: {done.stderr.strip() or 'no error output'}")
    return json.loads(done.stdout)
