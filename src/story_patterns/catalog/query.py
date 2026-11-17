from __future__ import annotations

from story_patterns.errors import ValidationError


def search_stories(stories: list[dict], text: str | None = None, tradition: str | None = None,
                   source_kind: str | None = None, sibling_order: int | None = None,
                   revision_policy: str = "all") -> list[dict]:
    if text is not None and (not isinstance(text, str) or not text.strip()):
        raise ValidationError("text search must be non-empty when provided")
    if tradition is not None and (not isinstance(tradition, str) or not tradition.strip()):
        raise ValidationError("tradition filter must be non-empty when provided")
    if source_kind is not None and source_kind not in {"book", "oral_record", "local_synthetic"}:
        raise ValidationError("source_kind is not supported")
    if sibling_order is not None and (type(sibling_order) is not int or sibling_order < 1):
        raise ValidationError("sibling_order must be a positive integer")
    if revision_policy not in {"all", "latest"}:
        raise ValidationError("revision_policy must be all or latest")
    candidates = stories
    if revision_policy == "latest":
        latest = {}
        for story in candidates:
            current = latest.get(story["story_id"])
            if current is None or story["revision"] > current["revision"]:
                latest[story["story_id"]] = story
        candidates = list(latest.values())
    needle = text.casefold().strip() if text else None
    result = []
    for story in candidates:
        if tradition is not None and story["tradition"] != tradition:
            continue
        if source_kind is not None and story["source"]["kind"] != source_kind:
            continue
        characters = story["characters"]
        if sibling_order is not None and all(item["sibling_order"] != sibling_order for item in characters):
            continue
        searchable = [story["title"], story["tradition"], story["source"]["reference"]]
        searchable.extend(item["name"] for item in characters)
        searchable.extend(event[field] for event in story["events"] for field in ("action", "consequence", "evidence"))
        if needle and not any(needle in value.casefold() for value in searchable):
            continue
        matching_events = [event["event_id"] for event in story["events"]
                           if not needle or any(needle in event[field].casefold()
                                                for field in ("action", "consequence", "evidence"))]
        result.append({"story_id": story["story_id"], "revision": story["revision"],
                       "title": story["title"], "tradition": story["tradition"],
                       "source": story["source"], "matching_event_ids": matching_events})
    return sorted(result, key=lambda item: (item["tradition"], item["story_id"], item["revision"]))
