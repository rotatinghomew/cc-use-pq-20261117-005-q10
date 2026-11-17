from __future__ import annotations

from story_patterns.catalog.validate import canonical_json, digest_json, _text
from story_patterns.errors import ConflictError, NotFoundError, ValidationError


def normalize_adjudication(raw: dict, story: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("adjudication must be an object")
    record_id = _text(raw.get("adjudication_id"), "adjudication_id", 120)
    moderator = _text(raw.get("moderator"), "moderator", 120)
    sequence = raw.get("sequence")
    if type(sequence) is not int or sequence < 1:
        raise ValidationError("sequence must be a positive integer")
    pattern = raw.get("pattern")
    outcome = raw.get("youngest_outcome")
    if pattern not in {"parallel", "harm"}:
        raise ValidationError("an adjudicated pattern must be parallel or harm")
    if outcome not in {"wins", "loses", "mixed", "unknown"}:
        raise ValidationError("youngest_outcome is not supported")
    evidence = raw.get("evidence_event_ids")
    known = {event["event_id"] for event in story["events"]}
    if not isinstance(evidence, list) or not evidence:
        raise ValidationError("adjudication must cite at least one event")
    if any(not isinstance(item, str) or item not in known for item in evidence):
        raise ValidationError("adjudication cites an event outside this story revision")
    if len(evidence) != len(set(evidence)):
        raise ValidationError("adjudication evidence cannot repeat")
    rationale = _text(raw.get("rationale"), "rationale", 1500)
    return {
        "adjudication_id": record_id,
        "story_id": story["story_id"], "story_revision": story["revision"],
        "moderator": moderator, "sequence": sequence, "pattern": pattern,
        "youngest_outcome": outcome, "evidence_event_ids": sorted(evidence),
        "rationale": rationale,
    }


class AdjudicationService:
    def __init__(self, store):
        self.store = store

    def record(self, raw: dict) -> dict:
        story_id = raw.get("story_id") if isinstance(raw, dict) else None
        revision = raw.get("story_revision") if isinstance(raw, dict) else None
        story = self.store.story_document(story_id, revision)
        if story is None:
            raise NotFoundError(f"story revision {story_id!r}/{revision!r} was not found")
        record = normalize_adjudication(raw, story)
        digest = digest_json(record)
        with self.store.transaction() as connection:
            previous = connection.execute(
                "SELECT digest FROM adjudications WHERE adjudication_id=?", (record["adjudication_id"],)
            ).fetchone()
            if previous:
                if previous["digest"] != digest:
                    raise ConflictError("adjudication identifier already refers to different content")
                return {"adjudication_id": record["adjudication_id"], "status": "already_recorded"}
            occupied = connection.execute(
                "SELECT adjudication_id FROM adjudications WHERE story_id=? AND story_revision=? AND sequence=?",
                (story_id, revision, record["sequence"]),
            ).fetchone()
            if occupied:
                raise ConflictError("adjudication sequence is already occupied for this story revision")
            connection.execute(
                "INSERT INTO adjudications(adjudication_id, story_id, story_revision, moderator, sequence, pattern, "
                "youngest_outcome, evidence_event_ids, rationale, digest) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (record["adjudication_id"], story_id, revision, record["moderator"], record["sequence"],
                 record["pattern"], record["youngest_outcome"], canonical_json(record["evidence_event_ids"]),
                 record["rationale"], digest),
            )
        return {"adjudication_id": record["adjudication_id"], "status": "recorded"}
