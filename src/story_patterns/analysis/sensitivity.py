from __future__ import annotations

def leave_one_reader_out(stories: list[dict], decisions: dict, minimum: int) -> dict:
    from story_patterns.analysis.report import _consensus

    examined = []
    fragile_pattern = 0
    fragile_outcome = 0
    for story in stories:
        identity = (story["story_id"], story["revision"])
        votes = decisions.get(identity, [])
        baseline_pattern, baseline_pattern_status = _consensus([vote["pattern"] for vote in votes], minimum)
        baseline_outcome, baseline_outcome_status = _consensus(
            [vote["youngest_outcome"] for vote in votes], minimum
        )
        removals = []
        for omitted in votes:
            remaining = [vote for vote in votes if vote["decision_id"] != omitted["decision_id"]]
            pattern, pattern_status = _consensus([vote["pattern"] for vote in remaining], minimum)
            outcome, outcome_status = _consensus([vote["youngest_outcome"] for vote in remaining], minimum)
            pattern_changed = (pattern, pattern_status) != (baseline_pattern, baseline_pattern_status)
            outcome_changed = (outcome, outcome_status) != (baseline_outcome, baseline_outcome_status)
            fragile_pattern += pattern_changed
            fragile_outcome += outcome_changed
            removals.append({"omitted_annotator": omitted["annotator"],
                             "pattern": pattern, "pattern_status": pattern_status,
                             "pattern_changed": pattern_changed,
                             "youngest_outcome": outcome, "outcome_status": outcome_status,
                             "outcome_changed": outcome_changed})
        examined.append({
            "story_id": story["story_id"], "revision": story["revision"],
            "baseline_pattern": baseline_pattern, "baseline_pattern_status": baseline_pattern_status,
            "baseline_outcome": baseline_outcome, "baseline_outcome_status": baseline_outcome_status,
            "reviewers_tested": len(removals), "removals": removals,
        })
    return {
        "method": "leave-one-reader-out stability check; diagnostic, not a statistical confidence interval",
        "stories_examined": len(examined),
        "pattern_results_changed": fragile_pattern,
        "outcome_results_changed": fragile_outcome,
        "stories": examined,
    }
