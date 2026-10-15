# Social Runtime

Phase 17 sibling of `tools/rider_campaign_runtime/`. It builds reviewable static-post and carousel packages from a canonical social spec, the project's social approval overlay, and templates that sequence the frames of the project's social scaffold. It imports nothing from the email runtime and never reads `data/agents/`.

```bash
python3 -m tools.social_runtime.cli build --spec projects/the-rider/social/examples/feature-carousel.preview.json
```

Exit code 0 means blocking QA passed, 1 means QA failed, and 2 means the build was refused before packaging, with the specific reason on stderr.

## One-step post from a brief

```bash
python3 -m tools.social_runtime.cli post --brief campaign-output/social/briefs/<slug>.json
```

A brief is the short form: the layouts in order, an image and text for each area, alt text, the caption, and hashtags. `brief.py` expands it into a full spec (written to `campaign-output/social/specs/<slug>.json`), choosing the post type and slide roles from the layouts, planning a centred crop for a catalog image that cannot be used as it is, and writing a draft content unit for every piece of text. The command then builds, renders, and opens the feed preview. A composed spec is always an in-house `composition-preview`. The format is documented in `projects/the-rider/skills/onbrand-the-rider-social/references/brief.md`.

`layouts --project <slug>` prints the post types and each layout's image areas and text limits as text, and `images --project <slug> --list [--find <text>]` prints the image catalog as text; both exist so a skill can read them without opening a page.

## What a build produces

`<output_dir>/<slug>/` holds `social-package.json` (slides, copy, and image references per variant), `asset-manifest.json` (used records and crop provenance, without Dropbox identifiers or paths), `preview.html` (a review sheet), and `qa-report.json`. A ZIP is written only when QA passes and the mode is not `smoke-test`.

The build step records where approved text and approved images go. The render step then produces the slide images:

```bash
python3 -m tools.social_runtime.cli render --package campaign-output/social/<slug>
```

It fills each slide's frame in the project scaffold (`projects/<slug>/social/scaffold/scaffold.html`) in Chromium and writes `slides/<variant>/slide-NN.jpg` at the format's pixel size, plus `render-report.json`, then rebuilds the ZIP. Exit code 0 means every render check passed, 1 means a check failed, and 2 means the render was refused. It needs Node and the Playwright install described in `tools/email_render_matrix/README.md`, and network access for the logo, fonts, and catalog images.

The render also writes `simulator.html`: a phone-sized feed preview of the rendered slides that can be swiped (or dragged, or stepped with the arrow keys), with position dots, the caption with its "more" cut-off, hashtags, each slide's alt text, and a dark mode. The phone keeps its proportions and scales to fill the browser window. It is a generic mock for review, not a copy of any platform's interface. The account handle and picture come from the project profile, `projects/<project>/profile.json` (`social.instagram_handle` and `social.avatar`, a PNG or JPEG path relative to the project folder); without them the project slug and the account's initial stand in.

`python3 -m tools.social_runtime.cli gallery --project <slug>` writes `projects/<slug>/social/scaffold/gallery.html` and opens it in the browser: every scaffold layout with its preview, the photos and text it takes, and the post types that accept it. Layouts can be lined up into a sequence, which the page checks against the project's templates and turns into a line to paste into a request. Add `--no-open` to write it without opening it. Regenerate it after a scaffold import or a template change.

`python3 -m tools.social_runtime.cli images --project <slug>` writes the image catalog page to `campaign-output/social/<slug>-image-catalog/catalog.html` and opens it in the browser: every image approved for social use, grouped by subject, with filters for subject and shape, a file-name search, pixel sizes, and whether an image is ready to use or needs a crop. Images can be collected into a line to paste into a request. The originals are 8 to 32 MB each, so the first run makes a small preview of each one (about a minute for The Rider's 133 images) and later runs reuse them. The page links to the originals, so it lives under `campaign-output/` and is not committed.

Render checks: each slide is the format's exact size and under its file-size ceiling, the logo loaded, and every text slot stays within its frame's `max_lines` and inside the slide. In slide text, a line break is a newline, and in a slot with an italic accent `*word*` is set in italics, with the scaffold's spacing applied around it (two non-breaking spaces before, one after) when it shares a line with upright words. Every image area cover-fits. If `social/scaffold/overrides.css` exists it is applied on top of `scaffold.css`; it holds owner-directed adjustments that the Elementor page does not carry yet and is never touched by a re-import. The render step does not crop: a planned crop is rendered from its uncropped source and reported as a warning. See LIM-023.

## Inputs

| Input | Location |
|---|---|
| Format sidecar | `tools/social_runtime/platform-formats.json` |
| Templates | `projects/<slug>/social/templates/<CODE>.json` |
| Frame definitions | `projects/<slug>/social/templates/frames.json`, generated from `social/scaffold/frame-catalog.json` |
| Social approvals | `projects/<slug>/asset-approvals.social.json` |
| Manifest | the `local_cache_path` in `projects/<slug>/manifest-source.json` |

## Frames and templates

A frame is one slide layout from the owner's scaffold: its image slots with their sizes and shapes, its text slots with draft line and character limits, and its locked content such as the logo. A template says which frames may appear at each position. Each slide in a spec names its `frame` and fills every image slot under `images` and every text slot under `text`.

After the scaffold is re-imported with `tools/social_scaffold/import_scaffold.cjs`, regenerate the definitions; a test fails while they are out of date:

```bash
python3 -m tools.social_runtime.cli frames --project the-rider
```

An image slot takes a directly approved asset only when the asset's orientation equals the slot's shape. Any other use needs a declared crop whose geometry matches the slot and whose output is the slot's size in export pixels. Every image slot cover-fits its image. 4:5 formats export at 1200x1500, the scaffold canvas at 2x.

### Supplied images

A template whose `image_sources` lists `user-supplied` lets a slide take a local file that is not in the approved catalog, which is how event photography reaches the gallery template `GAL-01`:

```json
"images": {"image-1": {"supplied": "~/Pictures/top-off/crowd-toast.jpg"}}
```

The path may be absolute or relative to the spec. The file must be a PNG or JPEG whose orientation, after the JPEG EXIF orientation tag is applied, equals the slot's shape. It is copied into the package as `images/supplied-<hash>` and listed under `supplied` in `asset-manifest.json`; the original path is not recorded. A supplied image is not an owner-approved record: every build that uses one carries a warning that rights and approval rest with the person who supplied it, and an image smaller than its slot is reported as enlarged.

## Build modes

| Mode | Variants built | Draft template, draft copy, unverified format, planned crop | ZIP |
|---|---|---|---|
| `composition-preview` | Representative only | Allowed, reported as warnings | Yes |
| `smoke-test` | All | Draft copy and planned crops refused | Never |
| `release` | All | All refused | Yes |

An `outside-broker` build needs an approved template that lists that audience, resolves images only from the filtered broker catalog, and cannot declare `cross_medium`.

## Modules

- `schema.py`: spec shape validation, no file access.
- `formats.py`: the pinned sidecar; an absent format fails rather than defaulting.
- `frames.py`: frame definitions derived from the scaffold catalog, with estimated draft text limits.
- `templates.py`: frame sequences with audience availability; resolves each slide to its frame. A sequence step may carry `"cap": {"frames": [...], "max": n}` to limit how many of its slides use those frames while the rest of its frames stay unlimited.
- `assets.py`: resolution against the overlay, and the broker-safe catalog filter.
- `generated.py`: which layouts take an AI-generated image, from the project's `social/generated-images.json` (every layout except its `excluded_layouts`; no file, no generated images), and the record each one must carry. A spec image `{"generated": {"file", "prompt", "tool", "based_on"}}` is checked like a supplied file, packaged under a `generated-` name, listed under `generated` in `asset-manifest.json`, and reported as a warning; a template must list `ai-generated` in `image_sources`.
- `supplied.py`: format and orientation checks for an image supplied outside the approved catalog.
- `crops.py`: provenance validation, against the image slot it fills, for a crop produced elsewhere.
- `copy_allocation.py`: one approved owner per text surface, in-carousel repetition, and cross-medium repetition against an email campaign spec.
- `render.py`, `render_slides.cjs`: slide export from the scaffold, and the render report.
- `qa.py`, `runtime.py`, `cli.py`: blocking QA, packaging, and the command line.


## Text and logo colour

Text and the logo are white over a dark scrim by default. During render, the text and logo on each image are hidden, the scrim is lifted, and the brightness of the image behind them is measured (relative luminance, 0 to 1, weighted by area). Above `LIGHT_IMAGE_THRESHOLD` in `render.py` (0.45, a draft value) everything on that image is set in `#000000`, the logo is replaced with the profile's `social.logo_on_light`, and every translucent scrim layer keeps its opacity but turns white. Text and logos that are not on an image, such as a heading on a black bar, are left alone.

Each change is listed under `adjustments` in `render-report.json` and in the `post` summary. A `text-colour` check fails the render if any text slot ends up in a colour other than plain `#ffffff` or `#000000`, or clipped to a background. Specs and briefs have no colour field.

## Scaffold additions, optional parts, and logo areas

`projects/<slug>/social/scaffold/additions.json` is applied by `tools/social_scaffold/import_scaffold.cjs` on top of the Elementor page at every import. It renames slots the importer cannot infer, marks slots as locked (fixed words) or optional, edits a frame's markup, and adds frames copied from an existing one. Remove an entry once the Elementor page carries the same change.

`projects/<slug>/social/scaffold/text-limits.json` holds text limits the owner has decided, by layout and slot (`max_chars`, `max_lines`, or both). The `frames` command applies them over the estimated limits, so they survive regeneration; a limit for a slot the layout does not have is refused. The Rider sets `AC-01` `heading` to 68 characters and `AC-04` `subheading` to 100, each on up to three lines.

In `frames.json`, an image slot carries `required` and a `fit` of `cover` or `contain`. A `contain` slot (shape `any`) holds another organisation's logo: it takes a supplied file only, a PNG, JPEG, or SVG of any shape, fitted inside the area from its left edge. An SVG is sized from its `viewBox` and refused if it carries scripts or embedded content. In a brief, a logo given on one press article (`AC-*`) slide is used on every `AC-*` slide; each `PC-02` slide is its own outlet and keeps only its own logo.

## AI-generated images with Codex ImageGen

Codex ImageGen is the only image generator the skill uses (`ALLOWED_TOOLS` in `generated.py`). Codex uses its built-in tool directly. Elsewhere, `image --project <slug> --shape <portrait|landscape|square> --output <path.png> --prompt <text> [--based-on <catalog file name>]` runs `imagegen.py`: one `codex exec` turn with `--ignore-user-config`, the prompt on stdin, and any catalog base image downloaded and attached with `-i`. Codex signs in with the user's ChatGPT account, so no API key is used. The command checks that a PNG or JPEG was saved and prints the brief entry. It finds Codex on the `PATH`, in `.cache/codex-cli/` where `setup` installs `@openai/codex` when the machine has none, or bundled with the ChatGPT desktop app. `setup` fails until Codex is installed and signed in, and opens the browser sign-in when it is not.

## Press logos

`press-logo --url <article>` runs `find_press_logo.cjs`: it opens the article in Chromium, scores the pictures near the top of the page (in the header or navigation, named as a logo, linking to the front page, wordmark-shaped), and keeps the best one, as the site's own SVG when it serves one and otherwise as a transparent PNG of the logo as drawn. A logo with almost no dark ink is a white logo for a dark header and is passed over. When the header has none, the publisher logo in the page's structured data is tried. The logo and a `-preview.png` are saved under `campaign-output/social/logos/<outlet>`. Exit code 0 means found, 1 means none was found (the reason is printed), 2 means the search was refused. Sites that block automated visits cannot be read; see LIM-024. `optional_marks` lists fixed marks a slide may leave off with `hide`. At render, optional text and image areas a slide does not fill, and marks it hides, are taken off the slide; a logo keeps its place so its neighbour does not move.

## Setup, updates, and the social-only distribution

`setup --project <slug>` checks Python and Node.js, installs the Playwright package where the workspace declares it (the root `package.json` in a social-only workspace, `tools/email_render_matrix/` in this repository), installs Chromium, and confirms the image list and its approvals load. `update --project <slug>` runs `git pull --ff-only` and then the same checks.

`python3 -m tools.social_export.export --project <slug> --output <directory>` builds the social-only workspace that is published as its own repository. It keeps an existing `.git` folder in the output, so refreshing the published repository is: export into its clone, review the diff, commit, push. The export is refused when the social approvals are not bound to the current image list.
