import unittest

from story_patterns.analysis.report import _consensus
from story_patterns.analysis.crosstab import consensus_crosstab
from story_patterns.errors import AnalysisError
from tests.support import AppCase, batch, decision, story


class ConsensusRuleTests(unittest.TestCase):
    def test_consensus_accepts_a_strict_leader_when_review_quorum_is_met(self):
        self.assertEqual(_consensus(["parallel", "parallel", "harm"], 2), ("parallel", "agreed"))

    def test_tie_is_split_even_when_quorum_is_met(self):
        self.assertEqual(_consensus(["parallel", "harm"], 2), (None, "split"))

    def test_too_few_usable_votes_is_insufficient(self):
        self.assertEqual(_consensus(["parallel", "unclear"], 2), (None, "insufficient"))

    def test_unknown_and_unclear_do_not_outvote_interpretations(self):
        self.assertEqual(_consensus(["parallel", "unclear", "unknown"], 1), ("parallel", "agreed"))

    def test_crosstab_uses_only_stories_with_both_consensus_axes(self):
        rows = [
            {"pattern": "parallel", "youngest_outcome": "wins"},
            {"pattern": "parallel", "youngest_outcome": "wins"},
            {"pattern": "harm", "youngest_outcome": None},
            {"pattern": None, "youngest_outcome": "loses"},
            {"pattern": None, "youngest_outcome": None},
        ]
        result = consensus_crosstab(rows)
        self.assertEqual(result["counts"], {"parallel": {"wins": 2}})
        self.assertEqual(result["eligible_story_revisions"], 2)
        self.assertEqual(result["excluded_for_both"], 1)

    def test_threshold_counts_only_non_abstaining_labels(self):
        self.assertEqual(_consensus(["parallel", "unclear", "harm"], 3), (None, "insufficient"))


class CohortAndCoverageTests(AppCase, unittest.TestCase):
    def test_unreviewed_stories_remain_in_cohort_denominator(self):
        self.app.import_batch(batch([story("a"), story("b"), story("c")], "three"))
        self.add_votes("a")
        report = self.app.create_report()
        self.assertEqual(report["population"]["story_revisions"], 3)
        self.assertEqual(report["population"]["pattern_consensus"], 1)
        self.assertEqual(report["coverage"]["pattern"]["insufficient"], 2)

    def test_tradition_filter_is_applied_before_votes_are_aggregated(self):
        coastal = story("coastal", tradition="coast")
        upland = story("upland", tradition="upland")
        self.app.import_batch(batch([coastal, upland], "mixed"))
        self.add_votes("coastal")
        self.add_votes("upland", values=[
            decision("upland", annotator="reader-a", pattern="harm", outcome="loses"),
            decision("upland", annotator="reader-b", pattern="harm", outcome="loses"),
        ])
        report = self.app.create_report("upland")
        self.assertEqual(report["population"]["story_revisions"], 1)
        self.assertEqual(report["pattern_counts"], {"harm": 1})
        self.assertEqual(report["provenance"]["story_revisions"], ["upland@1"])

    def test_no_filter_includes_each_tradition_without_mixing_identifiers(self):
        records = [story("a", tradition="one"), story("b", tradition="two")]
        self.app.import_batch(batch(records, "two-traditions"))
        report = self.app.create_report()
        self.assertEqual(report["population"]["story_revisions"], 2)
        self.assertEqual(report["criteria"]["tradition"], None)

    def test_disagreement_is_visible_and_does_not_enter_pattern_rate(self):
        self.import_story()
        self.add_votes(values=[
            decision(annotator="reader-a", pattern="parallel"),
            decision(annotator="reader-b", pattern="harm"),
        ])
        report = self.app.create_report()
        self.assertEqual(report["coverage"]["pattern"]["split"], 1)
        self.assertEqual(report["population"]["pattern_consensus"], 0)
        self.assertEqual(report["story_results"][0]["pattern_status"], "split")

    def test_pattern_and_outcome_can_have_different_coverage(self):
        self.import_story()
        self.add_votes(values=[
            decision(annotator="reader-a", pattern="parallel", outcome="wins"),
            decision(annotator="reader-b", pattern="parallel", outcome="unknown"),
        ])
        report = self.app.create_report()
        self.assertEqual(report["coverage"]["pattern"]["agreed"], 1)
        self.assertEqual(report["coverage"]["outcome"]["insufficient"], 1)

    def test_minimum_reviewer_threshold_is_validated_before_reporting(self):
        for threshold in [True, 0, 1, 21, "2"]:
            with self.subTest(threshold=threshold):
                with self.assertRaises(AnalysisError):
                    self.app.create_report(minimum_reviewers=threshold)

    def test_filter_rejects_empty_string_instead_of_silently_empty_report(self):
        with self.assertRaises(AnalysisError):
            self.app.create_report("")

    def test_exact_tradition_match_does_not_trim_stored_identity(self):
        self.import_story(story(tradition="Coast "))
        report = self.app.create_report("coast")
        self.assertEqual(report["population"]["story_revisions"], 0)

    def test_coverage_categories_always_sum_to_story_population(self):
        records = [story(f"tale-{number}") for number in range(4)]
        self.app.import_batch(batch(records, "coverage-four"))
        self.add_votes("tale-0")
        self.add_votes("tale-1", values=[
            decision("tale-1", annotator="reader-a"),
            decision("tale-1", annotator="reader-b", pattern="harm"),
        ])
        self.add_votes("tale-2", values=[decision("tale-2", annotator="reader-a")])
        report = self.app.create_report()
        pattern_total = sum(report["coverage"]["pattern"].values())
        outcome_total = sum(report["coverage"]["outcome"].values())
        self.assertEqual(pattern_total, 4)
        self.assertEqual(outcome_total, 4)


if __name__ == "__main__":
    unittest.main()
