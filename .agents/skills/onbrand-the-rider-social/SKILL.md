---
name: onbrand-the-rider-social
description: Explicitly invoked OnBrand the-rider social workflow.
---

# onbrand-the-rider-social

Run only after a HUMAN explicitly invokes $onbrand-the-rider-social. Ordinary topic matches are not invocation.

Read [the canonical workflow](../../../projects/the-rider/skills/onbrand-the-rider-social/SKILL.md); resolve its references from its own folder. Do not copy project rules or approve inputs on behalf of the user.

The core repository is at `.` relative to this workspace. Run commands from that core root, using Python 3.10+ with the standard library.

For a post brief, use the social runtime directly:

```bash
python3 -m tools.social_runtime.cli post --brief <brief.json>
```

`gallery --project the-rider` opens the layout gallery and `images --project the-rider` opens the image catalog. Do not invoke another skill automatically. If shell execution is unavailable, provide the same command for the human; never bypass QA or reconstruct a package manually.
