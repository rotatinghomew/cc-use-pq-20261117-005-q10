from __future__ import annotations

from collections import defaultdict

from story_patterns.analysis.report import _consensus


def build_review_queue(stories: list[dict], decisions: dict, minimum: int, adjudications: dict | None = None) -> list[dict]:
    queue = []
    for story in sorted(stories, key=lambda item: (item["tradition"], item["story_id"], item["revision"])):
        identity = (story["story_id"], story["revision"])
        votes = decisions.get(identity, [])
        adjudication = (adjudications or {}).get(identity)
        pattern, pattern_status = _consensus([item["pattern"] for item in votes], minimum)
        outcome, outcome_status = _consensus([item["youngest_outcome"] for item in votes], minimum)
        cited = {event_id for vote in votes for event_id in vote["evidence_event_ids"]}
        missing_evidence = [event["event_id"] for event in story["events"] if event["event_id"] not in cited]
        if adjudication:
            status = "adjudicated"
        elif not votes:
            status = "unreviewed"
        elif pattern_status == "split" or outcome_status == "split":
            status = "disputed"
        elif pattern_status != "agreed" or outcome_status != "agreed":
            status = "needs_more_reviews"
        else:
            status = "ready"
        queue.append({
            "story_id": story["story_id"], "revision": story["revision"], "title": story["title"],
            "tradition": story["tradition"], "status": status, "reviewer_count": len(votes),
            "pattern": pattern, "outcome": outcome, "missing_evidence_event_ids": missing_evidence,
            "reviewer_names": sorted(item["annotator"] for item in votes),
            "adjudication_id": adjudication["adjudication_id"] if adjudication else None,
            "final_pattern": adjudication["pattern"] if adjudication else pattern,
            "final_outcome": adjudication["youngest_outcome"] if adjudication else outcome,
        })
    return queue


def queue_totals(rows: list[dict]) -> dict:
    totals = defaultdict(int)
    for row in rows:
        totals[row["status"]] += 1
    return {key: totals.get(key, 0) for key in ("unreviewed", "needs_more_reviews", "disputed", "ready", "adjudicated")}
