from __future__ import annotations

from story_patterns.errors import AnalysisError


def select_cohort(stories: list[dict], tradition: str | None) -> list[dict]:
    if tradition is not None and (not isinstance(tradition, str) or not tradition.strip()):
        raise AnalysisError("tradition filter must be a non-empty label or omitted")
    selected = [story for story in stories if tradition is None or story["tradition"] == tradition]
    return sorted(selected, key=lambda story: (story["story_id"], story["revision"]))


def validate_minimum(minimum: int) -> int:
    if type(minimum) is not int or minimum < 2 or minimum > 20:
        raise AnalysisError("minimum_reviewers must be an integer from 2 to 20")
    return minimum
