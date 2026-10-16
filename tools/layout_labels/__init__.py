"""Owner labels for social layouts and email blocks: purpose, content, and tone.

One vocabulary serves both sides (AUD-121). Labels are owner data: the skills read
only labels the owner has committed, and nothing here calls a model. Four `content`
values are facts about the layout, not judgments: how many photos it holds and
whether it has an outlet logo area. Code computes them from the layout data, and a
label that contradicts them is refused, so a disagreement is fixed in the data.
A layout has one or two purposes, main purpose first (AUD-123).
"""

from __future__ import annotations

import json
from pathlib import Path


VOCABULARY_VERSION = "v1"
VOCABULARY_FILE = Path(__file__).resolve().parent / f"vocabulary.{VOCABULARY_VERSION}.json"
LABEL_FIELDS = ("purpose", "content", "tone")
MAX_PURPOSES = 2


class LabelError(ValueError):
    """Raised when labels are missing, malformed, or outside the vocabulary."""


def load_vocabulary() -> dict:
    """The current vocabulary: field name to its allowed values, and which content values are computed."""
    data = json.loads(VOCABULARY_FILE.read_text(encoding="utf-8"))
    fields = data["fields"]
    return {
        "version": data["version"],
        "purpose": tuple(fields["purpose"]["values"]),
        "content": tuple(fields["content"]["values"]),
        "tone": tuple(fields["tone"]["values"]),
        "computed": tuple(fields["content"]["computed"]),
    }


def computed_content(photos: int, outlet_logo: bool) -> list[str]:
    """The content values that follow from a layout's photo count and outlet logo area."""
    values = ["no photo" if photos == 0 else "single photo" if photos == 1 else "several photos"]
    return values + (["outlet logo"] if outlet_logo else [])


def check_labels(labels: object, computed: list[str], where: str, *, required_purpose: str | None = None) -> dict:
    """Return the labels with content in vocabulary order, or refuse them with a message naming `where`.

    `purpose` is a list of one or two values, main purpose first, and keeps its order.
    `required_purpose`, when given, must be one of them.
    """
    vocabulary = load_vocabulary()
    if not isinstance(labels, dict) or set(labels) != set(LABEL_FIELDS):
        raise LabelError(f"{where}: labels must give exactly {', '.join(LABEL_FIELDS)}")
    purpose = labels["purpose"]
    if (not isinstance(purpose, list) or not 1 <= len(purpose) <= MAX_PURPOSES
            or len(set(map(str, purpose))) != len(purpose)):
        raise LabelError(f"{where}: purpose must be a list of one or two different values, main purpose first")
    if any(value not in vocabulary["purpose"] for value in purpose):
        raise LabelError(f"{where}: purpose must be one or two of: {', '.join(vocabulary['purpose'])}")
    if required_purpose and required_purpose not in purpose:
        raise LabelError(f"{where}: a block with the project logo must have purpose {required_purpose}")
    if labels["tone"] not in vocabulary["tone"]:
        raise LabelError(f"{where}: tone must be one of: {', '.join(vocabulary['tone'])}")
    content = labels["content"]
    if not isinstance(content, list) or not content or len(set(content)) != len(content):
        raise LabelError(f"{where}: content must be a list of different values")
    unknown = [value for value in content if value not in vocabulary["content"]]
    if unknown:
        raise LabelError(f"{where}: content values not in the vocabulary: {', '.join(map(str, unknown))}; "
                         f"use: {', '.join(vocabulary['content'])}")
    given = {value for value in content if value in vocabulary["computed"]}
    if given != set(computed):
        raise LabelError(f"{where}: the layout data gives content {', '.join(computed)}, but the labels list "
                         f"{', '.join(sorted(given)) or 'none of these'}; fix the labels or the layout data")
    return {
        "purpose": list(purpose),
        "content": [value for value in vocabulary["content"] if value in content],
        "tone": labels["tone"],
    }
