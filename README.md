<p align="center">
  <img src="assets/banner.jpg" alt="OnBrand Design by Cervera" width="100%">
</p>

# The Rider Social: Quick Start

Build Instagram posts and carousels for The Rider Residences by describing them to an AI assistant. The assistant fills The Rider's approved layouts with images and text, then opens a phone-style preview of the finished post.

This guide covers everything needed to go from nothing installed to a first post.

## What You Need

| Requirement | Notes |
|---|---|
| A Mac or Windows computer | Linux also works. |
| An AI coding assistant | [Claude Code](https://claude.com/claude-code) or [OpenAI Codex](https://openai.com/codex), signed in with **your own** account. |
| [Python](https://www.python.org/downloads/) 3.10 or newer | Already present on most Macs. Check with `python3 --version`. |
| [Node.js](https://nodejs.org) (LTS version) | Renders the slides. Check with `node --version`. |
| [Git](https://git-scm.com/downloads) | Downloads the skill and its updates. |
| About 500 MB of free disk space | Mostly the browser used to render slides. |
| An internet connection | For setup, for updates, and to load catalog images. |

### Who Pays For What

Nothing in this skill is billed to The Rider, Cervera, or the author. The conversation with the assistant runs on your own Claude or Codex account and counts against your own plan. Building a post uses no paid service at all: the slides are drawn on your computer.

## Install

1. Open a terminal and download the skill:

   ```bash
   git clone https://github.com/CerveraDev/OnBrand-Rider-Social.git
   cd OnBrand-Rider-Social
   ```

2. Start your assistant **in that folder**:

   - Claude Code: run `claude`. In the Claude desktop app, open the Code tab and choose this folder.
   - Codex: run `codex`, or open this folder in the Codex app.

3. Start the skill and ask it to set up:

   - Claude Code: `/onbrand-the-rider-social set me up`
   - Codex: `$onbrand-the-rider-social set me up`

Setup takes a few minutes the first time because it downloads a browser of about 150 MB. It finishes with `Ready.` If it says Node.js is missing, install it from [nodejs.org](https://nodejs.org) and ask again.

To run setup yourself instead: `python3 -m tools.social_runtime.cli setup --project the-rider`

## The One Command

The skill starts only when you type its name. It never starts on its own.

| Assistant | Type this |
|---|---|
| Claude Code | `/onbrand-the-rider-social` |
| Codex | `$onbrand-the-rider-social` |

After the name, say what you want in plain words. The sections below show what to ask for.

## The Two Galleries

Both open in your web browser by themselves.

### Layout Gallery

Ask: **"Show me the layouts."**

Every approved layout with a picture, what it holds, and how much text fits. Filter by type: single post, carousel slide, photo gallery, or press carousel. Tick the layouts you want in order, and the bar at the bottom checks that the sequence is allowed and gives you a line to paste back to the assistant, such as:

> Make an Editorial Carousel using layouts SP-04, SC-02, SG-03 in that order.

### Image Catalog

Ask: **"Show me the images."**

Every official Rider image approved for social, with filters by subject and shape. The first opening takes about a minute while previews are made. Tick images and paste the resulting line back to the assistant.

## Making A Post

Tell the assistant what you want. For example:

- "Make a single post with layout SP-09 using the rooftop pool rendering. Heading: Above Wynwood."
- "Make an amenities carousel, four slides. Pick the layouts and write the text."
- "Make a carousel with SP-04, SC-02 and SG-03 using the photos in my Downloads/shoot folder."

The assistant asks for anything missing, builds the post, and opens the **feed preview**: the post as it would look on a phone, with swipe, caption, hashtags, alt text, and a dark-mode switch. The full-size slide images (1200 × 1500 pixels, 4:5) are saved in a folder the assistant names.

To change something, just say so: "shorten the heading", "swap slide 2 for the lobby image".

### Post Types

| Post type | What it is | Layouts |
|---|---|---|
| Single post | One image | `SP-01` to `SP-19` |
| Editorial carousel | Up to ten slides | Optionally one `SP` layout first, then `SC` and `SG` layouts |
| Photo gallery | A carousel of photo grids | `SG-01` to `SG-08` |
| Multi-press carousel | Coverage from several outlets | `PC-01` as the cover, then one `PC-02` per outlet |
| Press article carousel | One article read across slides | `AC-01` cover, optional `AC-02` quote and `AC-03` excerpt, optional `AC-04` closing slide |

You do not need to name the post type. The skill recognises it from the layouts.

### Your Own Images

Give the assistant a file or folder path. Files must be PNG or JPEG, and each image area needs a particular shape (portrait, landscape, or square); the assistant tells you when a shape does not fit. Your own images are recorded as supplied by you: permission to post them, and the consent of anyone shown, are yours to confirm.

### Press Carousels

- Quotes and article text must be the publication's exact words. The assistant will not write or tidy a quote.
- Give the publication's logo file once and it appears bottom left on every slide of the article carousel. Permission to use another organisation's logo is yours to confirm.
- Some words are fixed and cannot be changed: "SWIPE", "There's more to the story", and the "Link in bio" button.

## Rules The Skill Enforces

- **Text is white or black only.** No other colours and no gradients on text. The skill picks white or black by itself from how light the image is, swaps the logo to match, and tells you when it has done so.
- **Text has to fit.** Each field has a line limit. If your text runs over, the build stops and names the field.
- **Layouts are fixed.** Fonts, spacing, logo position, and the layouts themselves cannot be changed from a conversation.
- **Only approved catalog images**, images you supply yourself, or AI-generated images on the layouts that take them.

## AI-Generated And AI-Edited Images

You can ask the assistant to create or change an image with AI, for example to extend a square photo into a taller one.

- **Only two image tools are used.** Codex ImageGen (built into Codex, and the one proven on this project) or OpenAI GPT Image through your own OpenAI API key. The assistant will not use Canva or any other image app or connector, even if one is connected; without an allowed tool it will tell you and offer a catalog image instead. The tool runs on your own account.
- **Not every layout takes one.** All layouts do except `SC-04` to `SC-07` and `SG-02` to `SG-07`. The layout gallery says which.
- **Real Rider places start from an official image.** The assistant bases the picture on a catalog image and keeps the architecture unchanged. Anything else is a concept and is labelled as one.
- **You choose.** The assistant shows candidates and uses only the one you pick.
- **It is recorded.** The package lists each AI-generated image with the prompt and tool that made it, and the build reminds you.
- **Disclosure is yours.** Saying that an image is AI-made when you post it, and having the consent of any real person shown, are your responsibility.

## Getting Updates

Ask: **"Update the skill."**

This downloads the latest layouts, image list, and image approvals, which always arrive as a matching set. Do this before an important post, or whenever you are told new layouts or images are available.

To run it yourself: `python3 -m tools.social_runtime.cli update --project the-rider`

Do not edit the files in this folder. An update can fail if they were changed, and edited layouts are no longer the approved ones.

## What This Skill Does Not Do

- **It does not post.** Nothing is sent to Instagram. You upload the slide images yourself.
- **It makes previews.** The post types and export sizes are still awaiting final owner approval, so every build is labelled a preview. The slide images are full size.
- **No reels, stories, or video.**
- **No cropping or retouching.** Catalog images that need a crop are centred automatically.
- **Email is not included.** This package covers social posts only.

## If Something Goes Wrong

| What you see | What to do |
|---|---|
| "The slide renderer is not installed" | Ask the assistant to set up, or run the setup command above. |
| "Node.js is not installed" | Install the LTS version from [nodejs.org](https://nodejs.org), then set up again. |
| "The image catalog is not usable" | Ask the assistant to update the skill. |
| "text:heading: 3 of 2 lines" | That text is too long for its layout. Shorten it or pick a layout with more room. |
| An image is refused for its shape | Use an image of the shape the layout asks for, or a different layout. |
| The skill does not start | Make sure the assistant was started inside the `OnBrand-Rider-Social` folder and that you typed the full command name. |
| The update fails | Files in the folder were changed. Download a fresh copy into a new folder. |

## Command Reference

You rarely need these; the assistant runs them for you. All run from the `OnBrand-Rider-Social` folder.

| Purpose | Command |
|---|---|
| Set up or re-check this computer | `python3 -m tools.social_runtime.cli setup --project the-rider` |
| Get the latest version | `python3 -m tools.social_runtime.cli update --project the-rider` |
| Open the layout gallery | `python3 -m tools.social_runtime.cli gallery --project the-rider` |
| Open the image catalog | `python3 -m tools.social_runtime.cli images --project the-rider` |
| List layouts and their limits as text | `python3 -m tools.social_runtime.cli layouts --project the-rider` |
| Build a post from a brief file | `python3 -m tools.social_runtime.cli post --brief <file>` |

---

The Rider Social is part of OnBrand Design by Felix Mendoza for Cervera Real Estate, Inc., licensed under Apache-2.0. See `LICENSE` and `NOTICE`.
