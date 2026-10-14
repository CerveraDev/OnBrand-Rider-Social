"""Layout gallery: one page showing every frame of a project's social scaffold.

Written next to the scaffold so it can use the imported previews. Each layout is
shown with what it holds (photos, text and its limits, logo, border) and which
post types accept it; layouts can be collected into a sequence, which the page
checks against the project's templates. Everything shown is read from the frame
catalog, the frame definitions, and the templates, so the page is regenerated,
never edited.
"""

from __future__ import annotations

from html import escape
import json
from pathlib import Path

from .frames import FRAMES_FILE, FrameError, load_frames
from .generated import GeneratedImageError, accepts, load_policy
from .profile import ProfileError, load_profile


GALLERY_FILE = "gallery.html"
FAMILY_LABELS = {"post": "Single posts", "carousel": "Carousel slides", "gallery": "Photo gallery slides",
                 "press": "Press carousel"}
SLOT_LABELS = {"heading": "Heading", "subheading": "Subheading", "copy": "Body copy", "footer-line": "Footer line"}


class GalleryError(ValueError):
    """Raised when a project's scaffold cannot be turned into a gallery."""


def write_gallery(project_dir: Path | str) -> Path:
    """Write `social/scaffold/gallery.html` for the project and return its path."""
    project_dir = Path(project_dir)
    scaffold_dir = project_dir / "social" / "scaffold"
    templates_dir = project_dir / "social" / "templates"
    try:
        catalog = json.loads((scaffold_dir / "frame-catalog.json").read_text(encoding="utf-8"))
        definitions = load_frames(templates_dir / FRAMES_FILE)["frames"]
        templates = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(templates_dir.glob("*.json")) if path.name != FRAMES_FILE
        ]
        profile = load_profile(project_dir)
        generated_policy = load_policy(project_dir)
        project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, FrameError, ProfileError, GeneratedImageError) as err:
        raise GalleryError(f"The layout gallery could not be built: {err}") from err

    frames = []
    for entry in catalog["frames"]:
        definition = definitions.get(entry["id"])
        if definition is None or not (scaffold_dir / "previews" / f"{entry['id']}.jpg").is_file():
            raise GalleryError(f"Frame {entry['id']} has no definition or preview; re-run the scaffold import")
        frames.append(_frame(entry, definition, templates, accepts(generated_policy, entry["id"])))
    data = {
        "families": [
            {"key": key, "label": label} for key, label in FAMILY_LABELS.items()
            if any(frame["family"] == key for frame in frames)
        ],
        "frames": frames,
        "templates": [
            {
                "code": template["code"], "label": template["label"],
                "min": template["min_slides"], "max": template["max_slides"],
                "rule": _rule(template), "sequence": template["sequence"],
            }
            for template in templates
        ],
    }
    name = escape(profile["official_name"] or project["project_name"])
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    path = scaffold_dir / GALLERY_FILE
    path.write_text(_PAGE.replace("__NAME__", name).replace("__DATA__", payload), encoding="utf-8")
    return path


def _frame(entry: dict, definition: dict, templates: list[dict], ai_images: bool) -> dict:
    observed = entry["observed"]
    placed = {slot["slot"]: slot for slot in observed["text_slots"]}
    overlays = {slot["slot"]: slot.get("overlay") or {} for slot in observed["image_slots"]}
    layout = []
    if observed["border"]:
        layout.append("Framed with a border")
    else:
        layout.append("Edge to edge, no border")
    logo = observed["logo"]
    layout.append(f"Logo {_position(logo['box'], entry['canvas'])}" if logo else "No logo")
    overlay = overlays.get("background", {})
    if overlay.get("type") == "linear-scrim":
        layout.append(f"Photo darkened at the {overlay['darkest_at']} so text stays readable")
    elif overlay.get("type") == "radial-scrim":
        layout.append("Photo darkened in the centre so text stays readable")

    if any(slot["fit"] == "contain" for slot in definition["image_slots"]):
        layout.append("Room for a publication's logo, bottom left, from a file you supply")
    for slot, words in definition["locked"].items():
        if slot != "logo":
            layout.append(f"Fixed text: \u201c{words}\u201d")
    if definition["optional_marks"]:
        layout.append("Small logo on the photo, which can be left off")
    if any(slot["fit"] == "cover" for slot in definition["image_slots"]):
        layout.append("Can take an AI-generated image" if ai_images else "Does not take AI-generated images")
    photos = [
        {"slot": slot["slot"], "shape": slot["shape"] + ("" if slot["required"] else ", optional"),
         "size": f"{slot['width']}×{slot['height']}"}
        for slot in definition["image_slots"] if slot["fit"] == "cover"
    ]
    text = []
    for slot, limits in definition["text_slots"].items():
        where = placed.get(slot, {})
        text.append({
            "slot": slot, "label": SLOT_LABELS.get(slot, slot.replace("-", " ").capitalize()),
            "where": " ".join(part for part in (where.get("vertical_zone"), where.get("text_align")) if part),
            "lines": limits["max_lines"], "chars": limits["max_chars"],
            "italic": limits["italic_accent"], "required": limits["required"],
        })
    used = [
        {"code": template["code"], "label": template["label"], "role": role["role"]}
        for template in templates for role in template["sequence"] if entry["id"] in role["frames"]
    ]
    return {
        "id": entry["id"], "family": entry["family"], "preview": f"previews/{entry['id']}.jpg",
        "layout": layout, "photos": photos, "text": text, "used": used,
    }


def _position(box: dict, canvas: dict) -> str:
    middle_x = (box["x"] + box["width"] / 2) / canvas["width"]
    middle_y = (box["y"] + box["height"] / 2) / canvas["height"]
    return f"{'top' if middle_y < 0.5 else 'bottom'} {'left' if middle_x < 0.4 else 'right' if middle_x > 0.6 else 'center'}"


def _rule(template: dict) -> str:
    low, high = template["min_slides"], template["max_slides"]
    parts = ["1 slide" if low == high == 1 else f"{low} to {high} slides"]
    roles = template["sequence"]
    if len(roles) > 1:
        first, last = roles[0], roles[-1]
        if first["min"] >= 1 and len(first["frames"]) == 1:
            parts.append(f"starts with {first['frames'][0]}")
        elif first["min"] == 0 and set(first["frames"]) <= set(roles[1]["frames"]):
            parts.append(f"any {_sets(roles[1])} layouts in any order")
        elif first["min"] == 0 and first["max"] == 1:
            parts.append(f"can open with one {_sets(first)} layout")
            parts.append(f"then {_sets(roles[1])} layouts")
        for middle in roles[1:-1] if len(roles) > 2 else roles[1:] if first["min"] >= 1 else []:
            cap = middle.get("cap")
            parts.append(f"then {_sets(middle)} layouts" + (
                f" (up to {cap['max']} of {' or '.join(cap['frames'])})" if cap else ""
            ))
        if len(roles) < 3:
            pass
        elif last["min"] >= 1 and len(last["frames"]) == 1:
            parts.append(f"ends with {last['frames'][0]}")
        elif last["min"] == 0 and len(last["frames"]) == 1:
            parts.append(f"can end with {last['frames'][0]}")
    return ", ".join(parts)


def _sets(role: dict) -> str:
    """Name the layout sets a role draws on by their ID prefix, as in 'SC or SG'; a lone layout keeps its ID."""
    sets: dict[str, list[str]] = {}
    for frame in role["frames"]:
        sets.setdefault(frame.split("-")[0], []).append(frame)
    names = sorted(frames[0] if len(frames) == 1 else prefix for prefix, frames in sets.items())
    return " or ".join((", ".join(names[:-1]), names[-1]) if len(names) > 1 else names)


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ · social layouts</title>
<style>
  :root { --page: #e9e7e2; --card: #ffffff; --ink: #1c1c1c; --muted: #6b6b6b; --line: #d9d6cf; --accent: #111; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
         padding: 28px 24px 150px; }
  header { max-width: 1320px; margin: 0 auto 20px; }
  h1 { font: 400 30px/1.15 Georgia, "Times New Roman", serif; margin: 0 0 6px; }
  header p { margin: 0; color: var(--muted); max-width: 70ch; }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  button { font: inherit; color: var(--ink); cursor: pointer; }
  .tabs button, .pill { background: transparent; border: 1px solid var(--muted); border-radius: 999px; padding: 5px 14px; }
  .tabs button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
  main { max-width: 1320px; margin: 0 auto; }
  h2 { font: 400 20px Georgia, "Times New Roman", serif; margin: 30px 0 4px; }
  .rule { color: var(--muted); margin: 0 0 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 18px; }
  .card { background: var(--card); border-radius: 10px; overflow: hidden; display: flex; flex-direction: column;
          box-shadow: 0 1px 2px rgba(0, 0, 0, .08); }
  .card.picked { outline: 2px solid var(--accent); }
  .shot { display: block; padding: 0; border: 0; background: #d5d2cb; cursor: zoom-in; }
  .shot img { display: block; width: 100%; height: auto; aspect-ratio: 4 / 5; }
  .body { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
  .id { font-weight: 700; font-size: 15px; letter-spacing: .02em; }
  .facts { margin: 0; padding: 0; list-style: none; color: var(--muted); font-size: 12.5px; }
  .facts b { color: var(--ink); font-weight: 600; }
  .add { margin-top: auto; align-self: flex-start; }
  dialog { border: 0; border-radius: 12px; padding: 0; max-width: min(960px, 94vw); width: 100%; color: var(--ink); }
  dialog::backdrop { background: rgba(0, 0, 0, .6); }
  .detail { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .detail img { width: 100%; height: auto; display: block; }
  .detail .info { padding: 22px 24px; overflow-y: auto; max-height: 90vh; }
  .detail h3 { margin: 0 0 10px; font-size: 20px; }
  .detail h4 { margin: 16px 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
  .detail ul { margin: 0; padding-left: 18px; }
  .detail .row { display: flex; gap: 8px; margin-top: 20px; }
  @media (max-width: 720px) { .detail { grid-template-columns: 1fr; } }
  .tray { position: fixed; left: 0; right: 0; bottom: 0; background: var(--card); border-top: 1px solid var(--line);
          box-shadow: 0 -6px 24px rgba(0, 0, 0, .12); padding: 12px 24px 14px; }
  .tray[hidden] { display: none; }
  .tray .inner { max-width: 1320px; margin: 0 auto; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  .strip { display: flex; gap: 8px; overflow-x: auto; flex: 1; min-width: 200px; padding: 2px; }
  .chip { position: relative; flex: none; width: 56px; text-align: center; font-size: 11px; font-weight: 600; }
  .chip img { width: 56px; height: 70px; display: block; border-radius: 4px; }
  .chip button { position: absolute; top: -4px; right: -4px; width: 18px; height: 18px; border-radius: 50%; border: 0;
                 background: var(--accent); color: #fff; font-size: 12px; line-height: 18px; padding: 0; }
  .verdict { flex: 1 1 320px; }
  .verdict .ok { font-weight: 600; }
  .verdict input { width: 100%; margin-top: 6px; font: inherit; padding: 6px 8px; border: 1px solid var(--line);
                   border-radius: 6px; background: var(--page); color: var(--ink); }
  .tray .buttons { display: flex; gap: 8px; }
  .solid { background: var(--accent); color: #fff; border: 1px solid var(--accent); border-radius: 999px; padding: 5px 14px; }
</style>
</head>
<body>
<header>
  <h1>__NAME__ social layouts</h1>
  <p>Every layout available for a post. Click a layout to see it larger and what it holds. Use “Add to my post” to
     line up layouts in the order you want; the bar at the bottom tells you whether they work together and gives you
     a line to paste into your request.</p>
  <div class="tabs" id="tabs"></div>
</header>
<main id="main"></main>
<dialog id="dialog"><div class="detail"><img id="d-img" alt=""><div class="info" id="d-info"></div></div></dialog>
<div class="tray" id="tray" hidden><div class="inner">
  <div class="strip" id="strip"></div>
  <div class="verdict"><div id="verdict"></div><input id="request" readonly aria-label="Text to paste into your request"></div>
  <div class="buttons"><button class="solid" id="copy" type="button">Copy</button><button class="pill" id="clear" type="button">Clear</button></div>
</div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
  const data = JSON.parse(document.getElementById('data').textContent);
  const $ = (id) => document.getElementById(id);
  const byId = Object.fromEntries(data.frames.map((frame) => [frame.id, frame]));
  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children);
    return node;
  };
  let family = 'all';
  const picked = [];

  const photoLine = (frame) => {
    if (!frame.photos.length) return 'No photo';
    const count = {};
    for (const photo of frame.photos) count[photo.shape] = (count[photo.shape] || 0) + 1;
    const total = frame.photos.length;
    return `${total} photo${total > 1 ? 's' : ''}: ` + Object.entries(count).map(([shape, n]) => `${n} ${shape}`).join(', ');
  };
  const textLine = (frame) => frame.text.length ? frame.text.map((slot) => slot.label).join(', ') : 'No text';
  const usedLine = (frame) => frame.used.length
    ? [...new Set(frame.used.map((use) => use.label))].join(', ') : 'Not in a post type yet';

  function render() {
    $('tabs').replaceChildren(...[{ key: 'all', label: 'All layouts' }, ...data.families].map((item) => {
      const count = item.key === 'all' ? data.frames.length : data.frames.filter((f) => f.family === item.key).length;
      const button = el('button', { type: 'button', textContent: `${item.label} (${count})` });
      button.setAttribute('aria-pressed', String(family === item.key));
      button.onclick = () => { family = item.key; render(); };
      return button;
    }));
    $('main').replaceChildren(...data.families.filter((item) => family === 'all' || family === item.key).flatMap((item) => {
      const frames = data.frames.filter((frame) => frame.family === item.key);
      const rules = data.templates.filter((t) => frames.some((f) => f.used.some((use) => use.code === t.code)));
      return [
        el('h2', { textContent: item.label }),
        el('p', { className: 'rule', textContent: rules.map((t) => `${t.label}: ${t.rule}.`).join(' ') }),
        el('div', { className: 'grid' }, ...frames.map(card)),
      ];
    }));
  }

  function card(frame) {
    const shot = el('button', { className: 'shot', type: 'button' },
      el('img', { src: frame.preview, alt: `Layout ${frame.id}`, loading: 'lazy', width: 600, height: 750 }));
    shot.setAttribute('aria-label', `See layout ${frame.id} larger`);
    shot.onclick = () => detail(frame);
    const facts = el('ul', { className: 'facts' },
      el('li', {}, el('b', { textContent: 'Photos ' }), photoLine(frame).replace(/^\\d+ photos?: /, '')),
      el('li', {}, el('b', { textContent: 'Text ' }), textLine(frame)),
      el('li', {}, el('b', { textContent: 'Look ' }), frame.layout.slice(0, 2).join(' · ')));
    const add = el('button', { className: 'pill add', type: 'button', textContent: 'Add to my post' });
    add.onclick = () => pick(frame.id);
    const node = el('div', { className: 'card' + (picked.includes(frame.id) ? ' picked' : '') }, shot,
      el('div', { className: 'body' }, el('div', { className: 'id', textContent: frame.id }), facts, add));
    return node;
  }

  function detail(frame) {
    $('d-img').src = frame.preview;
    $('d-img').alt = `Layout ${frame.id}`;
    const add = el('button', { className: 'solid', type: 'button', textContent: 'Add to my post' });
    add.onclick = () => { pick(frame.id); $('dialog').close(); };
    const close = el('button', { className: 'pill', type: 'button', textContent: 'Close' });
    close.onclick = () => $('dialog').close();
    $('d-info').replaceChildren(
      el('h3', { textContent: frame.id }),
      el('h4', { textContent: 'Look' }), el('ul', {}, ...frame.layout.map((line) => el('li', { textContent: line }))),
      el('h4', { textContent: 'Photos you provide' }),
      el('ul', {}, ...(frame.photos.length ? frame.photos : [null]).map((photo) => el('li', {
        textContent: photo ? `${photo.shape[0].toUpperCase()}${photo.shape.slice(1)} photo (${photo.slot}, ${photo.size} on the slide)` : 'None',
      }))),
      el('h4', { textContent: 'Text you provide' }),
      el('ul', {}, ...(frame.text.length ? frame.text : [null]).map((slot) => el('li', {
        textContent: slot ? `${slot.label}${slot.required ? '' : ' (optional)'}: ${slot.where}, up to ${slot.lines} `
          + `line${slot.lines > 1 ? 's' : ''}, about ${slot.chars} characters`
          + (slot.italic ? ', one word or phrase can be italic' : '') : 'None',
      }))),
      el('h4', { textContent: 'Can be used in' }), el('ul', {}, el('li', { textContent: usedLine(frame) })),
      el('div', { className: 'row' }, add, close));
    $('dialog').showModal();
  }
  $('dialog').addEventListener('click', (event) => { if (event.target === $('dialog')) $('dialog').close(); });

  function pick(id) {
    picked.push(id);
    tray();
    render();
  }

  // A sequence fits a post type when its slides can be dealt, in order, to the type's roles.
  // Returns the step each slide falls to, or null. A step's cap limits how many slides may use some of its layouts.
  function deal(template, ids, role = 0, at = 0) {
    if (role === template.sequence.length) return at === ids.length ? [] : null;
    const step = template.sequence[role];
    const cap = step.cap || { frames: [], max: 0 };
    let taken = 0;
    let capped = 0;
    while (true) {
      const rest = taken >= step.min ? deal(template, ids, role + 1, at + taken) : null;
      if (rest) return [...Array(taken).fill(step), ...rest];
      if (taken === step.max || at + taken >= ids.length || !step.frames.includes(ids[at + taken])) return null;
      if (cap.frames.includes(ids[at + taken]) && (capped += 1) > cap.max) return null;
      taken += 1;
    }
  }

  function tray() {
    $('tray').hidden = !picked.length;
    $('strip').replaceChildren(...picked.map((id, i) => {
      const remove = el('button', { type: 'button', textContent: '×' });
      remove.setAttribute('aria-label', `Remove slide ${i + 1}, ${id}`);
      remove.onclick = () => { picked.splice(i, 1); tray(); render(); };
      return el('div', { className: 'chip' }, el('img', { src: byId[id].preview, alt: '' }), `${i + 1}. ${id}`, remove);
    }));
    if (!picked.length) return;
    // When several post types fit, the closest match gives the most slides a place only one layout can take,
    // such as a cover; after that, the one with the fewest layouts to choose from.
    const size = (t) => new Set(t.sequence.flatMap((step) => step.frames)).size;
    const match = data.templates
      .map((t) => ({ t, steps: picked.length >= t.min && picked.length <= t.max ? deal(t, picked) : null }))
      .filter((fit) => fit.steps)
      .map((fit) => ({ t: fit.t, fixed: fit.steps.filter((step) => step.frames.length === 1).length }))
      .sort((a, b) => b.fixed - a.fixed || size(a.t) - size(b.t) || (a.t.code < b.t.code ? -1 : 1))
      .map((fit) => fit.t)[0];
    const named = match && `${/^[aeiou]/i.test(match.label) ? 'an' : 'a'} ${match.label}`;
    let message;
    if (match) {
      message = el('span', { className: 'ok', textContent: `Works as ${named} (${picked.length} slide${picked.length > 1 ? 's' : ''}).` });
    } else {
      const holds = (t) => picked.every((id) => t.sequence.some((step) => step.frames.includes(id)));
      const options = data.templates.filter(holds);
      message = options.length
        ? 'This order is not a complete post yet. ' + options.map((t) => `${t.label}: ${t.rule}.`).join(' ')
        : 'No post type takes all of these layouts together.';
    }
    $('verdict').replaceChildren(message);
    $('request').value = match
      ? `Make ${named} using ${picked.length > 1 ? `layouts ${picked.join(', ')} in that order` : `layout ${picked[0]}`}.`
      : `Layouts ${picked.join(', ')}`;
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

  render();
</script>
</body>
</html>
"""
