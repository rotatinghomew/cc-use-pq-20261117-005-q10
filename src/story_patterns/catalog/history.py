from __future__ import annotations

from collections import defaultdict


def revision_lineage(stories: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for story in stories:
        grouped[story["story_id"]].append(story)
    result = []
    for story_id, versions in sorted(grouped.items()):
        versions.sort(key=lambda item: item["revision"])
        revision_numbers = [item["revision"] for item in versions]
        expected = list(range(1, revision_numbers[-1] + 1))
        missing = sorted(set(expected) - set(revision_numbers))
        result.append({
            "story_id": story_id,
            "revision_count": len(versions),
            "latest_revision": revision_numbers[-1],
            "missing_revision_numbers": missing,
            "titles_by_revision": [{"revision": item["revision"], "title": item["title"]} for item in versions],
            "traditions": sorted({item["tradition"] for item in versions}),
        })
    return result


def lineage_warnings(lineage: list[dict]) -> list[dict]:
    return [{"story_id": item["story_id"], "missing_revision_numbers": item["missing_revision_numbers"]}
            for item in lineage if item["missing_revision_numbers"]]
