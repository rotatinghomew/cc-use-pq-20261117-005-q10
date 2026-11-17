from __future__ import annotations


def build_manifest(batches: list[dict], stories: list[dict]) -> dict:
    by_tradition = {}
    for story in stories:
        by_tradition[story["tradition"]] = by_tradition.get(story["tradition"], 0) + 1
    return {
        "batch_count": len(batches),
        "story_revision_count": len(stories),
        "tradition_counts": dict(sorted(by_tradition.items())),
        "batches": sorted(batches, key=lambda item: item["batch_id"]),
        "story_revisions": [
            {"story_id": item["story_id"], "revision": item["revision"],
             "source_reference": item["source"]["reference"], "source_kind": item["source"]["kind"]}
            for item in sorted(stories, key=lambda value: (value["story_id"], value["revision"]))
        ],
    }
