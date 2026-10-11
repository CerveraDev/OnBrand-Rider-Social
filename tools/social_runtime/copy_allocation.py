"""Social copy allocation: one approved owner per text surface, and repetition control.

A thin adapter over the Phase 10 contract. The normalization, similarity score, and
thresholds deliberately mirror `tools.rider_campaign_runtime.copy_allocation` without
importing it; `tests/test_social_runtime.py` asserts they stay in parity.
"""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re


ALLOCATION_VERSION = "1.0"
CHANNELS = ("caption", "on-image-text", "slide-text", "hashtags", "alt-text")
REUSE_POLICIES = ("single-use", "intentional-refrain", "required-legal", "static-brand", "required-name")
# Email policies and channels whose repetition on social is expected rather than a defect.
CROSS_MEDIUM_EXEMPT_POLICIES = {"required-legal", "static-brand", "required-name", "footer-contact", "metadata-required"}
CROSS_MEDIUM_EXEMPT_CHANNELS = {"static", "legal", "footer"}
NEAR_DUPLICATE_WARN_THRESHOLD = 0.65
NEAR_DUPLICATE_BLOCK_THRESHOLD = 0.82
MIN_SIMILARITY_WORDS = 4
UNIT_FIELDS = {"id", "text", "owner", "approval_status"}


class SocialCopyError(ValueError):
    """Raised when social copy ownership is incomplete or unapproved."""


def collect_surfaces(spec: dict, steps: list[dict]) -> dict[str, dict]:
    """Every text surface the build will emit, keyed by owner key."""
    surfaces = {"caption": {"channel": "caption", "text": spec["caption"]}}
    if spec.get("hashtags"):
        surfaces["hashtags"] = {"channel": "hashtags", "text": " ".join(spec["hashtags"])}
    for index, (slide, step) in enumerate(zip(spec["slides"], steps), start=1):
        for slot, text in slide["text"].items():
            channel = step["slots"][slot]["channel"]
            surfaces[f"{channel}::{index}::{slot}"] = {"channel": channel, "text": text}
        surfaces[f"alt-text::{index}"] = {"channel": "alt-text", "text": slide["alt_text"]}
    return surfaces


def owner_key(owner: dict) -> str:
    channel = owner.get("channel")
    if channel in ("caption", "hashtags"):
        return channel
    if channel == "alt-text":
        return f"alt-text::{owner.get('slide')}"
    return f"{channel}::{owner.get('slide')}::{owner.get('slot')}"


def validate_copy_allocation(spec: dict, steps: list[dict], *, mode: str, base_dir: Path) -> dict:
    allocation = spec["copy_allocation"]
    if allocation.get("version") != ALLOCATION_VERSION:
        raise SocialCopyError(f"copy_allocation.version must be {ALLOCATION_VERSION}")
    status = allocation.get("status")
    if status not in ("draft", "approved"):
        raise SocialCopyError("copy_allocation.status must be draft or approved")
    if status != "approved" and mode != "composition-preview":
        raise SocialCopyError(f"copy_allocation.status must be approved for a {mode} build")
    units = allocation.get("content_units")
    if not isinstance(units, list) or not units:
        raise SocialCopyError("copy_allocation.content_units must be a non-empty array")

    surfaces = collect_surfaces(spec, steps)
    owned: dict[str, str] = {}
    normalized: dict[str, str] = {}
    by_id: dict[str, dict] = {}
    for index, unit in enumerate(units):
        label = f"copy_allocation.content_units[{index}]"
        if not isinstance(unit, dict) or not UNIT_FIELDS <= set(unit) or set(unit) - UNIT_FIELDS - {"reuse_policy"}:
            raise SocialCopyError(f"{label} must give id, text, owner, approval_status and optionally reuse_policy")
        unit_id = unit["id"]
        if not isinstance(unit_id, str) or not unit_id or unit_id in by_id:
            raise SocialCopyError(f"{label} id must be a unique non-empty string")
        if not isinstance(unit["owner"], dict) or unit["owner"].get("channel") not in CHANNELS:
            raise SocialCopyError(f"{unit_id} owner.channel must be one of {', '.join(CHANNELS)}")
        if unit.get("reuse_policy", "single-use") not in REUSE_POLICIES:
            raise SocialCopyError(f"{unit_id} reuse_policy is not supported")
        if unit["approval_status"] != "approved" and not (
            mode == "composition-preview" and unit["approval_status"] == "draft"
        ):
            raise SocialCopyError(f"{unit_id} approval_status must be approved")
        key = owner_key(unit["owner"])
        surface = surfaces.get(key)
        if surface is None:
            raise SocialCopyError(f"{unit_id} owner is unknown or stale: {key}")
        if key in owned:
            raise SocialCopyError(f"{key} is owned by both {owned[key]} and {unit_id}")
        if surface["text"] != unit["text"]:
            raise SocialCopyError(f"{unit_id} text does not match its owner surface")
        owned[key] = unit_id
        by_id[unit_id] = unit
        normalized[unit_id] = normalize_text(unit["text"])
    unowned = sorted(set(surfaces) - set(owned))
    if unowned:
        raise SocialCopyError("Text surface(s) have no content unit: " + ", ".join(unowned))

    checks: list[dict] = []
    pairs: list[dict] = []
    ids = list(by_id)
    for position, left in enumerate(ids):
        for right in ids[position + 1:]:
            if "hashtags" in (by_id[left]["owner"]["channel"], by_id[right]["owner"]["channel"]):
                continue
            refrain = "single-use" not in (
                by_id[left].get("reuse_policy", "single-use"), by_id[right].get("reuse_policy", "single-use")
            )
            _compare(checks, pairs, "copy-similarity", left, normalized[left], right, normalized[right], refrain)

    cross = _cross_medium(spec, by_id, normalized, base_dir, checks)
    return {
        "version": ALLOCATION_VERSION,
        "status": status,
        "unit_count": len(by_id),
        "thresholds": {"warn": NEAR_DUPLICATE_WARN_THRESHOLD, "block": NEAR_DUPLICATE_BLOCK_THRESHOLD},
        "pairs": pairs,
        "cross_medium": cross,
        "checks": checks,
    }


def _cross_medium(spec: dict, by_id: dict, normalized: dict, base_dir: Path, checks: list[dict]) -> dict:
    cross = spec.get("cross_medium")
    if not cross:
        return {"checked": False, "surfaces": [], "pairs": []}
    exempt = {(item["social"], item["other"]) for item in cross.get("exemptions", [])}
    pairs: list[dict] = []
    surfaces = []
    for surface in cross["surfaces"]:
        path = (base_dir / surface["campaign_spec"]).resolve()
        try:
            other = json.loads(path.read_text(encoding="utf-8"))
            other_units = other["copy_allocation"]["content_units"]
            campaign = other["campaign"]["slug"]
        except (OSError, ValueError, KeyError, TypeError) as err:
            raise SocialCopyError(
                f"Cross-medium surface is unreadable or has no copy allocation: {surface['campaign_spec']}"
            ) from err
        compared = 0
        for other_unit in other_units:
            owner = other_unit.get("owner") or {}
            if (other_unit.get("reuse_policy", "single-use") in CROSS_MEDIUM_EXEMPT_POLICIES
                    or owner.get("channel") in CROSS_MEDIUM_EXEMPT_CHANNELS):
                continue
            compared += 1
            other_id = f"{surface['medium']}:{campaign}:{other_unit['id']}"
            other_text = normalize_text(other_unit["text"])
            for unit_id, unit in by_id.items():
                if unit["owner"]["channel"] == "hashtags" or unit.get("reuse_policy", "single-use") in CROSS_MEDIUM_EXEMPT_POLICIES:
                    continue
                allowed = (unit_id, other_unit["id"]) in exempt
                _compare(checks, pairs, "cross-medium-repetition", unit_id, normalized[unit_id],
                         other_id, other_text, allowed)
        surfaces.append({"medium": surface["medium"], "campaign": campaign, "units_compared": compared})
    return {"checked": True, "surfaces": surfaces, "pairs": pairs}


def _compare(checks, pairs, name, left_id, left, right_id, right, exempt) -> None:
    if not left or not right:
        return
    if left == right:
        score = 1.0
    elif min(len(left.split()), len(right.split())) < MIN_SIMILARITY_WORDS:
        return
    else:
        score = similarity_score(left, right)
    if score < NEAR_DUPLICATE_WARN_THRESHOLD:
        return
    blocking = score >= NEAR_DUPLICATE_BLOCK_THRESHOLD and not exempt
    pairs.append({"left": left_id, "right": right_id, "score": round(score, 3), "blocking": blocking, "exempt": bool(exempt)})
    checks.append({
        "name": f"{name}:{left_id}:{right_id}",
        "passed": not blocking,
        "message": f"similarity {score:.3f}; warning >= {NEAR_DUPLICATE_WARN_THRESHOLD}, blocking >= {NEAR_DUPLICATE_BLOCK_THRESHOLD}",
    })


def normalize_text(value: str) -> str:
    text = _html_to_text(value)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("—", " ").replace("–", " ")
    text = re.sub(r"https?://\S+", " ", text.lower())
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity_score(left: str, right: str) -> float:
    left_tokens = left.split()
    right_tokens = right.split()
    token_score = _jaccard(set(left_tokens), set(right_tokens))
    bigram_score = _jaccard(_ngrams(left_tokens, 2), _ngrams(right_tokens, 2))
    char_score = _jaccard(_char_ngrams(left, 4), _char_ngrams(right, 4))
    return max(token_score, (bigram_score + char_score) / 2)


def _html_to_text(value: str) -> str:
    parser = _TextParser()
    parser.feed(value.replace("<br>", " <br> ").replace("<br/>", " <br/> ").replace("<br />", " <br /> "))
    parser.close()
    return " ".join(parser.parts)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data)


def _jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _ngrams(tokens: list[str], size: int) -> set[tuple[str, ...]]:
    if len(tokens) < size:
        return set()
    return {tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def _char_ngrams(text: str, size: int) -> set[str]:
    compact = text.replace(" ", "")
    if len(compact) < size:
        return set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}
