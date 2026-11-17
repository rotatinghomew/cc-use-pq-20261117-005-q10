from __future__ import annotations

from collections import defaultdict

from story_patterns.analysis.comparison import compare_traditions
from story_patterns.analysis.report import build_report
from story_patterns.analysis.revision_drift import compare_revisions
from story_patterns.analysis.sample_profile import build_sample_profile
from story_patterns.catalog.history import lineage_warnings, revision_lineage
from story_patterns.catalog.validate import canonical_json
from story_patterns.errors import AnalysisError

TIE_HANDLING = (
    "Within each comparable cell, candidates are ordered by (story_id, revision) and every "
    "tradition keeps as many records as the smallest per-tradition candidate count; remaining "
    "candidates are excluded with reason tie_not_selected."
)

SPARSE_CAUTION_THRESHOLD = 5

INTERPRETATION_LIMITS = [
    "Matched sensitivity rates describe only the matched subset of these local records; "
    "they are not population estimates.",
    "Matching controls only the chosen keys; remaining differences between traditions are "
    "descriptive associations, not causal effects.",
    "Records listed under not_comparable have no comparable counterpart under the chosen keys; "
    "they are excluded from the matched rates only and remain in the unrestricted comparison.",
    "A difference that appears or disappears after matching flags sample composition for review; "
    "it neither proves nor disproves a real difference.",
]


def _key_sibling_count(story: dict, context: dict) -> int:
    return len(story["characters"])


def _key_event_count(story: dict, context: dict) -> int:
    return len(story["events"])


def _key_source_kind(story: dict, context: dict) -> str:
    return story["source"]["kind"]


def _key_revision_number(story: dict, context: dict) -> int:
    return story["revision"]


def _key_revision_recency(story: dict, context: dict) -> str:
    latest = context["latest_revision"][story["story_id"]]
    return "latest" if story["revision"] == latest else "superseded"


MATCH_KEYS = {
    "sibling_count": (_key_sibling_count, "number of sibling characters on the roster"),
    "event_count": (_key_event_count, "number of events in the revision"),
    "source_kind": (_key_source_kind, "source kind of the record"),
    "revision_number": (_key_revision_number, "revision number of the record"),
    "revision_recency": (_key_revision_recency, "latest versus superseded revision of the story"),
}


def validate_match_keys(keys) -> list[str]:
    if isinstance(keys, str) or not isinstance(keys, (list, tuple)):
        raise AnalysisError("match keys must be a list of known key names")
    normalized = []
    for key in keys:
        if not isinstance(key, str) or key not in MATCH_KEYS:
            raise AnalysisError(
                f"unknown match key {key!r}; choose from {', '.join(sorted(MATCH_KEYS))}"
            )
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise AnalysisError("at least one match key is required")
    return normalized


def _identity(story: dict) -> tuple[str, int]:
    return (story["story_id"], story["revision"])


def _label(identity: tuple[str, int]) -> str:
    return f"{identity[0]}@{identity[1]}"


def build_matched_cohort(stories: list[dict], keys: list[str]) -> tuple[dict, dict]:
    """Group records into match-key cells and keep only fully comparable sets.

    Returns the JSON-safe matching audit trail plus the selected identity -> cell
    mapping for internal use. Every record is either selected or excluded with a
    recorded reason; nothing is dropped silently.
    """
    keys = validate_match_keys(keys)
    latest_revision: dict[str, int] = {}
    for story in stories:
        latest_revision[story["story_id"]] = max(
            story["revision"], latest_revision.get(story["story_id"], 0)
        )
    context = {"latest_revision": latest_revision}
    traditions = sorted({story["tradition"] for story in stories})
    cells: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for story in stories:
        cell_key = tuple((name, MATCH_KEYS[name][0](story, context)) for name in keys)
        cells[cell_key][story["tradition"]].append(story)
    cell_rows = []
    selected: dict[tuple[str, int], dict] = {}
    exclusions = []
    ordered_cells = sorted(cells.items(), key=lambda item: canonical_json(dict(item[0])))
    for cell_key, by_tradition in ordered_cells:
        label = dict(cell_key)
        candidates = {
            tradition: [_label(_identity(item)) for item in sorted(members, key=_identity)]
            for tradition, members in sorted(by_tradition.items())
        }
        missing = [tradition for tradition in traditions if tradition not in by_tradition]
        row = {"key": label, "candidates": candidates, "missing_traditions": missing}
        if len(traditions) < 2:
            row["comparable"] = False
            row["selected"] = {}
            for tradition, members in sorted(by_tradition.items()):
                for item in members:
                    exclusions.append({
                        "story_id": item["story_id"], "revision": item["revision"],
                        "tradition": tradition, "reason": "no_other_tradition",
                        "detail": "only one tradition is present, so no cross-tradition "
                                  "counterpart can exist",
                    })
        elif missing:
            row["comparable"] = False
            row["selected"] = {}
            for tradition, members in sorted(by_tradition.items()):
                for item in members:
                    exclusions.append({
                        "story_id": item["story_id"], "revision": item["revision"],
                        "tradition": tradition, "reason": "no_shared_cell",
                        "detail": "cell has no candidate from tradition(s): " + ", ".join(missing),
                    })
        else:
            keep = min(len(members) for members in by_tradition.values())
            chosen = {}
            for tradition, members in sorted(by_tradition.items()):
                ordered = sorted(members, key=_identity)
                chosen[tradition] = ordered[:keep]
                for item in ordered[keep:]:
                    exclusions.append({
                        "story_id": item["story_id"], "revision": item["revision"],
                        "tradition": tradition, "reason": "tie_not_selected",
                        "detail": f"cell keeps {keep} record(s) per tradition under the "
                                  "(story_id, revision) ordering",
                    })
            row["comparable"] = True
            row["kept_per_tradition"] = keep
            row["selected"] = {
                tradition: [_label(_identity(item)) for item in members]
                for tradition, members in chosen.items()
            }
            for members in chosen.values():
                for item in members:
                    selected[_identity(item)] = label
        cell_rows.append(row)
    exclusions.sort(key=lambda item: (item["story_id"], item["revision"]))
    coverage = []
    for tradition in traditions:
        members = [item for item in stories if item["tradition"] == tradition]
        matched = [item for item in members if _identity(item) in selected]
        reasons: dict[str, int] = {}
        for item in exclusions:
            if item["tradition"] == tradition:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        coverage.append({
            "tradition": tradition,
            "story_revisions": len(members),
            "matched": len(matched),
            "excluded": len(members) - len(matched),
            "matched_share": len(matched) / len(members) if members else None,
            "exclusions_by_reason": dict(sorted(reasons.items())),
        })
    matching = {
        "match_keys": keys,
        "match_key_meanings": {name: MATCH_KEYS[name][1] for name in keys},
        "tie_handling": TIE_HANDLING,
        "traditions": traditions,
        "cells": cell_rows,
        "cell_counts": {
            "total": len(cell_rows),
            "comparable": sum(1 for row in cell_rows if row["comparable"]),
            "dropped": sum(1 for row in cell_rows if not row["comparable"]),
        },
        "selected_story_revisions": [_label(identity) for identity in sorted(selected)],
        "exclusions": exclusions,
        "coverage_by_tradition": coverage,
    }
    return matching, selected


def build_matched_comparison(stories: list[dict], decisions: dict, origins: dict,
                             adjudications: dict, keys: list[str], minimum: int) -> dict:
    """Chain sample profile, revision changes, reader consensus/adjudication and the
    unrestricted plus matched descriptive comparisons into one reproducible report."""
    keys = validate_match_keys(keys)
    matching, selected = build_matched_cohort(stories, keys)
    matched_stories = [item for item in stories if _identity(item) in selected]
    full = build_report(stories, decisions, None, minimum, origins, adjudications)
    unrestricted = compare_traditions(stories, decisions, minimum, adjudications)
    matched = compare_traditions(matched_stories, decisions, minimum, adjudications)
    matched["method"] = ("descriptive comparison restricted to records matched across all "
                         "traditions on the chosen keys")
    matched["interpretation_limit"] = ("Matched rates describe only the matched subset of local "
                                       "records; they are not population estimates and not "
                                       "causal effects.")
    lineage = revision_lineage(stories)
    reason_counts: dict[str, int] = {}
    for item in matching["exclusions"]:
        reason_counts[item["reason"]] = reason_counts.get(item["reason"], 0) + 1
    not_comparable = {
        "excluded_story_revisions": [
            _label((item["story_id"], item["revision"])) for item in matching["exclusions"]
        ],
        "exclusion_counts_by_reason": dict(sorted(reason_counts.items())),
        "dropped_cells": [
            {"key": row["key"], "missing_traditions": row["missing_traditions"]}
            for row in matching["cells"] if not row["comparable"]
        ],
        "note": "Excluded records have no fully comparable counterpart set under the chosen "
                "match keys; they remain in the unrestricted comparison and are absent from "
                "the matched sensitivity rates.",
    }
    warnings = []
    traditions = matching["traditions"]
    if len(traditions) < 2:
        warnings.append("fewer than two traditions are present, so no matched comparison "
                        "is possible")
    if not selected:
        warnings.append("no comparable record sets exist under the chosen match keys; "
                        "the matched sensitivity comparison is empty")
    coverage = {row["tradition"]: row for row in matching["coverage_by_tradition"]}
    for tradition in traditions:
        row = coverage[tradition]
        if row["story_revisions"] and row["matched"] == 0:
            warnings.append(f"tradition '{tradition}' contributes no matched records and is "
                            "absent from the matched sensitivity comparison")
        elif 0 < row["matched"] < SPARSE_CAUTION_THRESHOLD:
            warnings.append(f"tradition '{tradition}' has only {row['matched']} matched "
                            "record(s); matched rates are fragile descriptives, not estimates")
    if reason_counts.get("tie_not_selected"):
        warnings.append(f"{reason_counts['tie_not_selected']} record(s) were set aside by the "
                        "deterministic tie rule; see matching.exclusions")
    multi_revision = [item["story_id"] for item in lineage if item["revision_count"] > 1]
    if multi_revision and not any(key in {"revision_number", "revision_recency"} for key in keys):
        warnings.append(f"{len(multi_revision)} story id(s) have multiple revisions in scope and "
                        "revision state is not a match key; matched sets may mix revision states")
    reason_by_identity = {
        (item["story_id"], item["revision"]): item for item in matching["exclusions"]
    }
    story_results = []
    for row in full["story_results"]:
        identity = (row["story_id"], row["revision"])
        exclusion = reason_by_identity.get(identity)
        story_results.append({
            **row,
            "matched": identity in selected,
            "match_cell": selected.get(identity),
            "exclusion_reason": exclusion["reason"] if exclusion else None,
            "exclusion_detail": exclusion["detail"] if exclusion else None,
        })
    return {
        "kind": "matched_tradition_comparison",
        "method": ("chained local analysis: sample profile, revision changes, reader "
                   "consensus/adjudication, then unrestricted and matched descriptive "
                   "comparisons"),
        "criteria": {
            "match_keys": keys,
            "minimum_reviewers": minimum,
            "tie_handling": TIE_HANDLING,
            "unclear_and_unknown_are_abstentions": True,
        },
        "sample_profile": build_sample_profile(stories),
        "revision_lineage": {
            "scope": "all story revisions in the analysis sample",
            "stories": lineage,
            "warnings": lineage_warnings(lineage),
        },
        "revision_changes": compare_revisions(stories),
        "reader_consensus": {
            "coverage": full["coverage"],
            "resolution_counts": full["resolution_counts"],
            "adjudicated_story_revisions": full["adjudicated_story_revisions"],
            "reviewer_agreement": full["reviewer_agreement"],
            "reader_vote_distribution": full["reader_vote_distribution"],
            "reader_sensitivity": full["reader_sensitivity"],
        },
        "matching": matching,
        "not_comparable": not_comparable,
        "unrestricted_comparison": unrestricted,
        "matched_sensitivity": matched,
        "warnings": warnings,
        "interpretation_limits": list(INTERPRETATION_LIMITS),
        "story_results": story_results,
        "provenance": full["provenance"],
    }
