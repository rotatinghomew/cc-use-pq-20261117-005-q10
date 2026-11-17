from __future__ import annotations

import hashlib
import json
from typing import Any

from story_patterns.errors import ValidationError

PATTERNS = {"parallel", "harm"}
OUTCOMES = {"wins", "loses", "mixed", "unknown"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > limit:
        raise ValidationError(f"{field} exceeds {limit} characters")
    return value


def normalize_story(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("each story must be an object")
    story_id = _text(raw.get("story_id"), "story_id", 100)
    title = _text(raw.get("title"), "title", 240)
    tradition = _text(raw.get("tradition"), "tradition", 120)
    revision = raw.get("revision")
    if type(revision) is not int or revision < 1:
        raise ValidationError("revision must be a positive integer")
    source = raw.get("source")
    if not isinstance(source, dict):
        raise ValidationError("source must be an object")
    source_ref = _text(source.get("reference"), "source.reference", 300)
    source_kind = _text(source.get("kind"), "source.kind", 40)
    if source_kind not in {"book", "oral_record", "local_synthetic"}:
        raise ValidationError("source.kind must be book, oral_record, or local_synthetic")
    characters = raw.get("characters")
    events = raw.get("events")
    if not isinstance(characters, list) or not characters:
        raise ValidationError("characters must be a non-empty list")
    if not isinstance(events, list) or not events:
        raise ValidationError("events must be a non-empty list")
    normalized_characters = []
    character_ids: set[str] = set()
    orders: set[int] = set()
    for item in characters:
        if not isinstance(item, dict):
            raise ValidationError("each character must be an object")
        character_id = _text(item.get("character_id"), "character.character_id", 100)
        order = item.get("sibling_order")
        if type(order) is not int or order < 1:
            raise ValidationError("character.sibling_order must be a positive integer")
        if character_id in character_ids or order in orders:
            raise ValidationError("character identifiers and sibling orders must be unique")
        character_ids.add(character_id)
        orders.add(order)
        normalized_characters.append({
            "character_id": character_id,
            "name": _text(item.get("name"), "character.name", 120),
            "sibling_order": order,
        })
    normalized_events = []
    event_ids: set[str] = set()
    sequences: set[int] = set()
    for item in events:
        if not isinstance(item, dict):
            raise ValidationError("each event must be an object")
        event_id = _text(item.get("event_id"), "event.event_id", 100)
        sequence = item.get("sequence")
        if type(sequence) is not int or sequence < 1:
            raise ValidationError("event.sequence must be a positive integer")
        if event_id in event_ids or sequence in sequences:
            raise ValidationError("event identifiers and sequences must be unique")
        actor_id = _text(item.get("actor_id"), "event.actor_id", 100)
        if actor_id not in character_ids:
            raise ValidationError(f"event {event_id} references an unknown actor")
        event_ids.add(event_id)
        sequences.add(sequence)
        normalized_events.append({
            "event_id": event_id,
            "sequence": sequence,
            "actor_id": actor_id,
            "action": _text(item.get("action"), "event.action", 300),
            "consequence": _text(item.get("consequence"), "event.consequence", 300),
            "evidence": _text(item.get("evidence"), "event.evidence", 1000),
        })
    if sorted(sequences) != list(range(1, len(events) + 1)):
        raise ValidationError("event sequences must be contiguous and start at one")
    return {
        "story_id": story_id,
        "revision": revision,
        "title": title,
        "tradition": tradition,
        "source": {"reference": source_ref, "kind": source_kind},
        "characters": sorted(normalized_characters, key=lambda item: item["sibling_order"]),
        "events": sorted(normalized_events, key=lambda item: item["sequence"]),
    }


def normalize_batch(raw: Any) -> tuple[str, list[dict[str, Any]], str]:
    if not isinstance(raw, dict):
        raise ValidationError("batch must be an object")
    batch_id = _text(raw.get("batch_id"), "batch_id", 120)
    stories = raw.get("stories")
    if not isinstance(stories, list) or not stories:
        raise ValidationError("stories must be a non-empty list")
    normalized = [normalize_story(story) for story in stories]
    identities = [(story["story_id"], story["revision"]) for story in normalized]
    if len(identities) != len(set(identities)):
        raise ValidationError("a batch cannot repeat a story revision")
    normalized.sort(key=lambda story: (story["story_id"], story["revision"]))
    payload = {"batch_id": batch_id, "stories": normalized}
    return batch_id, normalized, digest_json(payload)
