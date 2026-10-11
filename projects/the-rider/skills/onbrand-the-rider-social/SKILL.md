---
name: onbrand-the-rider-social
description: Explicitly invoked workflow for creating Rider Residences Instagram posts and carousels from the project's approved layouts, with a phone-style preview of the finished post.
metadata:
  short-description: Build Rider Residences social posts
---

# OnBrand Design: The Rider Social

Run this skill only when the user explicitly invokes `$onbrand-the-rider-social` in Codex or `/onbrand-the-rider-social` in Claude Code. Do not infer invocation from an ordinary request involving Rider, Instagram, social posts, or images.

Use this skill for Rider Residences single-image posts and carousels only. Reels, stories, email, and other properties are out of scope. Email belongs to `onbrand-the-rider-email`, which is also explicit-only; never start it from here.

Run every command from the repository root. The social runtime at `tools/social_runtime/` does the work; this skill decides what to ask, writes a short brief, and runs it.

## What The User Can Ask For

| The user wants | Do this |
|---|---|
| To see the layouts | `python3 -m tools.social_runtime.cli gallery --project the-rider` |
| To see the official images | `python3 -m tools.social_runtime.cli images --project the-rider` |
| A post or carousel | Follow the workflow below |
| To set up, or a command says the slide renderer or Node.js is missing | `python3 -m tools.social_runtime.cli setup --project the-rider` |
| The latest layouts and images | `python3 -m tools.social_runtime.cli update --project the-rider` |

Both pages open in the user's browser on their own; do not send the user looking for a file. The first run of the image page takes about a minute while it makes previews. Each page has a bar that turns the user's picks into a line they can paste back to you, such as "Make an Editorial Carousel using layouts SP-04, SC-02, SG-03 in that order."

## Setup And Updates

- **First use in a folder.** If there is no `node_modules` folder at the repository root or under `tools/email_render_matrix/`, run `setup` before anything else and tell the user it is a one-time step of a few minutes that downloads a browser of about 150 MB. It prints one line per check and ends with "Ready."; if a line reports a problem, relay it in plain words. Node.js is the one thing it cannot install: the user installs it from https://nodejs.org and you run `setup` again.
- **Updates.** `update` fetches the latest published layouts, image list, and image approvals, which always arrive as a matching set, then repeats the setup checks. Run it when the user asks for it or asks whether there are new layouts or images. Never fetch or edit the image list any other way.

## Workflow

1. **Layouts.** If the user named layouts, use them in that order. If not, either offer to open the layout gallery or propose a sequence and say which layouts you chose. Read the current rules with `python3 -m tools.social_runtime.cli layouts --project the-rider`; it lists the post types, which layouts go where, each layout's image areas with the shape they need, and each text field's line limit and approximate length.
2. **Images.** See [Choosing images](#choosing-images).
3. **Text.** See [Text](#text).
4. **Brief.** Write the brief to `campaign-output/social/briefs/<slug>.json` in the format described in [references/brief.md](references/brief.md).
5. **Build.** Run `python3 -m tools.social_runtime.cli post --brief campaign-output/social/briefs/<slug>.json`. It works out the post type, builds the package, renders every slide, and opens the phone-style preview in the user's browser.
6. **Read the result.** The command prints a summary. Exit code 0 means every check passed. Exit code 2 means it was refused before building; the message says what to change in the brief. Exit code 1 means a check failed; `failed_checks` names it. The usual one is `text:<field>: N of M lines`, which means that text wraps onto more lines than the layout allows: shorten it or move a line break, then run the command again. Never edit the output by hand to get around a refusal or a failed check.
7. **Report.** Tell the user the preview is open, where the slide images are (`slides/branded/slide-NN.jpg` inside the package folder in the summary), and anything in `warnings` they need to know, in plain words. Offer changes; a change is an edit to the brief and another run.

## Choosing Images

- **The user's own images win.** If the user gives a file, a folder, or an attachment, use those images. Any layout accepts them. Use `{"file": "<path>"}`.
- **Use the catalog when the request points to official project imagery**, such as "the rooftop pool rendering" or "an amenities carousel". Find candidates with `python3 -m tools.social_runtime.cli images --project the-rider --list --find <word>`, which prints each image's name, subject, shape, and whether it is ready or needs a crop. Use `{"catalog": "<file name>"}` with the exact name.
- **If it is unclear which the user means, ask.** Do not guess between their photo and a catalog image.
- **Shape matters.** Each image area needs a portrait, landscape, or square image. A user's file of the wrong shape is refused; ask for another image or choose a layout that fits. Files must be PNG or JPEG; ask the user to export HEIC photos as JPEG.
- **Catalog images that need a crop** are placed centred in their area automatically and reported as a planned crop. Tell the user the framing is automatic and centred, since this workflow cannot move it.
- **An attachment you cannot reach as a file** cannot be used. Ask the user to save it and give you its path.
- **Images made or changed by AI.** This skill does not generate or edit images. If the user asks for an image to be created, extended, or retouched, that is separate from this skill: do it only if you have an image tool of your own, say that it runs on the user's own account, and say plainly that the result is AI-generated or AI-altered. The build records such a file as supplied by the user and keeps no note that AI was involved, so remind the user that disclosing it, and the consent of any real person shown, are theirs to handle.
- **Do not judge rights.** A user's own image is recorded as supplied by them, not as approved by the project. Say so once when you report: permission to post it, and the consent of anyone in it, are theirs to confirm.
- Photo gallery layouts (`SG-*`) also take a portrait `background` image, which shows dimly behind the photos.

## Text

- **Use the user's words exactly** when they provide them. Do not rewrite approved copy to make it fit; say what does not fit and let them decide.
- **When the user asks you to write the text**, write it, say plainly that it is your draft, and keep it true: no prices, dates, availability, square footage, incentives, or claims that the user or [the project profile](../../profile.json) did not give you.
- A line break is a newline (`\n` in the brief). In a field that allows it, `*word*` sets a word or phrase in italics; elsewhere asterisks would print as typed, so leave them out.
- Stay within each field's line limit. The character figures are approximate guides, not rules; the build measures the real line count.
- Every slide needs alt text: one plain sentence describing the image, about 100 characters at most.
- The caption can run long; the preview shows how it is cut off in the feed. Hashtags are separate, each written as `#Word`.
- Use the names in the project profile: "The Rider Residences" as the official name and `theriderresidences` as the Instagram handle.

## Press Carousels

Two post types present press coverage. The build recognises each from its layouts; you do not name the type.

| Post type | Use it for | Slides |
|---|---|---|
| Multi-press carousel | Coverage from several outlets | `PC-01` as the cover, which stands for the whole set, then one `PC-02` per outlet (2 to 10 slides) |
| Press article carousel | One article, read across a carousel | `AC-01` as the cover, then up to two of `AC-02` (a quote) and `AC-03` (a piece of the article, with a landscape image if there is one), then `AC-04` as an optional last slide inviting people to read more (2 to 4 slides) |

- **Quote and article text must be the publication's exact words**, given by the user or copied from the article they gave you. Never write, paraphrase, shorten, or tidy a quote, and never invent a byline, date, outlet, or photographer credit. If something is missing, ask.
- **The publication's logo** goes bottom left on `AC-01` to `AC-04` and is optional: `"publication-logo": {"file": "<path>"}`, a PNG or JPEG of any shape. Give it on one slide and it appears on every slide of the carousel that has the space; leave it out of the whole brief and the space stays empty. It is another organisation's logo, so tell the user once that permission to use it is theirs to confirm. The Rider logo on the right is fixed.
- **Optional parts** are left out by leaving them out of the brief: the photographer `credit` on `AC-01`, the image and second paragraph (`body-2`) on `AC-03`.
- **The small logo on the photo in `PC-02`** shows unless the slide says `"hide": ["photo-logo"]`.
- **Fixed words** cannot be changed: "SWIPE" on `PC-01`, and on `AC-04` the eyebrow "There's more to the story" and the "Link in bio" button. Only the `AC-04` subheading is yours to fill.
- The eyebrow on `PC-01` and `PC-02` is black like all other text on a white block.

## Text And Logo Colour

- **Text is white (`#ffffff`) or black (`#000000`), nothing else.** The build chooses between them; the brief has no colour setting. If the user asks for any other text colour, or for a gradient on text or on a word, say that the brand allows only white or black text and do not attempt it by any route.
- **The build picks the colour from the image.** Where the image behind the text or logo is light, the text turns black, the logo is swapped for the black logo, and the dark scrim becomes a white scrim of the same strength. Where the image is dark, text on it is white. Text that is not on an image, such as a heading on a black bar or on a white block, stays as the layout has it.
- **Tell the user when it happens.** The summary lists each change under `adjustments`; report them in plain words, for example "slide 2 has a light photo, so its text and logo are black".
- **You cannot force the choice.** If the user disagrees with it, the fix is a different image or a different layout. A warning that an image is "light in some places and dark in others" means some text may be hard to read; look at the slide and suggest another image or layout if so.

## What This Skill Does Not Do

- **It makes previews, not approved releases.** Every build is a draft preview: the post types and the export sizes are still awaiting owner approval, and the runtime refuses a release build until they are approved. The slide images are full size and usable, but say they are previews.
- **It does not post.** Nothing is sent to Instagram or any other service.
- **It does not crop or retouch images**, generate images, or make video.
- **It serves the in-house team only.** There is no outside-broker version yet.
- Do not edit the scaffold, the templates, the image approvals, or anything under `tools/`. If a request needs one of those changed, say so and stop.

## References

- [references/brief.md](references/brief.md): the brief format, with an example
- [examples/mixed-carousel.brief.json](examples/mixed-carousel.brief.json): a working three-slide brief
- `tools/social_runtime/README.md`: how the runtime builds, renders, and checks a post
