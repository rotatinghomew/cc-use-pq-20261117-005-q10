from __future__ import annotations

from collections import defaultdict
from itertools import combinations


def pairwise_agreement(decisions: dict) -> dict:
    comparisons = defaultdict(lambda: {"compared": 0, "pattern_matches": 0, "outcome_matches": 0})
    for votes in decisions.values():
        by_annotator = {vote["annotator"]: vote for vote in votes}
        for first, second in combinations(sorted(by_annotator), 2):
            key = (first, second)
            summary = comparisons[key]
            summary["compared"] += 1
            summary["pattern_matches"] += by_annotator[first]["pattern"] == by_annotator[second]["pattern"]
            summary["outcome_matches"] += by_annotator[first]["youngest_outcome"] == by_annotator[second]["youngest_outcome"]
    output = []
    for (first, second), summary in sorted(comparisons.items()):
        compared = summary["compared"]
        output.append({
            "annotators": [first, second],
            "compared_story_revisions": compared,
            "pattern_matches": summary["pattern_matches"],
            "pattern_agreement": summary["pattern_matches"] / compared,
            "outcome_matches": summary["outcome_matches"],
            "outcome_agreement": summary["outcome_matches"] / compared,
        })
    return {"method": "exact pairwise agreement; descriptive only", "pairs": output}
