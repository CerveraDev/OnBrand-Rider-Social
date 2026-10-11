#!/usr/bin/env node

// Makes small preview images for the image catalog page.
//
// Catalog originals are tens of megabytes each, far too heavy for a page that
// shows all of them. Each one is loaded in Chromium once, measured, and saved
// as a narrow JPEG. Called by tools/social_runtime/catalog.py:
//   node tools/social_runtime/make_thumbnails.cjs --job <job.json>
// The result is printed to stdout as JSON; progress goes to stderr.

const fs = require('fs');
const path = require('path');

const WORKERS = 4;
const LOAD_TIMEOUT_MS = 240000;
// The image host refuses some requests when many arrive together; a short wait clears it.
const ATTEMPTS = 3;
const RETRY_WAIT_MS = 4000;

async function main() {
  const jobIndex = process.argv.indexOf('--job');
  if (jobIndex < 0 || !process.argv[jobIndex + 1]) {
    throw new Error('Usage: make_thumbnails.cjs --job <job.json>');
  }
  const job = JSON.parse(fs.readFileSync(process.argv[jobIndex + 1], 'utf8'));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const results = new Array(job.items.length);
  let next = 0;
  let done = 0;
  try {
    const context = await browser.newContext({ viewport: { width: job.width, height: 800 }, deviceScaleFactor: 1 });
    await Promise.all(Array.from({ length: WORKERS }, async () => {
      const page = await context.newPage();
      while (next < job.items.length) {
        const index = next++;
        const item = job.items[index];
        for (let attempt = 1; attempt <= ATTEMPTS; attempt += 1) {
          if (attempt > 1) await new Promise((resolve) => setTimeout(resolve, RETRY_WAIT_MS * (attempt - 1)));
          try {
            await page.setContent(`<body style="margin:0"><img id="i" style="display:block;width:${job.width}px"></body>`);
            const size = await page.evaluate(async ({ url, limit }) => {
              const img = document.getElementById('i');
              img.src = url;
              await Promise.race([
                img.decode(),
                new Promise((resolve, reject) => setTimeout(() => reject(new Error('timed out loading the image')), limit)),
              ]);
              return { width: img.naturalWidth, height: img.naturalHeight };
            }, { url: item.url, limit: LOAD_TIMEOUT_MS });
            fs.mkdirSync(path.dirname(item.output), { recursive: true });
            await page.locator('#i').screenshot({ path: item.output, type: 'jpeg', quality: job.quality });
            results[index] = size;
            break;
          } catch (error) {
            results[index] = { error: String(error.message).split('\n')[0] };
          }
        }
        done += 1;
        process.stderr.write(`thumbnail ${done}/${job.items.length}\n`);
      }
    }));
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({ items: results }) + '\n');
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

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});
