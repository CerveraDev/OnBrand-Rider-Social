# Post Brief

A brief is a small JSON file that says which layouts to use, in order, and what goes in each. Save it as `campaign-output/social/briefs/<slug>.json` and run:

```bash
python3 -m tools.social_runtime.cli post --brief campaign-output/social/briefs/<slug>.json
```

## Fields

| Field | Required | What it is |
|---|---|---|
| `project` | Yes | Always `the-rider` |
| `slug` | Yes | A short name for this post in lowercase words joined by hyphens, such as `rooftop-opening-carousel`. It names the output folder; reusing a slug replaces that post. |
| `title` | No | A human-readable name shown on the preview page |
| `slides` | Yes | One entry per slide, in order. A single post has one. |
| `caption` | Yes | The caption text |
| `hashtags` | No | A list such as `["#TheRiderResidences", "#Wynwood"]`, without repeats |
| `post_type` | No | Force `PST-01`, `CAR-01`, `GAL-01`, `MPC-01` (multi-press), or `PAC-01` (press article). Leave it out; the post type is worked out from the layouts. |

Each slide has these four fields, plus `hide` where a layout allows it:

| Field | What it is |
|---|---|
| `layout` | The layout ID, such as `SC-02` |
| `images` | One entry per image area of that layout, keyed by the area's name (`background`, `image-1`, ...). Each is `{"catalog": "<exact file name>"}` for an official image, `{"file": "<path>"}` for the user's own, or a `generated` entry for an AI-generated one (see below). A path may be absolute, start with `~`, or be relative to the brief. |
| `text` | One entry per text field of that layout, keyed by the field's name (`heading`, `subheading`, `copy`, `footer-line`). Use `\n` for a line break and `*word*` for italics where the layout allows it. |
| `alt_text` | One sentence describing the slide's image |
| `hide` | Optional. A list of fixed parts to leave off, from the layout's "can hide" list. No layout has one today. |

Run `python3 -m tools.social_runtime.cli layouts --project the-rider` to see every layout's image areas, text fields, and limits. Every image area and every text field of a layout must be filled unless the listing marks it optional; an optional one is left off the slide when you leave it out. Text listed as fixed cannot be set; a name the layout does not have is refused.

## Example

[examples/mixed-carousel.brief.json](../examples/mixed-carousel.brief.json) is a three-slide carousel: a single-post layout as the opener, a two-image carousel layout whose landscape catalog images are placed automatically, and a full-image carousel layout.

```json
{
  "project": "the-rider",
  "slug": "sauna-post",
  "slides": [
    {
      "layout": "SP-05",
      "images": {"background": {"catalog": "the-rider-recovery-sauna.jpg"}},
      "text": {"heading": "THE RECOVERY\nSAUNA", "subheading": "Warm wood, low light"},
      "alt_text": "Woman resting on a bench in a wood-lined sauna"
    }
  ],
  "caption": "Nowhere to be. The Recovery Sauna at The Rider Residences.",
  "hashtags": ["#TheRiderResidences"]
}
```

A slide using the user's own photo differs only in its image entry:

```json
"images": {"background": {"file": "~/Pictures/top-off/crowd-toast.jpg"}}
```

A slide using an AI-generated image the user has chosen, on a layout that takes one (`layouts` says "AI-generated image: yes"):

```json
"images": {"background": {
  "generated": "campaign-output/social/generated/sauna-post/candidate-2.png",
  "prompt": "Extend the approved sauna photo upward to a 4:5 portrait; keep the room unchanged",
  "tool": "Codex ImageGen",
  "based_on": ["the-rider-recovery-sauna.jpg"]
}}
```

`prompt` and `tool` are required. `tool` is `Codex ImageGen`; the build refuses any other. The `image` command prints this entry for you. `based_on` lists the catalog images it started from, by exact file name; leave it out for a conceptual image. A relative path is read from the folder the brief is in.

A press article slide with the publication's logo and no photographer credit:

```json
{
  "layout": "AC-01",
  "images": {"image-1": {"file": "campaign-output/social/article-images/therealdeal.com-story/image-01.jpg"}, "publication-logo": {"file": "campaign-output/social/logos/therealdeal.com.svg"}},
  "text": {"byline": "By Author Name", "heading": "THE ARTICLE'S\nHEADLINE", "subheading": "Its subheading"},
  "alt_text": "Tower exterior at dusk"
}
```

A layout with no image areas filled takes `"images": {}`. In a press article carousel, a `publication-logo` given on one `AC-*` slide is used on every `AC-*` slide, so give it once. In a multi-press carousel, give each `PC-02` its own outlet's logo. The logo file, or the outlet's typeset name when it has no usable logo, comes from the `press-logo` command and may be a PNG, JPEG, or SVG. The photos come from the `press-images` command. `subheading` holds the article's subheading or, when it has none, the rest of a long headline, and is left out when there is neither; it is never the date or byline, which go in `date` on `AC-02` and `AC-03` and in `byline`.

## What The Command Works Out

- The post type, from the layouts and their order.
- A centred placement for any catalog image that is the wrong shape for its area or is approved only as a crop source. It is recorded as a planned crop and reported as a warning.
- The draft copy record the runtime requires for every piece of text. A line repeated word for word across slides, such as an event date in a gallery footer, is marked as a deliberate refrain.

## Result

The command prints `passed`, `package_dir`, `slides`, `simulator`, `zip_path`, `warnings`, and `failed_checks`.

| Exit code | Meaning | What to do |
|---|---|---|
| 0 | Built, rendered, and every check passed | Report to the user |
| 1 | Built, but a check failed | Read `failed_checks`, fix the brief, run again |
| 2 | Refused before building | Read the message, fix the brief, run again |

Warnings that always appear for now, and what they mean:

- "Template ... is a draft pending owner approval" and "Format ... values are provisional and unverified": the post types and export sizes have not had final owner sign-off, so every build is a preview.
- "Copy allocation is a draft pending approval": the text has not been through an approval step.
- "Crop ... is planned": that image was placed centred automatically rather than cropped by hand.
- "Directly used assets are matched by manifest orientation only": catalog images were matched by shape; their exact pixel size was not checked.
- "No cross_medium surface was declared": the text was not compared against any email campaign.
