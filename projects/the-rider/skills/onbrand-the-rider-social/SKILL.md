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

- **First use in a folder.** If there is no `node_modules` folder at the repository root or under `tools/email_render_matrix/`, run `setup` before anything else and tell the user it is a one-time step of a few minutes that downloads a browser of about 150 MB and sets up Codex ImageGen for AI images. If the machine has no Codex, it installs it into the folder; if Codex is not signed in, a browser window opens for the user to sign in with their ChatGPT account. Tell the user that before you run it. Setup is not finished until it says "Codex ImageGen: ok". It prints one line per check and ends with "Ready."; if a line reports a problem, relay it in plain words. Node.js is the one thing it cannot install: the user installs it from https://nodejs.org and you run `setup` again.
- **Updates.** `update` fetches the latest published layouts, image list, and image approvals, which always arrive as a matching set, then repeats the setup checks. Run it when the user asks for it or asks whether there are new layouts or images. Never fetch or edit the image list any other way.

## Workflow

1. **Layouts.** If the user named layouts, use them in that order. If not, either offer to open the layout gallery or propose a sequence and say which layouts you chose. Read the current rules with `python3 -m tools.social_runtime.cli layouts --project the-rider`; it lists the post types, which layouts go where, each layout's image areas with the shape they need, and each text field's line limit and approximate length. When you choose layouts yourself, shortlist them by their labels first; see [Layout labels](#layout-labels).
2. **Images.** See [Choosing images](#choosing-images).
3. **Text.** See [Text](#text).
4. **Brief.** Write the brief to `campaign-output/social/briefs/<slug>.json` in the format described in [references/brief.md](references/brief.md).
5. **Build.** Run `python3 -m tools.social_runtime.cli post --brief campaign-output/social/briefs/<slug>.json`. It works out the post type, builds the package, renders every slide, and opens the phone-style preview in the user's browser.
6. **Read the result.** The command prints a summary. Exit code 0 means every check passed. Exit code 2 means it was refused before building; the message says what to change in the brief. Exit code 1 means a check failed; `failed_checks` names it. The usual one is `text:<field>: N of M lines`, which means that text wraps onto more lines than the layout allows: shorten it or move a line break, then run the command again. Never edit the output by hand to get around a refusal or a failed check.
7. **Report.** Tell the user the preview is open, where the slide images are (`slides/branded/slide-NN.jpg` inside the package folder in the summary), and anything in `warnings` they need to know, in plain words. Offer changes; a change is an edit to the brief and another run.

## Layout Labels

Each layout carries the owner's labels, shown at the end of its line in `layouts` and on its card in the gallery: one or two purposes (main purpose first), a tone, and what it holds. When you choose layouts yourself:

1. **Shortlist by purpose.** For each slide, keep the layouts whose purposes include that slide's job:
   - **introduce:** opens the piece.
   - **showcase:** presents one feature of the property, mostly through a photo.
   - **explain:** gives information to read.
   - **quote:** sets someone else's words apart, with their name or source.
   - **gallery:** lets several photos carry the message.
   - **invite:** asks the reader to act.
   - **close:** ends the piece.
2. **Then by what it holds.** Keep the layouts that hold what the user has:
   - `quote` for a quotation.
   - `long text` for a paragraph.
   - `short headline` for a heading.
   - `several photos`, `single photo`, or `no photo` for the images available.
   - `outlet logo` for a publication's logo.
3. **Then choose by tone and the post type's rules.** The tones are editorial, bold, quiet, and warm. Say which layouts you chose and why.

If no layout fits a slide, say so and what is missing; do not force a layout that does not fit. Labels guide the choice only: the post type rules and the build's checks still decide what is allowed, and layouts the user names are used as named.

## Choosing Images

- **The user's own images win.** If the user gives a file, a folder, or an attachment, use those images. Any layout accepts them. Use `{"file": "<path>"}`.
- **A press carousel uses the article's own photos**, never catalog images chosen on your own. See [The Article's Photos](#the-articles-photos).
- **Use the catalog when the request points to official project imagery**, such as "the rooftop pool rendering" or "an amenities carousel". Find candidates with `python3 -m tools.social_runtime.cli images --project the-rider --list --find <word>`, which prints each image's name, subject, shape, and whether it is ready or needs a crop. Use `{"catalog": "<file name>"}` with the exact name.
- **If it is unclear which the user means, ask.** Do not guess between their photo and a catalog image.
- **Shape matters.** Each image area needs a portrait, landscape, or square image. A user's file of the wrong shape is refused; ask for another image or choose a layout that fits. Files must be PNG or JPEG; ask the user to export HEIC photos as JPEG.
- **Catalog images that need a crop** are placed centred in their area automatically and reported as a planned crop. Tell the user the framing is automatic and centred, since this workflow cannot move it.
- **An attachment you cannot reach as a file** cannot be used. Ask the user to save it and give you its path.
- **Images made or changed by AI** follow [AI-Generated Images](#ai-generated-images). Never pass one off as the user's own file.
- **Do not judge rights.** A user's own image is recorded as supplied by them, not as approved by the project. Say so once when you report: permission to post it, and the consent of anyone in it, are theirs to confirm.
- Photo gallery layouts (`SG-*`) also take a portrait `background` image, which shows dimly behind the photos.

## AI-Generated Images

When the user asks for an image to be created, extended, or changed with AI, you may make it for a layout that takes one. Do this only when the user asks; never generate an image on your own to fill a gap.

- **Which layouts.** Every layout takes an AI-generated image except `SC-04` to `SC-07` and `SG-02` to `SG-07`. The `layouts` command says "AI-generated image: yes" or "no" for each. The publication-logo area never takes one.
- **Use only Codex ImageGen.** It is the one image generator the skill uses, and the build refuses any other `tool`. When you are Codex, use your built-in image tool. In any other assistant, such as Claude Code, run:

  `python3 -m tools.social_runtime.cli image --project the-rider --shape <portrait|landscape|square> --output campaign-output/social/generated/<slug>/candidate-<n>.png --prompt "<what to show>" [--based-on <catalog file name>]`

  It makes the image with Codex ImageGen through the Codex command line, signed in with the user's ChatGPT account, and prints the brief entry to use. It takes about a minute. Run it once per candidate.
- **Never ask for an API key, and never use another tool.** No OpenAI API key, Canva, Adobe Firefly, Midjourney, Gemini, or any other connector or app, even when one is connected. If `image` says Codex is not installed or not signed in, run `setup`, which installs it and asks for the one-time sign-in, then try again. Say that images are made on the user's own ChatGPT account.
- **Start from an official image for any real Rider place.** For the building, an amenity, or an interior, pick a catalog image as the base and keep the architecture and the room as they are. Find it with `python3 -m tools.social_runtime.cli images --project the-rider --list --find <word>` and pass its exact file name to `--based-on`; the command downloads it and gives it to Codex as the base. An image not based on a catalog image is for a concept only, at the user's request; say that it is conceptual.
- **Keep the image clean.** No text, logos, or signage in it; the layout adds the text and the logo. No people unless the user asked for them, and never a real, recognisable person.
- **Make it the shape the area needs**, portrait, landscape, or square. A full-slide background is 1200 by 1500; Codex's portraits come out at about 1122 by 1402, which is expected and close enough. The build warns only when an image is more than 10% smaller than its area.
- **Show candidates and wait.** Offer two unless the user asks for another number. Only an image the user has chosen goes into a brief.
- **Save the chosen image** as a PNG or JPEG under `campaign-output/social/generated/<slug>/`.
- **Record it in the brief** as `{"generated": "<path>", "prompt": "<the prompt used>", "tool": "Codex ImageGen", "based_on": ["<catalog file name>"]}`, leaving `based_on` out for a conceptual image. An image the user made with AI elsewhere is accepted only if it came from Codex ImageGen, and is recorded the same way with what they tell you about the request. Never give an AI-generated image as `file`.
- **Tell the user.** When you report, name the slides that carry an AI-generated image. The package records each one with its prompt and tool. Saying so when the post is published, and the consent of anyone shown, are the user's to handle.

## Text

- **Use the user's words exactly** when they provide them. Do not rewrite approved copy to make it fit; say what does not fit and let them decide.
- **When the user asks you to write the text**, write it, say plainly that it is your draft, and keep it true: no prices, dates, availability, square footage, incentives, or claims that the user or [the project profile](../../profile.json) did not give you.
- A line break is a newline (`\n` in the brief). In a field that allows it, `*word*` sets a word or phrase in italics; elsewhere asterisks would print as typed, so leave them out.
- Stay within each field's line limit. The character figures are approximate guides, not rules; the build measures the real line count.
- Every slide needs alt text: one plain sentence describing the image, about 100 characters at most.
- The caption can run long; the preview shows how it is cut off in the feed. Hashtags are separate, each written as `#Word`.
- Use the names in the project profile: "The Rider Residences" as the official name and `theriderresidences` as the Instagram handle.

## Mixing Layouts In A Carousel

Any single-post layout (`SP-*`) and any carousel layout (`SC-*`) can go in any carousel, between that carousel's own slides and in any order with them.

| Carousel | What stays fixed | What can go after the cover |
|---|---|---|
| Editorial | Nothing | Any `SP-*`, `SC-*`, and `SG-*` layouts, from the first slide on |
| Photo gallery | `SG-01` first, `SG-08` last | `SG-02` to `SG-07`, `SP-*`, and `SC-*` layouts |
| Multi-press | `PC-01` first | `PC-02`, `SP-*`, and `SC-*` layouts |
| Press article | `AC-01` first; `AC-04`, if used, last | `AC-02`, `AC-03`, `SP-*`, and `SC-*` layouts, with no more than two of `AC-02` and `AC-03` together |

- Every carousel holds at most 10 slides.
- The press layouts (`PC-*`, `AC-*`) stay in their own carousels: they do not go in an Editorial or Photo gallery carousel, the two press carousels do not share layouts, and `SG-*` layouts do not go in a press carousel.
- The publication's logo appears only on the `AC-*` and `PC-02` slides; a single-post or carousel layout in a press carousel carries The Rider logo as usual.

## Press Carousels

Two post types present press coverage. The build recognises each from its layouts; you do not name the type.

| Post type | Use it for | Slides |
|---|---|---|
| Multi-press carousel | Coverage from several outlets | `PC-01` as the cover, which stands for the whole set, then one `PC-02` per outlet (2 to 10 slides) |
| Press article carousel | One article, read across a carousel | `AC-01` as the cover, then up to two of `AC-02` (a quote) and `AC-03` (a piece of the article, with a landscape image if there is one), then `AC-04` as an optional last slide inviting people to read more (2 to 10 slides) |

Either one also takes single-post and carousel layouts after its cover; see [Mixing Layouts In A Carousel](#mixing-layouts-in-a-carousel).

- **Quote and article text must be the publication's exact words**, given by the user or copied from the article they gave you. Never write, paraphrase, shorten, or tidy a quote (the one exception is a long subheading; see [Heading And Subheading](#heading-and-subheading)), and never invent a byline, date, outlet, or photographer credit. If something is missing, ask.
- **The publication's logo** goes bottom left on `AC-01` to `AC-04`, and bottom right on the photo of each `PC-02`, on a small white backing. Find it yourself; never ask the user for a logo file or where to find one. See [Finding The Publication's Logo](#finding-the-publications-logo).
- **In a press article carousel**, give the logo once, on the `AC-01` slide, and it appears on every `AC-*` slide. **In a multi-press carousel**, each `PC-02` is a different outlet: give each one its own outlet's logo. A logo is never carried from one `PC-02` to another.
- It is another organisation's logo, so tell the user once that permission to use it is theirs to confirm. The Rider logo is fixed.
- **Optional parts** are left out by leaving them out of the brief: the photographer `credit` and the `subheading` on `AC-01`, the `subheading` on `PC-01` and `PC-02`, the image and second paragraph (`body-2`) on `AC-03`.
- **The article's date** goes only in the `date` field of `AC-02` and `AC-03`, and the author only in `byline`. Never put a date, byline, outlet name, or credit in a `heading` or `subheading`.
- **Fixed words** cannot be changed: "SWIPE" on `PC-01`, and on `AC-04` the eyebrow "There's more to the story" and the "Link in bio" button. Only the `AC-04` subheading is yours to fill.
- The eyebrow on `PC-01` and `PC-02` is black like all other text on a white block.

### Heading And Subheading

`AC-01`, `PC-01`, and `PC-02` each have a `heading` and an optional `subheading`. When they come from an article:

1. **The article has a subheading** (the line under its headline, sometimes called a dek or standfirst): put the headline in `heading` and the article's subheading in `subheading`, both word for word.
2. **The article has no subheading and its headline is too long for `heading`:** the `subheading` continues the headline. Put as much of the headline in `heading` as fits, then the rest in `subheading`, breaking between words, ideally at a natural pause. Keep every word as written and add no dash or other punctuation; if the rest is too long for `subheading`, truncate it as below.
3. **The article has no subheading and its headline fits in `heading`:** leave `subheading` out of the brief, and the area is left off the slide. Do not fill it with the date, the byline, or words of your own.

**A subheading too long for its one line is truncated.** This applies to the article's subheading and to the end of a split headline. Keep the words from the start, cut after the last whole word that fits, and end with an ellipsis (…). Change nothing else. Tell the user which subheading was truncated.

`PC-01` is the cover for several outlets: when its heading is one article's headline, these rules apply; when the user gives their own words for it, use those.

### The Article's Photos

Every image area in a press carousel, on `AC-*` and `PC-*` slides and on any `SP-*` or `SC-*` slide mixed in, is filled with photos from the article it presents. For every article in the post, run, with its address:

`python3 -m tools.social_runtime.cli press-images --url <article address>`

It opens the article in the slide renderer's browser, saves the photos in the article and the share image the page names for itself under `campaign-output/social/article-images/`, and lists each one with its shape, size, and caption. It skips small pictures, icons, and logos.

- **Look at each photo first** and drop any that is not part of the story, such as an advert or a photo of another article. Then match the photos to the image areas by shape. Use one as `{"file": "<path>"}`.
- **In a multi-press carousel**, each `PC-02` takes a photo from its own outlet's article, and `PC-01` takes one from any of the articles.
- **`AC-03`'s image is optional.** Give it another photo from the article if there is one; otherwise leave it out.
- **The photographer `credit` on `AC-01`** is used only when the article names the photographer, for example in the photo's caption, and in its exact words.
- **When the article has no usable photo**, because it has none, the site blocked the visit, or none is the shape an area needs, tell the user which and ask whether they want an image from the catalog or one of their own. Do not choose a catalog image without asking, and do not make one with AI unless the user asks for that.
- **The article address** is found the same way as for the logo, below.
- The photos belong to the publication or its photographers, so tell the user once that permission to post them is theirs to confirm.

### Finding The Publication's Logo

For every outlet in a press post, run, with the address of that outlet's article:

`python3 -m tools.social_runtime.cli press-logo --url <article address>`

It opens the article in the slide renderer's browser, takes the outlet's logo from the page header or navigation (or, failing that, the publisher logo the page names), and saves it under `campaign-output/social/logos/`.

- **When it finds one** it prints `Logo file:` and `Look at it first:`. Open the preview image and check that it is the outlet's own logo, not a sponsor, a section badge, or another site's. If it is right, use the logo file: `"publication-logo": {"file": "<logo file>"}`. If it is wrong, leave the area empty.
- **When it finds none** it says why, for example that the site blocked the visit or only has a white logo for a dark header. Leave `publication-logo` out of that slide: the area stays empty. Tell the user in one line which outlet has no logo and why; do not ask them for one.
- **The article address.** Use the link the user gave. If they gave only the article's text and you can search the web, find the article by its headline and outlet; otherwise leave the logo out.
- **A logo the user supplies anyway** is used as given, a PNG, JPEG, or SVG file.
## Text And Logo Colour

- **Text is white (`#ffffff`) or black (`#000000`), nothing else.** The build chooses between them; the brief has no colour setting. If the user asks for any other text colour, or for a gradient on text or on a word, say that the brand allows only white or black text and do not attempt it by any route.
- **The build picks the colour from the image.** Where the image behind the text or logo is light, the text turns black, the logo is swapped for the black logo, and the dark scrim becomes a white scrim of the same strength. Where the image is dark, text on it is white. Text that is not on an image, such as a heading on a black bar or on a white block, stays as the layout has it.
- **Tell the user when it happens.** The summary lists each change under `adjustments`; report them in plain words, for example "slide 2 has a light photo, so its text and logo are black".
- **You cannot force the choice.** If the user disagrees with it, the fix is a different image or a different layout. A warning that an image is "light in some places and dark in others" means some text may be hard to read; look at the slide and suggest another image or layout if so.

## What This Skill Does Not Do

- **It makes previews, not approved releases.** Every build is a draft preview: the post types and the export sizes are still awaiting owner approval, and the runtime refuses a release build until they are approved. The slide images are full size and usable, but say they are previews.
- **It does not post.** Nothing is sent to Instagram or any other service.
- **It does not crop images or make video.** It generates or retouches an image only with Codex ImageGen, as described under AI-Generated Images.
- **It serves the in-house team only.** There is no outside-broker version yet.
- Do not edit the scaffold, the templates, the image approvals, or anything under `tools/`. If a request needs one of those changed, say so and stop.

## References

- [references/brief.md](references/brief.md): the brief format, with an example
- [examples/mixed-carousel.brief.json](examples/mixed-carousel.brief.json): a working three-slide brief
- `tools/social_runtime/README.md`: how the runtime builds, renders, and checks a post
