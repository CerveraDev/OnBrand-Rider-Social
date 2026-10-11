"""Image catalog page: every image approved for a project's social posts.

Reads the same approved catalog a build resolves images from and writes one
browsable page, grouped by subject, with a small preview of each image. The
originals are tens of megabytes each, so previews are made once and kept. The
page links to the originals, so it is written under `campaign-output/`, which is
not committed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from tools.asset_selection.manifest_source import validate_manifest_source_config

from .assets import CROP_ROLE, SocialAssetError, load_social_assets
from .profile import ProfileError, load_profile


ROOT = Path(__file__).resolve().parents[2]
THUMBNAILER = Path(__file__).with_name("make_thumbnails.cjs")
CATALOG_FILE = "catalog.html"
THUMBS_DIR = "thumbs"
THUMBS_INDEX = "index.json"
THUMB_WIDTH = 560
THUMB_QUALITY = 80
UPPERCASE_WORDS = {"rh", "3d"}


class CatalogError(ValueError):
    """Raised when a project's image catalog page cannot be built."""


@dataclass(frozen=True)
class CatalogResult:
    path: Path
    images: int
    without_preview: list[str]


def write_catalog(
    project_dir: Path | str,
    *,
    manifest_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    thumbnailer=None,
) -> CatalogResult:
    """Write the catalog page for the project's in-house social catalog."""
    project_dir = Path(project_dir)
    try:
        if manifest_path is None:
            manifest_path = validate_manifest_source_config(project_dir / "manifest-source.json")["local_cache_path"]
        assets = load_social_assets(manifest_path, project_dir / "asset-approvals.social.json", audience="in-house")
        profile = load_profile(project_dir)
        project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, SocialAssetError, ProfileError) as err:
        raise CatalogError(f"The image catalog could not be built: {err}") from err
    approved = sorted(
        (asset for asset in assets if asset.get("social_roles") and asset.get("media_type") == "image"),
        key=lambda asset: (asset["social_cluster"], asset["filename"].lower()),
    )
    if not approved:
        raise CatalogError("No images are approved for social use in this project")
    output_dir = Path(output_dir) if output_dir else default_output_dir(project["project_slug"])
    thumbs_dir = output_dir / THUMBS_DIR
    names, index = _ensure_previews(approved, thumbs_dir, thumbnailer)

    images = []
    without_preview = []
    for asset in approved:
        thumb = names[asset["filename"]]
        size = index.get(thumb) if (thumbs_dir / thumb).is_file() else None
        if size is None:
            without_preview.append(asset["filename"])
        images.append({
            "name": asset["filename"], "group": asset["social_cluster"], "shape": asset["orientation"],
            "crop_only": asset["social_roles"] == [CROP_ROLE],
            "thumb": f"{THUMBS_DIR}/{thumb}" if size else None,
            "width": size["width"] if size else None, "height": size["height"] if size else None,
            "full": asset["public_url"], "rights": asset.get("third_party_rights") or None,
        })
    groups = sorted({image["group"] for image in images})
    data = {"groups": [{"key": key, "label": _label(key)} for key in groups], "images": images}
    name = escape(profile["official_name"] or project["project_name"])
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    path = output_dir / CATALOG_FILE
    path.write_text(_PAGE.replace("__NAME__", name).replace("__DATA__", payload), encoding="utf-8")
    return CatalogResult(path, len(images), without_preview)


def list_catalog(project_dir: Path | str, *, manifest_path: Path | str | None = None, find: str | None = None) -> list[dict]:
    """The approved catalog as plain records, without previews: name, subject, shape, and how it may be used."""
    project_dir = Path(project_dir)
    try:
        if manifest_path is None:
            manifest_path = validate_manifest_source_config(project_dir / "manifest-source.json")["local_cache_path"]
        assets = load_social_assets(manifest_path, project_dir / "asset-approvals.social.json", audience="in-house")
    except (OSError, ValueError, SocialAssetError) as err:
        raise CatalogError(f"The image catalog could not be read: {err}") from err
    needle = (find or "").strip().lower()
    return [
        {
            "name": asset["filename"], "subject": asset["social_cluster"], "shape": asset["orientation"],
            "use": "needs-crop" if asset["social_roles"] == [CROP_ROLE] else "ready",
        }
        for asset in sorted(assets, key=lambda asset: (asset.get("social_cluster") or "", asset["filename"].lower()))
        if asset.get("social_roles") and asset.get("media_type") == "image"
        and needle in f"{asset['filename']} {asset['social_cluster']}".lower()
    ]


def default_output_dir(project_slug: str) -> Path:
    return ROOT / "campaign-output" / "social" / f"{project_slug}-image-catalog"


def image_sizes(assets: list[dict], *, output_dir: Path | str, thumbnailer=None) -> dict[str, tuple[int, int]]:
    """Pixel sizes of catalog images, measured while making their previews and kept with them."""
    names, index = _ensure_previews(assets, Path(output_dir) / THUMBS_DIR, thumbnailer)
    return {
        asset["filename"]: (index[names[asset["filename"]]]["width"], index[names[asset["filename"]]]["height"])
        for asset in assets if names[asset["filename"]] in index
    }


def _ensure_previews(assets: list[dict], thumbs_dir: Path, thumbnailer) -> tuple[dict[str, str], dict]:
    """Make any missing previews; return each asset's preview name and the size index."""
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    index_path = thumbs_dir / THUMBS_INDEX
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {}
    names = {asset["filename"]: hashlib.sha256(asset["filename"].encode()).hexdigest()[:16] + ".jpg" for asset in assets}
    wanted = [
        asset for asset in assets
        if names[asset["filename"]] not in index or not (thumbs_dir / names[asset["filename"]]).is_file()
    ]
    if wanted:
        job = {
            "width": THUMB_WIDTH, "quality": THUMB_QUALITY,
            "items": [{"url": asset["public_url"], "output": str(thumbs_dir / names[asset["filename"]])} for asset in wanted],
        }
        made = (thumbnailer or _run_thumbnailer)(job)["items"]
        for asset, result in zip(wanted, made):
            if not result.get("error"):
                index[names[asset["filename"]]] = {"width": result["width"], "height": result["height"]}
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return names, index


def _label(key: str) -> str:
    words = [word.upper() if word in UPPERCASE_WORDS else word for word in key.split("-")]
    text = " ".join(words)
    return text[0].upper() + text[1:]


def _run_thumbnailer(job: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        job_path = Path(tmp) / "job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        try:
            done = subprocess.run(["node", str(THUMBNAILER), "--job", str(job_path)],
                                  stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=3600)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise CatalogError(f"The preview maker could not run: {err}") from err
    if done.returncode != 0:
        raise CatalogError("The preview maker failed")
    return json.loads(done.stdout)


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ · image catalog</title>
<style>
  :root { --page: #e9e7e2; --card: #ffffff; --ink: #1c1c1c; --muted: #6b6b6b; --line: #d9d6cf; --accent: #111; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
         padding: 28px 24px 150px; }
  header, main { max-width: 1320px; margin: 0 auto; }
  h1 { font: 400 30px/1.15 Georgia, "Times New Roman", serif; margin: 0 0 6px; }
  header p { margin: 0; color: var(--muted); max-width: 72ch; }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; align-items: center; }
  .tabs span { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; width: 62px; }
  button { font: inherit; color: var(--ink); cursor: pointer; }
  .tabs button, .pill { background: transparent; border: 1px solid var(--muted); border-radius: 999px; padding: 5px 14px; }
  .tabs button[aria-pressed="true"], .solid { background: var(--accent); border: 1px solid var(--accent); color: #fff;
         border-radius: 999px; padding: 5px 14px; }
  #search { font: inherit; padding: 6px 12px; border: 1px solid var(--muted); border-radius: 999px; background: transparent;
            color: var(--ink); min-width: 240px; }
  h2 { font: 400 20px Georgia, "Times New Roman", serif; margin: 30px 0 12px; }
  h2 small { font: 13px -apple-system, "Helvetica Neue", Arial, sans-serif; color: var(--muted); margin-left: 6px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 18px; align-items: start; }
  .card { background: var(--card); border-radius: 10px; overflow: hidden; box-shadow: 0 1px 2px rgba(0, 0, 0, .08); }
  .card.picked { outline: 2px solid var(--accent); }
  .shot { display: block; width: 100%; padding: 0; border: 0; background: #d5d2cb; cursor: zoom-in; }
  .shot img { display: block; width: 100%; height: auto; }
  .shot .none { display: grid; place-items: center; aspect-ratio: 4 / 3; color: var(--muted); font-size: 12px; }
  .body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 6px; }
  .name { font-weight: 600; overflow-wrap: anywhere; font-size: 13px; }
  .facts { color: var(--muted); font-size: 12.5px; }
  .tag { display: inline-block; border-radius: 4px; padding: 1px 6px; font-size: 11.5px; background: #e7f0e4; color: #24521b; }
  .tag.crop { background: #f3ead9; color: #6b4a12; }
  .body .pill { align-self: flex-start; margin-top: 4px; }
  .empty { color: var(--muted); margin-top: 30px; }
  dialog { border: 0; border-radius: 12px; padding: 0; max-width: min(1000px, 94vw); color: var(--ink); }
  dialog::backdrop { background: rgba(0, 0, 0, .6); }
  dialog img { display: block; max-width: 100%; max-height: 72vh; margin: 0 auto; }
  dialog .info { padding: 16px 20px 18px; }
  dialog .row { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; align-items: center; }
  dialog a { color: var(--ink); }
  .tray { position: fixed; left: 0; right: 0; bottom: 0; background: var(--card); border-top: 1px solid var(--line);
          box-shadow: 0 -6px 24px rgba(0, 0, 0, .12); padding: 12px 24px 14px; }
  .tray[hidden] { display: none; }
  .tray .inner { max-width: 1320px; margin: 0 auto; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  .strip { display: flex; gap: 8px; overflow-x: auto; flex: 1; min-width: 200px; padding: 4px 2px; }
  .chip { position: relative; flex: none; }
  .chip img { height: 64px; width: auto; display: block; border-radius: 4px; }
  .chip button { position: absolute; top: -4px; right: -4px; width: 18px; height: 18px; border-radius: 50%; border: 0;
                 background: var(--accent); color: #fff; font-size: 12px; line-height: 18px; padding: 0; }
  .tray input { flex: 1 1 320px; font: inherit; padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px;
                background: var(--page); color: var(--ink); }
</style>
</head>
<body>
<header>
  <h1>__NAME__ image catalog</h1>
  <p>Every official image approved for social posts. Click an image to see it larger. Use “Add to my post” to collect
     images; the bar at the bottom gives you a line to paste into your request. Images marked “Needs a crop” are wide
     pictures that are cut down to fit a slide.</p>
  <div class="tabs" id="groups"></div>
  <div class="tabs" id="shapes"></div>
  <div class="tabs"><span>Find</span><input id="search" type="search" placeholder="Part of a file name" aria-label="Find by file name"></div>
</header>
<main id="main"></main>
<dialog id="dialog"><img id="d-img" alt=""><div class="info" id="d-info"></div></dialog>
<div class="tray" id="tray" hidden><div class="inner">
  <div class="strip" id="strip"></div>
  <input id="request" readonly aria-label="Text to paste into your request">
  <button class="solid" id="copy" type="button">Copy</button><button class="pill" id="clear" type="button">Clear</button>
</div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
  const data = JSON.parse(document.getElementById('data').textContent);
  const $ = (id) => document.getElementById(id);
  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.filter((child) => child !== null));
    return node;
  };
  const byName = Object.fromEntries(data.images.map((image) => [image.name, image]));
  const state = { group: 'all', shape: 'all', text: '' };
  const picked = [];

  const shown = () => data.images.filter((image) =>
    (state.group === 'all' || image.group === state.group) && (state.shape === 'all' || image.shape === state.shape)
    && image.name.toLowerCase().includes(state.text));
  const facts = (image) => [image.shape[0].toUpperCase() + image.shape.slice(1),
    image.width ? `${image.width} × ${image.height} px` : null].filter(Boolean).join(' · ');
  const tag = (image) => el('span', { className: 'tag' + (image.crop_only ? ' crop' : ''),
    textContent: image.crop_only ? 'Needs a crop' : 'Ready to use' });

  function tabs(target, label, key, options) {
    $(target).replaceChildren(el('span', { textContent: label }), ...options.map((option) => {
      const count = data.images.filter((image) => option.key === 'all' || image[key] === option.key).length;
      const button = el('button', { type: 'button', textContent: `${option.label} (${count})` });
      button.setAttribute('aria-pressed', String(state[key] === option.key));
      button.onclick = () => { state[key] = option.key; render(); };
      return button;
    }));
  }

  function render() {
    tabs('groups', 'Subject', 'group', [{ key: 'all', label: 'All' }, ...data.groups]);
    tabs('shapes', 'Shape', 'shape', [{ key: 'all', label: 'All' }, { key: 'portrait', label: 'Portrait' },
      { key: 'square', label: 'Square' }, { key: 'landscape', label: 'Landscape' }]);
    const images = shown();
    $('main').replaceChildren(...(images.length ? data.groups.flatMap((group) => {
      const mine = images.filter((image) => image.group === group.key);
      return mine.length ? [
        el('h2', {}, group.label, el('small', { textContent: `${mine.length} image${mine.length > 1 ? 's' : ''}` })),
        el('div', { className: 'grid' }, ...mine.map(card)),
      ] : [];
    }) : [el('p', { className: 'empty', textContent: 'No images match.' })]));
  }

  function card(image) {
    const shot = el('button', { className: 'shot', type: 'button' }, image.thumb
      ? el('img', { src: image.thumb, alt: image.name, loading: 'lazy', width: image.width, height: image.height })
      : el('div', { className: 'none', textContent: 'Preview not available' }));
    shot.setAttribute('aria-label', `See ${image.name} larger`);
    shot.onclick = () => detail(image);
    const add = el('button', { className: 'pill', type: 'button', textContent: 'Add to my post' });
    add.onclick = () => pick(image.name);
    return el('div', { className: 'card' + (picked.includes(image.name) ? ' picked' : '') }, shot,
      el('div', { className: 'body' }, el('div', { className: 'name', textContent: image.name }),
        el('div', { className: 'facts' }, facts(image)), el('div', {}, tag(image)), add));
  }

  function detail(image) {
    $('d-img').hidden = !image.thumb;
    if (image.thumb) $('d-img').src = image.thumb;
    $('d-img').alt = image.name;
    const add = el('button', { className: 'solid', type: 'button', textContent: 'Add to my post' });
    add.onclick = () => { pick(image.name); $('dialog').close(); };
    const close = el('button', { className: 'pill', type: 'button', textContent: 'Close' });
    close.onclick = () => $('dialog').close();
    const full = el('a', { href: image.full, target: '_blank', rel: 'noopener', textContent: 'Open the full-size original' });
    $('d-info').replaceChildren(...[el('div', { className: 'name', textContent: image.name }),
      el('div', { className: 'facts' }, facts(image), ' · ', tag(image)),
      image.rights ? el('div', { className: 'facts', textContent: `Third-party rights: ${image.rights}` }) : null,
      el('div', { className: 'row' }, add, close, full)].filter(Boolean));
    $('dialog').showModal();
  }
  $('dialog').addEventListener('click', (event) => { if (event.target === $('dialog')) $('dialog').close(); });

  function pick(name) {
    if (!picked.includes(name)) picked.push(name);
    tray();
    render();
  }

  function tray() {
    $('tray').hidden = !picked.length;
    $('strip').replaceChildren(...picked.map((name, i) => {
      const remove = el('button', { type: 'button', textContent: '×' });
      remove.setAttribute('aria-label', `Remove ${name}`);
      remove.onclick = () => { picked.splice(i, 1); tray(); render(); };
      const image = byName[name];
      return el('div', { className: 'chip', title: name },
        image.thumb ? el('img', { src: image.thumb, alt: name }) : el('span', { textContent: name }), remove);
    }));
    $('request').value = picked.length > 1
      ? `Use these catalog images in this order: ${picked.join(', ')}.` : `Use the catalog image ${picked[0] || ''}.`;
  }
  $('clear').onclick = () => { picked.length = 0; tray(); render(); };
  $('copy').onclick = async () => {
    try {
      await navigator.clipboard.writeText($('request').value);
    } catch (error) {
      $('request').select();
      document.execCommand('copy');
    }
    $('copy').textContent = 'Copied';
    setTimeout(() => { $('copy').textContent = 'Copy'; }, 1500);
  };
  $('search').oninput = () => { state.text = $('search').value.trim().toLowerCase(); render(); $('search').focus(); };

  render();
</script>
</body>
</html>
"""
