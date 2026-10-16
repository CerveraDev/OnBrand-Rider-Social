#!/usr/bin/env node

// Saves the photos of a press article, so a press carousel shows the article's own
// images rather than catalog ones.
//
// The article is opened in Chromium and scrolled so lazy images load. The pictures
// inside the article body, along with the share image the page names for itself
// (og:image or twitter:image), are collected. Pictures in the header, navigation,
// footer, or sidebars, small pictures, and logos, icons, avatars, and adverts are
// skipped. Each picture is downloaded at the largest size the page offers and saved
// as the site serves it when that is a JPEG or PNG; any other format, such as WebP
// or AVIF, is redrawn by the browser and saved as a JPEG.
//
// Called by tools/social_runtime/press_images.py, which writes the job file:
//   node tools/social_runtime/find_article_images.cjs --job <job.json>
// The result is printed to stdout as JSON.

const fs = require('fs');
const path = require('path');

const VIEWPORT = { width: 1440, height: 900 };
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';
const MIN_SIDE = 400;
const MAX_IMAGES = 12;

async function main() {
  const jobIndex = process.argv.indexOf('--job');
  if (jobIndex < 0 || !process.argv[jobIndex + 1]) throw new Error('Usage: find_article_images.cjs --job <job.json>');
  const job = JSON.parse(fs.readFileSync(process.argv[jobIndex + 1], 'utf8'));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: VIEWPORT, userAgent: USER_AGENT, locale: 'en-US' });
    const page = await context.newPage();
    try {
      await page.goto(job.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    } catch (error) {
      return finish({ images: [], reason: `the article page did not open (${error.message.split('\n')[0]})` });
    }
    await page.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
    const title = (await page.title()).toLowerCase();
    const host = new URL(page.url()).hostname.replace(/^www\./, '');
    if (/just a moment|attention required|access denied|are you a robot|captcha/.test(title) || title === host) {
      return finish({ images: [], reason: 'the site blocked the automated visit' });
    }
    await scrollThrough(page);
    const candidates = await page.evaluate(findImagesInPage, { minSide: MIN_SIDE, limit: MAX_IMAGES * 2 });
    const images = [];
    const seen = new Set();
    for (const candidate of candidates) {
      if (images.length >= MAX_IMAGES) break;
      const saved = await save(context, candidate, `${job.output_stem}-${String(images.length + 1).padStart(2, '0')}`);
      if (!saved || seen.has(saved.digest)) {
        if (saved) fs.unlinkSync(saved.file);
        continue;
      }
      seen.add(saved.digest);
      images.push({ file: saved.file, source_url: candidate.url, where: candidate.where, caption: candidate.caption });
    }
    const reason = images.length ? null : candidates.length
      ? 'the article\'s pictures could not be downloaded'
      : 'the article has no pictures in its body and names no share image';
    return finish({ images, reason, page_url: page.url() });
  } finally {
    await browser.close();
  }
}

function finish(result) {
  process.stdout.write(JSON.stringify(result) + '\n');
}

async function scrollThrough(page) {
  const height = await page.evaluate(() => document.body.scrollHeight).catch(() => 0);
  for (let y = 0; y < Math.min(height, 20000); y += 700) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(150);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(800);
}

function findImagesInPage({ minSide, limit }) {
  const SKIP = /logo|icon|avatar|author|headshot|sprite|badge|sponsor|advert|\bads?\b|banner-ad|pixel|tracking/i;
  const OUTSIDE = 'header, nav, footer, aside, [role="banner"], [role="navigation"], [role="contentinfo"], [role="complementary"]';
  const body = document.querySelector('[itemprop="articleBody"]') || document.querySelector('article') ||
    document.querySelector('main') || document.body;
  const found = [];
  const urls = new Set();
  const add = (url, where, caption) => {
    if (!url || url.startsWith('data:')) return;
    const absolute = new URL(url, location.href).href;
    if (urls.has(absolute)) return;
    urls.add(absolute);
    found.push({ url: absolute, where, caption: caption || null });
  };
  const largest = (img) => {
    const sources = [img.getAttribute('srcset'), img.getAttribute('data-srcset'),
      ...[...(img.closest('picture')?.querySelectorAll('source') || [])].map((s) => s.getAttribute('srcset'))];
    let best = null;
    let bestWidth = 0;
    for (const set of sources.filter(Boolean)) {
      for (const part of set.split(/,\s+(?=\S)/)) {
        const [url, size] = part.trim().split(/\s+/);
        const width = !size ? 1 : size.endsWith('w') ? parseInt(size, 10) : size.endsWith('x') ? parseFloat(size) * 100 : 0;
        if (url && width > bestWidth) { best = url; bestWidth = width; }
      }
    }
    return best || img.currentSrc || img.src || img.getAttribute('data-src');
  };
  const meta = document.querySelector('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"], meta[property="twitter:image"]');
  if (meta && meta.content) add(meta.content, 'share image', null);
  for (const img of body.querySelectorAll('img')) {
    if (found.length >= limit) break;
    if (img.closest(OUTSIDE)) continue;
    const label = [img.alt, img.className, img.id, img.src].join(' ');
    if (SKIP.test(label)) continue;
    const width = img.naturalWidth || img.width;
    const height = img.naturalHeight || img.height;
    if (Math.max(width, height) < minSide && !img.getAttribute('srcset')) continue;
    const figure = img.closest('figure');
    const caption = figure?.querySelector('figcaption')?.innerText.trim().replace(/\s+/g, ' ');
    add(largest(img), 'article', caption);
  }
  return found;
}

async function save(context, candidate, stem) {
  let response;
  try {
    response = await context.request.get(candidate.url, { timeout: 30000 });
  } catch (error) {
    return null;
  }
  if (!response.ok()) return null;
  const data = await response.body();
  let bytes = data;
  let suffix = null;
  if (data[0] === 0xff && data[1] === 0xd8) suffix = '.jpg';
  else if (data.slice(0, 4).toString('latin1') === '\x89PNG') suffix = '.png';
  else {
    bytes = await redraw(context, data, response.headers()['content-type'] || 'image/webp');
    if (!bytes) return null;
    suffix = '.jpg';
  }
  const file = `${stem}${suffix}`;
  fs.writeFileSync(file, bytes);
  const digest = require('crypto').createHash('sha256').update(bytes).digest('hex');
  return { file, digest };
}

async function redraw(context, data, type) {
  if (!type.startsWith('image/') || type.includes('svg')) return null;
  const page = await context.newPage();
  try {
    const dataUrl = await page.evaluate(async ({ b64, type }) => {
      const img = new Image();
      img.src = `data:${type};base64,${b64}`;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      return canvas.toDataURL('image/jpeg', 0.92);
    }, { b64: data.toString('base64'), type });
    return Buffer.from(dataUrl.split(',')[1], 'base64');
  } catch (error) {
    return null;
  } finally {
    await page.close();
  }
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
  throw new Error('The browser is not installed. Run: python3 -m tools.social_runtime.cli setup --project <slug>');
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exit(1);
});
