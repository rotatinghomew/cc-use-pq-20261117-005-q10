from __future__ import annotations

from story_patterns.catalog.validate import _text, normalize_story
from story_patterns.errors import ValidationError


def normalize_decision(raw: dict, story: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("decision must be an object")
    decision_id = _text(raw.get("decision_id"), "decision_id", 120)
    annotator = _text(raw.get("annotator"), "annotator", 120)
    sequence = raw.get("sequence")
    if type(sequence) is not int or sequence < 1:
        raise ValidationError("sequence must be a positive integer")
    pattern = raw.get("pattern")
    outcome = raw.get("youngest_outcome")
    if pattern not in {"parallel", "harm", "unclear"}:
        raise ValidationError("pattern must be parallel, harm, or unclear")
    if outcome not in {"wins", "loses", "mixed", "unknown"}:
        raise ValidationError("youngest_outcome is not supported")
    evidence_ids = raw.get("evidence_event_ids")
    known = {event["event_id"] for event in story["events"]}
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise ValidationError("at least one evidence event is required")
    if any(not isinstance(item, str) or item not in known for item in evidence_ids):
        raise ValidationError("evidence_event_ids must refer to events in this revision")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValidationError("evidence_event_ids cannot repeat")
    note = raw.get("note", "")
    if not isinstance(note, str) or len(note) > 1000:
        raise ValidationError("note must be text of at most 1000 characters")
    return {
        "decision_id": decision_id,
        "story_id": story["story_id"],
        "story_revision": story["revision"],
        "annotator": annotator,
        "sequence": sequence,
        "pattern": pattern,
        "youngest_outcome": outcome,
        "evidence_event_ids": sorted(evidence_ids),
        "note": note.strip(),
    }
