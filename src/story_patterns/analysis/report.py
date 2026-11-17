from __future__ import annotations

from collections import Counter
from typing import Any

from story_patterns.catalog.validate import canonical_json, digest_json
from story_patterns.analysis.agreement import pairwise_agreement
from story_patterns.analysis.evidence import evidence_coverage
from story_patterns.analysis.sensitivity import leave_one_reader_out
from story_patterns.analysis.revision_drift import compare_revisions
from story_patterns.analysis.votes import vote_distribution
from story_patterns.analysis.sample_profile import build_sample_profile
from story_patterns.analysis.crosstab import consensus_crosstab
from story_patterns.catalog.history import lineage_warnings, revision_lineage
from story_patterns.errors import ConflictError


def _consensus(votes: list[str], minimum: int) -> tuple[str | None, str]:
    usable = [vote for vote in votes if vote not in {"unclear", "unknown"}]
    if len(usable) < minimum:
        return None, "insufficient"
    counts = Counter(usable)
    ordered = counts.most_common()
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None, "split"
    return ordered[0][0], "agreed"


def build_report(stories: list[dict], decisions: dict[tuple[str, int], list[dict]],
                 tradition: str | None, minimum: int, origins: dict | None = None,
                 adjudications: dict | None = None) -> dict[str, Any]:
    pattern_counts: Counter = Counter()
    outcome_counts: Counter = Counter()
    final_pattern_counts: Counter = Counter()
    final_outcome_counts: Counter = Counter()
    pattern_coverage: Counter = Counter()
    outcome_coverage: Counter = Counter()
    resolution_counts: Counter = Counter()
    used_decisions = []
    story_results = []
    for story in stories:
        identity = (story["story_id"], story["revision"])
        votes = decisions.get(identity, [])
        pattern, pattern_status = _consensus([item["pattern"] for item in votes], minimum)
        outcome, outcome_status = _consensus([item["youngest_outcome"] for item in votes], minimum)
        adjudication = (adjudications or {}).get(identity)
        resolution_counts["adjudicated" if adjudication else "reader_consensus"] += 1
        pattern_coverage[pattern_status] += 1
        outcome_coverage[outcome_status] += 1
        if pattern is not None:
            pattern_counts[pattern] += 1
        if outcome is not None:
            outcome_counts[outcome] += 1
        final_pattern = adjudication["pattern"] if adjudication else pattern
        final_outcome = adjudication["youngest_outcome"] if adjudication else outcome
        if final_pattern is not None:
            final_pattern_counts[final_pattern] += 1
        if final_outcome not in {None, "unknown"}:
            final_outcome_counts[final_outcome] += 1
        used_decisions.extend(item["decision_id"] for item in votes)
        story_results.append({
            "story_id": story["story_id"], "revision": story["revision"],
            "title": story["title"], "tradition": story["tradition"],
            "pattern": pattern, "pattern_status": pattern_status,
            "youngest_outcome": outcome, "outcome_status": outcome_status,
            "final_pattern": final_pattern, "final_outcome": final_outcome,
            "resolution": "adjudicated" if adjudication else "reader_consensus",
            "adjudication_id": adjudication["adjudication_id"] if adjudication else None,
            "adjudication_rationale": adjudication["rationale"] if adjudication else None,
            "adjudication_evidence_event_ids": adjudication["evidence_event_ids"] if adjudication else [],
            "reviewer_count": len(votes),
        })
    return {
        "criteria": {"tradition": tradition, "minimum_reviewers": minimum,
                     "unclear_and_unknown_are_abstentions": True},
        "population": {"story_revisions": len(stories), "pattern_consensus": sum(pattern_counts.values()),
                       "outcome_consensus": sum(outcome_counts.values())},
        "coverage": {
            "pattern": {key: pattern_coverage.get(key, 0) for key in ("agreed", "split", "insufficient")},
            "outcome": {key: outcome_coverage.get(key, 0) for key in ("agreed", "split", "insufficient")},
        },
        "pattern_counts": dict(sorted(pattern_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "final_pattern_counts": dict(sorted(final_pattern_counts.items())),
        "final_outcome_counts": dict(sorted(final_outcome_counts.items())),
        "adjudicated_story_revisions": sum(value is not None for value in (adjudications or {}).values()),
        "resolution_counts": {key: resolution_counts.get(key, 0)
                              for key in ("reader_consensus", "adjudicated")},
        "story_results": story_results,
        "reviewer_agreement": pairwise_agreement(decisions),
        "evidence_coverage": evidence_coverage(stories, decisions),
        "reader_sensitivity": leave_one_reader_out(stories, decisions, minimum),
        "reader_vote_distribution": vote_distribution(stories, decisions),
        "sample_profile": build_sample_profile(stories),
        "pattern_outcome_crosstab": consensus_crosstab(story_results),
        "revision_lineage": {"scope": "selected story revisions", "stories": revision_lineage(stories),
                             "warnings": lineage_warnings(revision_lineage(stories))},
        "revision_changes": compare_revisions(stories),
        "provenance": {
            "story_revisions": [f"{item['story_id']}@{item['revision']}" for item in stories],
            "decision_ids": sorted(used_decisions),
            "adjudication_ids": sorted(value["adjudication_id"] for value in (adjudications or {}).values() if value),
            "batch_ids_by_story": {
                f"{story_id}@{revision}": sorted(batch_ids)
                for (story_id, revision), batch_ids in sorted((origins or {}).items())
            },
        },
    }


class ReportService:
    def __init__(self, store):
        self.store = store

    def create(self, tradition: str | None, minimum: int) -> dict:
        from story_patterns.analysis.cohorts import select_cohort, validate_minimum

        minimum = validate_minimum(minimum)
        stories, decisions, origins, adjudications = self.store.analysis_snapshot(tradition)
        stories = select_cohort(stories, tradition)
        result = build_report(stories, decisions, tradition, minimum, origins, adjudications)
        report_id = digest_json(result)[:24]
        request_digest = digest_json({"criteria": result["criteria"], "provenance": result["provenance"]})
        document = canonical_json({"report_id": report_id, **result})
        with self.store.transaction() as connection:
            previous = connection.execute("SELECT document FROM reports WHERE report_id=?", (report_id,)).fetchone()
            if previous and previous["document"] != document:
                raise ConflictError("report identifier collision with different contents")
            connection.execute(
                "INSERT OR IGNORE INTO reports(report_id, request_digest, document) VALUES(?,?,?)",
                (report_id, request_digest, document),
            )
        return {"report_id": report_id, **result}

    def get(self, report_id: str) -> dict | None:
        return self.store.report_document(report_id)

    def compare(self, minimum: int) -> dict:
        from story_patterns.analysis.cohorts import validate_minimum
        from story_patterns.analysis.comparison import compare_traditions

        minimum = validate_minimum(minimum)
        stories, decisions, _origins, adjudications = self.store.analysis_snapshot(None)
        return compare_traditions(stories, decisions, minimum, adjudications)
