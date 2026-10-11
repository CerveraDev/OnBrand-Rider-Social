#!/usr/bin/env node

// Renders the slides of a built social package from the project's scaffold.
//
// For each slide the scaffold page is loaded in Chromium, every frame but the
// slide's own is removed, the frame's image and text slots are filled, and the
// frame canvas is exported as a JPEG at the requested scale. Each text slot is
// measured after layout so the caller can check it against the frame's limits.
//
// Text and logos that sit on an image follow the image behind them. Over a
// light image the text is black, the logo is the project's on-light logo, and
// the scrim keeps its opacity but turns white; over a dark image the text is
// white. Text and logos that are not on an image are left as the scaffold has them.
//
// Called by tools/social_runtime/render.py, which writes the job file:
//   node tools/social_runtime/render_slides.cjs --job <job.json>
// The result is printed to stdout as JSON.

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const VIEWPORT = { width: 1512, height: 900 };

async function main() {
  const jobIndex = process.argv.indexOf('--job');
  if (jobIndex < 0 || !process.argv[jobIndex + 1]) {
    throw new Error('Usage: render_slides.cjs --job <job.json>');
  }
  const job = JSON.parse(fs.readFileSync(process.argv[jobIndex + 1], 'utf8'));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const slides = [];
  try {
    const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: job.scale });
    const page = await context.newPage();
    for (const slide of job.slides) {
      await page.goto(pathToFileURL(job.scaffold_html).href, { waitUntil: 'domcontentloaded' });
      if (job.overrides_css) await page.addStyleTag({ path: job.overrides_css });
      const measured = await page.evaluate(fillInPage, slide);
      if (!measured.error) {
        const canvas = page.locator(`[data-frame-id="${slide.frame}"] [data-frame-canvas]`);
        const overlays = await page.evaluate(exposeImagesInPage, slide);
        const bare = await canvas.screenshot({ type: 'png' });
        const toned = await page.evaluate(toneInPage, {
          slide, overlays, png: bare.toString('base64'),
          logoOnLight: job.logo_on_light || null, threshold: job.light_threshold,
        });
        measured.tones = toned.tones;
        measured.logo_loaded = toned.logo_loaded;
        for (const [slot, style] of Object.entries(toned.text)) Object.assign(measured.text[slot], style);
        fs.mkdirSync(path.dirname(slide.output), { recursive: true });
        await canvas.screenshot({ path: slide.output, type: 'jpeg', quality: job.quality });
      }
      slides.push({ output: slide.output, ...measured });
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({ slides }) + '\n');
}

function loadPlaywright() {
  const candidates = [
    process.env.ONBRAND_PLAYWRIGHT_MODULE,
    path.join(__dirname, '..', '..', 'node_modules', 'playwright'),
    path.join(__dirname, '..', 'email_render_matrix', 'node_modules', 'playwright'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      // Try the next location.
    }
  }
  throw new Error('The slide renderer is not installed. Run: python3 -m tools.social_runtime.cli setup --project <slug>');
}

// Runs in the page. Fills one frame and measures the result.
async function fillInPage(slide) {
  const frame = document.querySelector(`[data-frame-id="${slide.frame}"]`);
  const canvas = frame && frame.querySelector('[data-frame-canvas]');
  if (!canvas) return { error: `frame ${slide.frame} is not in the scaffold` };
  for (const other of document.querySelectorAll('[data-frame-id]')) {
    if (other !== frame) other.remove();
  }
  // Scaffold containers transition their backgrounds; a swap must land at once.
  const still = document.createElement('style');
  still.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
  document.head.append(still);
  const slotElement = (name) =>
    canvas.matches(`[data-slot="${name}"]`) ? canvas : canvas.querySelector(`[data-slot="${name}"]`);
  const layersOf = (value) => {
    const layers = [];
    let depth = 0;
    let current = '';
    for (const char of value) {
      if (char === '(') depth += 1;
      if (char === ')') depth -= 1;
      if (char === ',' && depth === 0) {
        layers.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    layers.push(current.trim());
    return layers;
  };

  // Optional parts the post leaves out. A logo keeps its place so its neighbour does not move.
  for (const name of slide.remove || []) {
    const element = slotElement(name);
    if (!element) return { error: `'${name}' is not in frame ${slide.frame}` };
    if (element.tagName === 'IMG') element.style.setProperty('visibility', 'hidden', 'important');
    else element.style.setProperty('display', 'none', 'important');
  }

  const images = [];
  for (const image of slide.images) {
    const element = slotElement(image.slot);
    if (!element) return { error: `image slot '${image.slot}' is not in frame ${slide.frame}` };
    if (element.tagName === 'IMG') {
      // A supplied logo is fitted inside the area, at its own proportions, from the left.
      const box = getComputedStyle(element);
      element.src = image.url;
      try {
        await element.decode();
      } catch (error) {
        return { error: `image for slot '${image.slot}' could not be loaded` };
      }
      for (const [property, value] of Object.entries({
        height: box.maxHeight === 'none' ? `${element.getBoundingClientRect().height}px` : box.maxHeight,
        width: 'auto', 'max-width': `${image.max_width}px`, 'object-fit': 'contain', 'object-position': 'left center',
      })) element.style.setProperty(property, value, 'important');
      images.push({ slot: image.slot, natural_width: element.naturalWidth, natural_height: element.naturalHeight });
      continue;
    }
    const style = getComputedStyle(element);
    const layers = layersOf(style.backgroundImage);
    const index = layers.findIndex((layer) => layer.startsWith('url('));
    if (index < 0) return { error: `image slot '${image.slot}' has no background image in the scaffold` };
    const probe = new Image();
    probe.src = image.url;
    try {
      await probe.decode();
    } catch (error) {
      return { error: `image for slot '${image.slot}' could not be loaded` };
    }
    layers[index] = `url(${JSON.stringify(image.url)})`;
    const sizes = layersOf(style.backgroundSize);
    const positions = layersOf(style.backgroundPosition);
    // Every image area cover-fits, whatever sizing the scaffold gives it.
    if (sizes[index] !== 'cover') {
      sizes[index] = 'cover';
      positions[index] = '50% 50%';
    }
    element.style.setProperty('background-image', layers.join(', '), 'important');
    element.style.setProperty('background-size', sizes.join(', '), 'important');
    element.style.setProperty('background-position', positions.join(', '), 'important');
    images.push({ slot: image.slot, natural_width: probe.naturalWidth, natural_height: probe.naturalHeight });
  }

  for (const entry of slide.text) {
    const element = slotElement(entry.slot);
    if (!element) return { error: `text slot '${entry.slot}' is not in frame ${slide.frame}` };
    element.replaceChildren();
    entry.value.split('\n').forEach((line, lineIndex) => {
      if (lineIndex) element.append(document.createElement('br'));
      // In a slot with an italic accent, *word* is set in italics. The italic face
      // crowds upright neighbours on the same line, so the scaffold's own spacing is
      // applied: two non-breaking spaces before the word and one after, inside it.
      const parts = entry.italic_accent ? line.split(/\*([^*]+)\*/) : [line];
      parts.forEach((part, partIndex) => {
        if (!part) return;
        if (partIndex % 2) {
          const accent = document.createElement('em');
          const followed = (parts[partIndex + 1] || '').trim() !== '';
          accent.textContent = part.trim() + (followed ? '\u00a0' : '');
          element.append(accent);
          return;
        }
        let upright = part;
        if (partIndex > 0) upright = upright.replace(/^ +/, '');
        if (partIndex < parts.length - 1 && upright.trim() !== '') upright = upright.replace(/ +$/, '') + '\u00a0\u00a0';
        if (upright) element.append(upright);
      });
    });
  }

  await document.fonts.ready;
  await Promise.all([...canvas.querySelectorAll('img')].map((img) => img.decode().catch(() => null)));
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  const bounds = canvas.getBoundingClientRect();
  const inside = (rect) =>
    rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1 &&
    rect.top >= bounds.top - 1 && rect.bottom <= bounds.bottom + 1;
  const text = {};
  for (const entry of slide.text) {
    const element = slotElement(entry.slot);
    const range = document.createRange();
    range.selectNodeContents(element);
    const rects = [...range.getClientRects()].filter((rect) => rect.width > 0);
    const step = parseFloat(getComputedStyle(element).fontSize) / 2;
    const lines = [];
    for (const rect of rects) {
      const middle = (rect.top + rect.bottom) / 2;
      if (!lines.some((line) => Math.abs(line - middle) < step)) lines.push(middle);
    }
    text[entry.slot] = {
      lines: lines.length,
      inside_canvas: inside(element.getBoundingClientRect()) && rects.every(inside),
    };
  }
  return { images, text, logo_loaded: null };
}

// Runs in the page. Hides the text and logo that sit on an image and lifts that
// image's scrim, so a screenshot shows what is really behind them. Returns where
// each hidden item was, in canvas pixels, and which image it sits on.
function exposeImagesInPage(slide) {
  const canvas = document.querySelector(`[data-frame-id="${slide.frame}"] [data-frame-canvas]`);
  const slotElement = (name) =>
    canvas.matches(`[data-slot="${name}"]`) ? canvas : canvas.querySelector(`[data-slot="${name}"]`);
  const bounds = canvas.getBoundingClientRect();
  const imageElements = slide.images.map((image) => slotElement(image.slot));
  const overlays = [];
  const add = (kind, slot, element, rect) => {
    let owner = null;
    imageElements.forEach((imageElement, index) => {
      if (imageElement.contains(element) && (owner === null || imageElements[owner].contains(imageElement))) owner = index;
    });
    if (owner === null || rect.width <= 0 || rect.height <= 0) return;
    overlays.push({
      kind, slot, image: slide.images[owner].slot,
      x: rect.left - bounds.left, y: rect.top - bounds.top, width: rect.width, height: rect.height,
    });
    element.style.setProperty('visibility', 'hidden', 'important');
  };
  for (const entry of slide.text) {
    const element = slotElement(entry.slot);
    const range = document.createRange();
    range.selectNodeContents(element);
    add('text', entry.slot, element, range.getBoundingClientRect());
  }
  // The project's own logos: every picture on the slide that the post did not supply.
  const supplied = new Set(slide.images.map((image) => image.slot));
  window.__logos = [...canvas.querySelectorAll('img[data-slot]')]
    .filter((img) => !supplied.has(img.getAttribute('data-slot')) && getComputedStyle(img).visibility !== 'hidden');
  for (const logo of window.__logos) add('logo', logo.getAttribute('data-slot'), logo, logo.getBoundingClientRect());

  window.__scrims = new Map();
  for (const element of imageElements) {
    if (element.tagName === 'IMG') continue;
    const filled = element.style.getPropertyValue('background-image');
    window.__scrims.set(element, filled);
    const layers = [];
    let depth = 0;
    let current = '';
    for (const char of filled) {
      if (char === '(') depth += 1;
      if (char === ')') depth -= 1;
      if (char === ',' && depth === 0) {
        layers.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    layers.push(current.trim());
    element.style.setProperty(
      'background-image', layers.map((layer) => (layer.startsWith('url(') ? layer : 'none')).join(', '), 'important');
  }
  return overlays;
}

// Runs in the page. Reads the brightness behind each hidden item from the
// screenshot, restores the slide, and sets every image's overlay for its tone.
async function toneInPage({ slide, overlays, png, logoOnLight, threshold }) {
  const canvas = document.querySelector(`[data-frame-id="${slide.frame}"] [data-frame-canvas]`);
  const slotElement = (name) =>
    canvas.matches(`[data-slot="${name}"]`) ? canvas : canvas.querySelector(`[data-slot="${name}"]`);
  const shot = new Image();
  shot.src = `data:image/png;base64,${png}`;
  await shot.decode();
  const board = document.createElement('canvas');
  board.width = shot.naturalWidth;
  board.height = shot.naturalHeight;
  const context = board.getContext('2d', { willReadFrequently: true });
  context.drawImage(shot, 0, 0);
  const ratio = shot.naturalWidth / canvas.getBoundingClientRect().width;
  const linear = Array.from({ length: 256 }, (_, value) => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  // Relative luminance of the region, 0 (black) to 1 (white).
  const brightness = (overlay) => {
    const left = Math.max(0, Math.floor(overlay.x * ratio));
    const top = Math.max(0, Math.floor(overlay.y * ratio));
    const width = Math.min(board.width - left, Math.ceil(overlay.width * ratio));
    const height = Math.min(board.height - top, Math.ceil(overlay.height * ratio));
    if (width <= 0 || height <= 0) return null;
    const data = context.getImageData(left, top, width, height).data;
    let total = 0;
    for (let i = 0; i < data.length; i += 4) {
      total += 0.2126 * linear[data[i]] + 0.7152 * linear[data[i + 1]] + 0.0722 * linear[data[i + 2]];
    }
    return total / (data.length / 4);
  };

  const groups = new Map();
  for (const overlay of overlays) {
    const value = brightness(overlay);
    if (value === null) continue;
    const group = groups.get(overlay.image) || { area: 0, total: 0, values: [], items: [] };
    const area = overlay.width * overlay.height;
    group.area += area;
    group.total += value * area;
    group.values.push(value);
    group.items.push(overlay);
    groups.set(overlay.image, group);
  }

  for (const overlay of overlays) slotElement(overlay.slot).style.removeProperty('visibility');
  for (const [imageElement, filled] of window.__scrims) {
    imageElement.style.setProperty('background-image', filled, 'important');
  }
  const tones = [];
  for (const image of slide.images) {
    const group = groups.get(image.slot);
    if (!group) continue;
    const mean = group.total / group.area;
    const light = mean > threshold;
    const tone = {
      image: image.slot, brightness: Math.round(mean * 100) / 100, light,
      // Part of what sits on this image is over the opposite tone.
      mixed: group.values.some((value) => (light ? value < threshold - 0.15 : value > threshold + 0.15)),
      logo_unchanged: false, scrim: false,
    };
    if (light) {
      const imageElement = slotElement(image.slot);
      const scrim = window.__scrims.get(imageElement)
        .replace(/rgba\(\s*\d+,\s*\d+,\s*\d+,\s*([\d.]+)\s*\)/g, 'rgba(255, 255, 255, $1)');
      imageElement.style.setProperty('background-image', scrim, 'important');
      tone.scrim = scrim !== window.__scrims.get(imageElement);
    }
    for (const overlay of group.items) {
      const item = slotElement(overlay.slot);
      if (overlay.kind === 'text') {
        const color = light ? '#000000' : '#ffffff';
        for (const part of [item, ...item.querySelectorAll('*')]) part.style.setProperty('color', color, 'important');
      } else if (light && logoOnLight) {
        item.src = logoOnLight;
        await item.decode().catch(() => null);
      } else if (light) {
        tone.logo_unchanged = true;
      }
    }
    tones.push(tone);
  }

  // Text is plain white or plain black, never another colour and never a gradient.
  const text = {};
  for (const entry of slide.text) {
    const slot = slotElement(entry.slot);
    const colors = new Set();
    let plain = true;
    for (const part of [slot, ...slot.querySelectorAll('*')]) {
      const style = getComputedStyle(part);
      colors.add(style.color);
      colors.add(style.webkitTextFillColor);
      if (style.webkitBackgroundClip === 'text' || style.backgroundClip === 'text') plain = false;
    }
    const used = [...colors];
    text[entry.slot] = {
      color: used.join(' / '),
      color_allowed: plain && used.length === 1 && ['rgb(255, 255, 255)', 'rgb(0, 0, 0)'].includes(used[0]),
    };
  }
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const logos = window.__logos;
  return { tones, text, logo_loaded: logos.length ? logos.every((logo) => logo.naturalWidth > 0) : null };
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});
