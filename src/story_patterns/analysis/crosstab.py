from __future__ import annotations

from collections import Counter


def consensus_crosstab(story_results: list[dict]) -> dict:
    pairs = Counter()
    excluded_pattern = 0
    excluded_outcome = 0
    excluded_both = 0
    for row in story_results:
        pattern = row["pattern"]
        outcome = row["youngest_outcome"]
        if pattern is None and outcome is None:
            excluded_both += 1
        elif pattern is None:
            excluded_pattern += 1
        elif outcome is None:
            excluded_outcome += 1
        else:
            pairs[(pattern, outcome)] += 1
    matrix = {}
    for (pattern, outcome), count in sorted(pairs.items()):
        matrix.setdefault(pattern, {})[outcome] = count
    return {
        "basis": "stories with both independent-reader consensus labels",
        "eligible_story_revisions": sum(pairs.values()),
        "excluded_for_pattern": excluded_pattern + excluded_both,
        "excluded_for_outcome": excluded_outcome + excluded_both,
        "excluded_for_both": excluded_both,
        "counts": matrix,
    }
