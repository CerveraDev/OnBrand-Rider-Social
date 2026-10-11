"""Feed simulator: a phone-sized preview page for a rendered social package.

Shows the rendered slides the way a feed post is experienced: swipeable, with
position dots, the caption, and hashtags. It is a generic mock for review, not a
copy of any platform's interface, and it never leaves the package directory.
"""

from __future__ import annotations

from html import escape
import json
from pathlib import Path


SIMULATOR_FILE = "simulator.html"


def write_simulator(
    package_dir: Path, package: dict, slides: dict[str, list[str]], *, passed: bool,
    account: str | None = None, avatar: str | None = None,
) -> Path:
    """Write the simulator for `slides`, a map of variant name to package-relative slide paths.

    `account` and `avatar` come from the project profile. Without a handle the project slug stands in;
    without an avatar (a package-relative path) the account's initial is shown.
    """
    composition = package["composition"]
    data = {
        "account": account or package["campaign"]["project"].replace("-", ""),
        "avatar": avatar,
        "ratio": [composition["width"], composition["height"]],
        "status": (
            f"{package['build']['mode']} · {composition['template']} ({composition['template_status']}) · "
            f"{composition['format']} {composition['width']}×{composition['height']}"
            + ("" if passed else " · render checks failed")
        ),
        "variants": {
            name: {
                "caption": package["variants"][name]["caption"],
                "hashtags": package["variants"][name]["hashtags"],
                "slides": [
                    {"src": src, "alt": slide["alt_text"]}
                    for src, slide in zip(paths, package["variants"][name]["slides"])
                ],
            }
            for name, paths in sorted(slides.items()) if paths
        },
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = escape(package["campaign"].get("title") or package["campaign"]["slug"])
    path = package_dir / SIMULATOR_FILE
    path.write_text(_PAGE.replace("__TITLE__", title).replace("__DATA__", payload), encoding="utf-8")
    return path


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · feed simulator</title>
<style>
  :root { --page: #e9e7e2; --ink: #1c1c1c; --muted: #6b6b6b; --screen: #ffffff; --line: #e3e3e3; --bezel: #111; }
  :root[data-theme="dark"] { --page: #1b1b1d; --ink: #f2f2f2; --muted: #a0a0a0; --screen: #000000; --line: #262626; --bezel: #2c2c2e; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; background: var(--page); color: var(--ink);
         font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
         display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 16px 16px 20px; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; justify-content: center;
         color: var(--muted); font-size: 12px; max-width: 720px; text-align: center; }
  .bar button, .bar select { font: inherit; color: var(--ink); background: transparent; border: 1px solid var(--muted);
         border-radius: 999px; padding: 4px 12px; cursor: pointer; }
  .phone { width: 390px; flex: none; background: var(--bezel); border-radius: 46px; padding: 10px;
           box-shadow: 0 24px 60px rgba(0, 0, 0, .28); }
  .screen { background: var(--screen); border-radius: 37px; overflow: hidden; height: 800px;
            display: flex; flex-direction: column; }
  .status { display: flex; justify-content: space-between; padding: 12px 26px 6px; font-weight: 600; font-size: 13px; }
  .appbar { padding: 6px 16px 10px; font-weight: 700; font-size: 18px; border-bottom: 1px solid var(--line); }
  .feed { flex: 1; overflow-y: auto; scrollbar-width: none; }
  .feed::-webkit-scrollbar { display: none; }
  .head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; }
  .avatar { width: 34px; height: 34px; border-radius: 50%; background: #111; color: #fff; display: grid;
            place-items: center; font: 600 15px Georgia, serif; border: 1px solid var(--line);
            background-size: cover; background-position: center; }
  .account { font-weight: 600; flex: 1; }
  .dotsmenu { letter-spacing: 2px; color: var(--ink); }
  .stage { position: relative; background: #000; }
  .track { display: flex; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none; cursor: grab; }
  .track::-webkit-scrollbar { display: none; }
  .track.dragging { cursor: grabbing; scroll-snap-type: none; }
  .track img { flex: 0 0 100%; width: 100%; height: auto; display: block; scroll-snap-align: center;
               scroll-snap-stop: always; user-select: none; -webkit-user-drag: none; }
  .count { position: absolute; top: 12px; right: 12px; background: rgba(20, 20, 20, .72); color: #fff;
           border-radius: 999px; padding: 3px 9px; font-size: 12px; }
  .nav { position: absolute; top: 50%; transform: translateY(-50%); width: 28px; height: 28px; border-radius: 50%;
         border: 0; background: rgba(255, 255, 255, .85); color: #111; font-size: 16px; line-height: 1; cursor: pointer;
         opacity: 0; transition: opacity .15s; }
  .stage:hover .nav:not([hidden]) { opacity: 1; }
  .nav.prev { left: 8px; } .nav.next { right: 8px; }
  .burst { position: absolute; inset: 0; display: grid; place-items: center; pointer-events: none; opacity: 0; }
  .burst.on { animation: burst .8s ease-out; }
  .burst svg { width: 96px; height: 96px; fill: #fff; filter: drop-shadow(0 4px 12px rgba(0, 0, 0, .4)); }
  @keyframes burst { 0% { opacity: 0; transform: scale(.4); } 20% { opacity: 1; transform: scale(1.1); }
                     70% { opacity: 1; transform: scale(1); } 100% { opacity: 0; transform: scale(1); } }
  .actions { display: flex; align-items: center; gap: 14px; padding: 10px 12px 4px; position: relative; }
  .actions button { background: none; border: 0; padding: 0; cursor: pointer; color: var(--ink); display: grid; }
  .actions svg { width: 25px; height: 25px; fill: none; stroke: currentColor; stroke-width: 1.8;
                 stroke-linecap: round; stroke-linejoin: round; }
  .actions .liked svg { fill: #ed4956; stroke: #ed4956; }
  .actions .saved svg { fill: currentColor; }
  .pager { position: absolute; left: 50%; transform: translateX(-50%); display: flex; gap: 4px; }
  .pager i { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); opacity: .45; }
  .pager i.on { background: #0095f6; opacity: 1; }
  .spacer { flex: 1; }
  .likes { padding: 2px 12px; font-weight: 600; }
  .caption { padding: 2px 12px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  .caption b { font-weight: 600; }
  .caption .tags { color: #00376b; }
  :root[data-theme="dark"] .caption .tags { color: #e0f1ff; }
  .more { color: var(--muted); background: none; border: 0; padding: 0; font: inherit; cursor: pointer; }
  .meta { padding: 6px 12px 18px; color: var(--muted); font-size: 12px; }
  .alt { max-width: 390px; color: var(--muted); font-size: 12px; text-align: center; min-height: 2.8em; }
</style>
</head>
<body>
<div class="bar">
  <span id="status"></span>
  <select id="variant" aria-label="Variant" hidden></select>
  <button id="theme" type="button">Dark mode</button>
</div>
<div class="phone" id="phone"><div class="screen">
  <div class="status"><span>9:41</span><span>●●● ▮</span></div>
  <div class="appbar">Feed preview</div>
  <div class="feed">
    <div class="head"><div class="avatar" id="avatar"></div><div class="account" id="account"></div><div class="dotsmenu">•••</div></div>
    <div class="stage">
      <div class="track" id="track"></div>
      <div class="count" id="count"></div>
      <button class="nav prev" id="prev" type="button" aria-label="Previous slide">‹</button>
      <button class="nav next" id="next" type="button" aria-label="Next slide">›</button>
      <div class="burst" id="burst"><svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.6-9.6-9.3C.9 8.300 2.700 4.500 6.300 4.500c2.100 0 3.700 1.100 5.700 3.300 2-2.200 3.600-3.300 5.700-3.300 3.600 0 5.400 3.800 3.900 7.200C19.500 16.400 12 21 12 21z"/></svg></div>
    </div>
    <div class="actions">
      <button id="like" type="button" aria-label="Like"><svg viewBox="0 0 24 24"><path d="M12 21s-7.500-4.600-9.600-9.300C.900 8.300 2.700 4.500 6.300 4.500c2.100 0 3.700 1.100 5.700 3.300 2-2.200 3.600-3.300 5.700-3.300 3.600 0 5.400 3.800 3.900 7.200C19.500 16.400 12 21 12 21z"/></svg></button>
      <button type="button" aria-label="Comment"><svg viewBox="0 0 24 24"><path d="M20.500 12a8.500 8.500 0 1 0-3.700 7l3.700 1-1-3.500a8.400 8.400 0 0 0 1-4.500z"/></svg></button>
      <button type="button" aria-label="Share"><svg viewBox="0 0 24 24"><path d="M21 3 10 14M21 3l-6.500 18-4.500-7-7-4.500L21 3z"/></svg></button>
      <div class="pager" id="pager"></div>
      <span class="spacer"></span>
      <button id="save" type="button" aria-label="Save"><svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-5-6 5V3z"/></svg></button>
    </div>
    <div class="likes" id="likes">Liked by the sales team</div>
    <div class="caption" id="caption"></div>
    <div class="meta">Just now</div>
  </div>
</div></div>
<div class="alt" id="alt"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
  const data = JSON.parse(document.getElementById('data').textContent);
  const $ = (id) => document.getElementById(id);
  const track = $('track');
  let post, index = 0, expanded = false;

  $('status').textContent = data.status;
  $('account').textContent = data.account;
  if (data.avatar) $('avatar').style.backgroundImage = `url(${JSON.stringify(data.avatar)})`;
  else $('avatar').textContent = data.account.replace(/^the/, '').charAt(0).toUpperCase();
  const names = Object.keys(data.variants);
  if (names.length > 1) {
    $('variant').hidden = false;
    for (const name of names) $('variant').add(new Option(name, name));
    $('variant').onchange = () => load($('variant').value);
  }

  // The phone keeps its proportions and grows or shrinks to fill the window.
  const phone = $('phone');
  function fit() {
    const style = getComputedStyle(document.body);
    const gaps = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom) + 2 * parseFloat(style.rowGap);
    const room = innerHeight - gaps - document.querySelector('.bar').offsetHeight - $('alt').offsetHeight;
    // On a phone-width window the mock fills the width and the page scrolls.
    const scale = Math.max(0.5, Math.min(innerWidth < 500 ? 2.5 : room / 820, (innerWidth - 32) / 390, 2.5));
    phone.style.zoom = scale;
    $('alt').style.maxWidth = `${390 * scale}px`;
  }
  addEventListener('resize', fit);
  // Pointer positions are in window pixels; scroll offsets are in the phone's own.
  const unit = () => track.getBoundingClientRect().width / track.clientWidth || 1;

  function load(name) {
    post = data.variants[name];
    track.replaceChildren(...post.slides.map((slide, i) => {
      const img = new Image();
      img.src = slide.src;
      img.alt = slide.alt;
      img.width = data.ratio[0];
      img.height = data.ratio[1];
      img.loading = i ? 'lazy' : 'eager';
      return img;
    }));
    $('pager').replaceChildren(...post.slides.map(() => document.createElement('i')));
    $('pager').hidden = post.slides.length < 2;
    expanded = false;
    track.scrollLeft = 0;
    show(0);
    caption();
  }

  function show(next) {
    index = Math.max(0, Math.min(post.slides.length - 1, next));
    [...$('pager').children].forEach((dot, i) => dot.classList.toggle('on', i === index));
    $('count').textContent = `${index + 1}/${post.slides.length}`;
    $('count').hidden = post.slides.length < 2;
    $('prev').hidden = index === 0;
    $('next').hidden = index === post.slides.length - 1;
    $('alt').textContent = `Alt text, slide ${index + 1}: ${post.slides[index].alt}`;
  }

  function go(next) {
    const target = Math.max(0, Math.min(post.slides.length - 1, next));
    track.scrollTo({ left: target * track.clientWidth, behavior: 'smooth' });
  }

  function caption() {
    const limit = 110;
    const box = $('caption');
    const name = document.createElement('b');
    name.textContent = data.account + ' ';
    const long = post.caption.length > limit;
    const text = !long || expanded ? post.caption : post.caption.slice(0, limit).replace(/\\s+\\S*$/, '') + '… ';
    box.replaceChildren(name, text);
    if (long && !expanded) {
      const more = document.createElement('button');
      more.className = 'more';
      more.type = 'button';
      more.textContent = 'more';
      more.onclick = () => { expanded = true; caption(); };
      box.append(more);
    } else if (post.hashtags.length) {
      const tags = document.createElement('span');
      tags.className = 'tags';
      tags.textContent = '\\n\\n' + post.hashtags.join(' ');
      box.append(tags);
    }
  }

  track.addEventListener('scroll', () => show(Math.round(track.scrollLeft / track.clientWidth)));
  $('prev').onclick = () => go(index - 1);
  $('next').onclick = () => go(index + 1);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowRight') go(index + 1);
    if (event.key === 'ArrowLeft') go(index - 1);
  });

  // Mouse drag stands in for a finger swipe on a desktop browser.
  let drag = null;
  track.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'mouse') return;
    drag = { x: event.clientX, left: track.scrollLeft };
    track.classList.add('dragging');
    track.setPointerCapture(event.pointerId);
  });
  track.addEventListener('pointermove', (event) => {
    if (drag) track.scrollLeft = drag.left - (event.clientX - drag.x) / unit();
  });
  const release = (event) => {
    if (!drag) return;
    const moved = event.clientX - drag.x;
    const start = Math.round(drag.left / track.clientWidth);
    drag = null;
    track.classList.remove('dragging');
    go(Math.abs(moved) > 40 ? start + (moved < 0 ? 1 : -1) : start);
  };
  track.addEventListener('pointerup', release);
  track.addEventListener('pointercancel', release);

  const like = (on) => $('like').classList.toggle('liked', on);
  $('like').onclick = () => like(!$('like').classList.contains('liked'));
  $('save').onclick = () => $('save').classList.toggle('saved');
  track.addEventListener('dblclick', () => {
    like(true);
    $('burst').classList.remove('on');
    void $('burst').offsetWidth;
    $('burst').classList.add('on');
  });
  $('theme').onclick = () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    $('theme').textContent = dark ? 'Light mode' : 'Dark mode';
  };

  load(names[0]);
  fit();
</script>
</body>
</html>
"""
