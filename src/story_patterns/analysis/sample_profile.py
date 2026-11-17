from __future__ import annotations

from collections import Counter
from statistics import median


def _sorted_counts(values) -> dict:
    counts = Counter(values)
    return {str(key): counts[key] for key in sorted(counts)}


def build_sample_profile(stories: list[dict]) -> dict:
    sibling_counts = [len(story["characters"]) for story in stories]
    event_counts = [len(story["events"]) for story in stories]
    events_by_order = Counter()
    source_by_tradition = {}
    for story in stories:
        roster = {item["character_id"]: item["sibling_order"] for item in story["characters"]}
        source_counts = source_by_tradition.setdefault(story["tradition"], Counter())
        source_counts[story["source"]["kind"]] += 1
        for event in story["events"]:
            events_by_order[roster[event["actor_id"]]] += 1
    return {
        "story_revisions": len(stories),
        "traditions": _sorted_counts(story["tradition"] for story in stories),
        "source_kinds": _sorted_counts(story["source"]["kind"] for story in stories),
        "sibling_roster_sizes": _sorted_counts(sibling_counts),
        "event_counts": _sorted_counts(event_counts),
        "events_by_sibling_order": _sorted_counts(events_by_order.elements()),
        "sources_by_tradition": {
            tradition: {kind: counts[kind] for kind in sorted(counts)}
            for tradition, counts in sorted(source_by_tradition.items())
        },
        "total_events": sum(event_counts),
        "total_characters": sum(sibling_counts),
        "mean_events_per_story": round(sum(event_counts) / len(event_counts), 3) if event_counts else None,
        "mean_siblings_per_story": round(sum(sibling_counts) / len(sibling_counts), 3) if sibling_counts else None,
        "median_events_per_story": median(event_counts) if event_counts else None,
        "median_siblings_per_story": median(sibling_counts) if sibling_counts else None,
        "structure": {
            "stories_with_exactly_three_siblings": sum(count == 3 for count in sibling_counts),
            "min_siblings": min(sibling_counts) if sibling_counts else None,
            "max_siblings": max(sibling_counts) if sibling_counts else None,
            "min_events": min(event_counts) if event_counts else None,
            "max_events": max(event_counts) if event_counts else None,
        },
        "warning": "Describes the imported sample only; it does not estimate the prevalence of a story pattern.",
    }
