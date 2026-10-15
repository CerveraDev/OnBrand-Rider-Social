#!/usr/bin/env node

// Finds a publication's logo on one of its article pages.
//
// The article is opened in Chromium and the pictures near the top of the page are
// scored: inside the header or navigation, named or labelled as a logo, linking to
// the site's front page, and shaped like a wordmark all count. Social, search,
// menu, and account icons are skipped. The best candidate is kept as the site
// serves it when that is an SVG, and otherwise as a transparent PNG of the logo
// exactly as the page draws it. A logo with almost no dark ink is a white logo
// made for a dark header and would vanish on a white slide, so it is passed over.
// When the header has no usable logo, the publisher logo the article page names in
// its structured data is tried.
//
// Called by tools/social_runtime/press_logo.py, which writes the job file:
//   node tools/social_runtime/find_press_logo.cjs --job <job.json>
// The result is printed to stdout as JSON.

const fs = require('fs');
const path = require('path');

const VIEWPORT = { width: 1440, height: 900 };
const SCALE = 4;
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';
// A visible pixel darker than this brightness (0 to 1) is ink; a logo with less ink
// than this share of its visible pixels is a white logo.
const INK = 0.6;
const MIN_INK_SHARE = 0.03;
const MAX_CANDIDATES = 6;

async function main() {
  const jobIndex = process.argv.indexOf('--job');
  if (jobIndex < 0 || !process.argv[jobIndex + 1]) throw new Error('Usage: find_press_logo.cjs --job <job.json>');
  const job = JSON.parse(fs.readFileSync(process.argv[jobIndex + 1], 'utf8'));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: VIEWPORT, deviceScaleFactor: SCALE, userAgent: USER_AGENT, locale: 'en-US',
    });
    const page = await context.newPage();
    try {
      await page.goto(job.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    } catch (error) {
      return finish({ found: false, reason: `the article page did not open (${error.message.split('\n')[0]})` });
    }
    await page.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1500);
    const title = (await page.title()).toLowerCase();
    const host = new URL(page.url()).hostname.replace(/^www\./, '');
    if (/just a moment|attention required|access denied|are you a robot|captcha/.test(title) || title === host) {
      return finish({ found: false, reason: 'the site blocked the automated visit' });
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    const candidates = await page.evaluate(findCandidatesInPage, MAX_CANDIDATES);
    const passed = [];
    for (const candidate of candidates) {
      const shot = await isolatedScreenshot(page, candidate);
      if (!shot) continue;
      const problem = await unusable(context, shot);
      if (problem) {
        passed.push(`${candidate.describe}: ${problem}`);
        continue;
      }
      const preview = `${job.output_stem}-preview.png`;
      fs.writeFileSync(preview, shot);
      let file = `${job.output_stem}.png`;
      let form = 'png';
      if (candidate.svg_url) {
        const svg = await fetchSvg(context, candidate.svg_url);
        if (svg) {
          file = `${job.output_stem}.svg`;
          form = 'svg';
          fs.writeFileSync(file, svg);
        }
      }
      if (form === 'png') fs.writeFileSync(file, shot);
      return finish({
        found: true, file, preview, form, where: candidate.where, describe: candidate.describe,
        page_url: page.url(), passed_over: passed,
      });
    }
    const published = await page.evaluate(publisherLogoInPage);
    if (published) {
      const fetched = await download(context, published);
      if (fetched) {
        const shot = await pictureOf(context, fetched);
        const problem = shot ? await unusable(context, shot, true) : 'it could not be drawn';
        if (!problem) {
          const preview = `${job.output_stem}-preview.png`;
          fs.writeFileSync(preview, shot);
          const file = `${job.output_stem}.${fetched.form}`;
          fs.writeFileSync(file, fetched.convert ? shot : fetched.body);
          return finish({
            found: true, file, preview, form: fetched.form, where: "article's publisher details",
            describe: published, page_url: page.url(), passed_over: passed,
          });
        }
        passed.push(`publisher logo: ${problem}`);
      }
    }
    const reason = passed.length
      ? `no usable logo on the article page (${passed.join('; ')})`
      : 'no logo in the page header or navigation';
    return finish({ found: false, reason, page_url: page.url() });
  } finally {
    await browser.close();
  }
}

function finish(result) {
  process.stdout.write(JSON.stringify(result) + '\n');
}

// Runs in the page. Returns the likeliest logos, best first, each tagged so it can be found again.
function findCandidatesInPage(limit) {
  const SKIP = /facebook|twitter|x-logo|instagram|linkedin|youtube|tiktok|pinterest|whatsapp|threads|rss|search|menu|hamburger|close|avatar|account|profile|user|arrow|chevron|caret|app-?store|google-?play|podcast|sponsor|advert|\bad\b|weather|flag|share|print|mail|bell|play-button/;
  const LOGO = /logo|brand|masthead|wordmark|site-?title|site-?name/;
  const host = location.hostname.replace(/^www\./, '');
  const siteName = (document.querySelector('meta[property="og:site_name"]')?.content || host.split('.')[0]).toLowerCase();
  const nameTokens = siteName.split(/[^a-z0-9]+/).filter((token) => token.length > 2);
  const label = (el) => [
    el.id, typeof el.className === 'string' ? el.className : el.className?.baseVal, el.getAttribute('alt'),
    el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('src'),
    el.querySelector?.('title')?.textContent, el.querySelector?.('use')?.getAttribute('href'),
  ].filter(Boolean).join(' ').toLowerCase();
  const homeLink = (el) => {
    const link = el.closest('a[href]');
    if (!link) return false;
    try {
      const target = new URL(link.href, location.href);
      return target.hostname.replace(/^www\./, '') === host && target.pathname.split('/').filter(Boolean).length <= 1;
    } catch (error) {
      return false;
    }
  };
  const found = [];
  const elements = [...document.querySelectorAll('img, svg')].filter((el) => !el.parentElement.closest('svg'));
  for (const el of elements) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width < 40 || rect.height < 10 || rect.top > 400 || rect.bottom < 0 || rect.width > 700) continue;
    if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0) continue;
    if (el.closest('footer, [role=contentinfo]')) continue;
    const own = label(el);
    const link = el.closest('a');
    const around = [own, link && label(link), link?.getAttribute('href')].filter(Boolean).join(' ');
    if (SKIP.test(own) && !LOGO.test(own)) continue;
    const inHeader = Boolean(el.closest('header, nav, [role=banner], [class*="header" i], [id*="header" i], [class*="masthead" i], [class*="navbar" i], [class*="nav-bar" i]'));
    let score = 0;
    if (inHeader) score += 3;
    if (LOGO.test(around)) score += 4;
    if (homeLink(el)) score += 3;
    if (nameTokens.some((token) => around.includes(token))) score += 2;
    const ratio = rect.width / rect.height;
    if (ratio >= 1.5 && ratio <= 12) score += 1;
    if (el.tagName.toLowerCase() === 'svg') score += 1;
    if (score < 5) continue;
    const tag = `onbrand-logo-${found.length}`;
    el.setAttribute('data-onbrand-logo', tag);
    let svgUrl = null;
    if (el.tagName === 'IMG') {
      const source = el.currentSrc || el.src;
      if (/\.svg(\?|#|$)/i.test(source) || source.startsWith('data:image/svg')) svgUrl = source;
    }
    found.push({
      tag, score, svg_url: svgUrl, where: inHeader ? 'page header' : 'top of the page',
      describe: `${el.tagName.toLowerCase()} ${Math.round(rect.width)}x${Math.round(rect.height)}${own ? ` "${own.slice(0, 60)}"` : ''}`,
      top: rect.top,
    });
  }
  return found.sort((a, b) => b.score - a.score || a.top - b.top).slice(0, limit);
}

// A transparent PNG of the logo alone: everything else on the page is made invisible.
async function isolatedScreenshot(page, candidate) {
  const box = await page.evaluate((tag) => {
    const el = document.querySelector(`[data-onbrand-logo="${tag}"]`);
    if (!el) return null;
    const style = document.createElement('style');
    style.id = 'onbrand-isolate';
    style.textContent = `html, body { background: transparent !important; }
      body * { visibility: hidden !important; }
      [data-onbrand-logo="${tag}"], [data-onbrand-logo="${tag}"] * { visibility: visible !important; }`;
    document.head.append(style);
    const rect = el.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }, candidate.tag);
  if (!box) return null;
  try {
    return await page.screenshot({ clip: box, omitBackground: true, type: 'png' });
  } catch (error) {
    return null;
  } finally {
    await page.evaluate(() => document.getElementById('onbrand-isolate')?.remove());
  }
}

// Why a captured logo cannot go on a white slide, or null when it can.
async function unusable(context, png, wordmark = false) {
  const tone = await measure(context, png);
  if (tone.visible < 50) return 'nothing visible';
  if (tone.ink < MIN_INK_SHARE * tone.visible) return 'a white logo made for a dark header';
  if (wordmark && tone.width < 1.5 * tone.height) return 'a square icon, not a wordmark';
  return null;
}

// Runs in the page. The publisher logo the article names in its structured data, if any.
function publisherLogoInPage() {
  const urls = [];
  const visit = (node, publisher) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach((item) => visit(item, publisher));
    const types = [].concat(node['@type'] || []);
    const isPublisher = publisher || types.includes('Organization') || types.includes('NewsMediaOrganization');
    if (isPublisher && node.logo) {
      const logo = [].concat(node.logo)[0];
      const url = typeof logo === 'string' ? logo : logo && (logo.url || logo.contentUrl);
      if (url) urls.push(url);
    }
    for (const [key, value] of Object.entries(node)) visit(value, key === 'publisher' || (isPublisher && key === '@graph'));
  };
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      visit(JSON.parse(script.textContent), false);
    } catch (error) {
      // Malformed structured data is ignored.
    }
  }
  const found = urls[0];
  return found ? new URL(found, location.href).href : null;
}

async function download(context, url) {
  try {
    const response = await context.request.get(url, { timeout: 20000 });
    const body = await response.body();
    if (!response.ok() || body.length > 5_000_000) return null;
    if (body.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return { form: 'png', body };
    if (body[0] === 0xff && body[1] === 0xd8) return { form: 'jpg', body };
    if (/<svg\b/i.test(body.subarray(0, 4096).toString())) {
      return /<script|<!entity|<foreignobject/i.test(body.toString()) ? null : { form: 'svg', body };
    }
    const type = response.headers()['content-type'] || '';
    return /^image\//.test(type) ? { form: 'png', body, type, convert: true } : null;
  } catch (error) {
    return null;
  }
}

// A transparent PNG of a downloaded logo, drawn in a blank page, for checking and for formats slides cannot take.
async function pictureOf(context, fetched) {
  const page = await context.newPage();
  try {
    const type = fetched.type || { png: 'image/png', jpg: 'image/jpeg', svg: 'image/svg+xml' }[fetched.form];
    await page.setContent(`<img id="logo" style="height:120px;width:auto" src="data:${type};base64,${fetched.body.toString('base64')}">`);
    const ok = await page.evaluate(() => document.getElementById('logo').decode().then(() => true, () => false));
    return ok ? await page.locator('#logo').screenshot({ omitBackground: true, type: 'png' }) : null;
  } finally {
    await page.close();
  }
}

// Ink and visible pixels of a logo, measured in a blank page.
async function measure(context, png) {
  const page = await context.newPage();
  try {
    return await page.evaluate(async ({ data, threshold }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${data}`;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d');
      context.drawImage(image, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let visible = 0;
      let ink = 0;
      for (let index = 0; index < pixels.length; index += 4) {
        if (pixels[index + 3] < 128) continue;
        visible += 1;
        if ((0.2126 * pixels[index] + 0.7152 * pixels[index + 1] + 0.0722 * pixels[index + 2]) / 255 < threshold) ink += 1;
      }
      return { visible, ink, width: canvas.width, height: canvas.height };
    }, { data: png.toString('base64'), threshold: INK });
  } finally {
    await page.close();
  }
}

async function fetchSvg(context, url) {
  try {
    if (url.startsWith('data:image/svg')) {
      const [, meta, body] = url.match(/^data:image\/svg\+xml(;base64)?,(.*)$/s) || [];
      if (body === undefined) return null;
      return meta ? Buffer.from(body, 'base64') : Buffer.from(decodeURIComponent(body));
    }
    const response = await context.request.get(url, { timeout: 20000 });
    const body = await response.body();
    if (!response.ok() || body.length > 2_000_000 || !/<svg\b/i.test(body.subarray(0, 4096).toString())) return null;
    if (/<script|<!entity|<foreignobject/i.test(body.toString())) return null;
    return body;
  } catch (error) {
    return null;
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
