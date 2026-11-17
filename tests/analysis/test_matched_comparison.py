import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from story_patterns.analysis.export import export_csv, export_json
from story_patterns.analysis.markdown import render_report
from story_patterns.analysis.matched import MATCH_KEYS, build_matched_cohort, validate_match_keys
from story_patterns.cli import main
from story_patterns.errors import AnalysisError
from tests.support import AppCase, batch, decision, story


def shaped(story_id, tradition, siblings=3, events=3, revision=1, kind="local_synthetic"):
    """Story record with a chosen roster size, event count, revision and source kind."""
    record = story(story_id, revision=revision, tradition=tradition)
    record["source"]["kind"] = kind
    while len(record["characters"]) > siblings:
        removed = record["characters"].pop()
        record["events"] = [event for event in record["events"]
                            if event["actor_id"] != removed["character_id"]]
    while len(record["characters"]) < siblings:
        order = len(record["characters"]) + 1
        record["characters"].append({"character_id": f"extra-{order}", "name": f"Extra {order}",
                                     "sibling_order": order})
    while len(record["events"]) > events:
        record["events"].pop()
    while len(record["events"]) < events:
        sequence = len(record["events"]) + 1
        record["events"].append({
            "event_id": f"extra-event-{sequence}", "sequence": sequence,
            "actor_id": record["characters"][0]["character_id"],
            "action": "extra step", "consequence": "extra result", "evidence": "extra note",
        })
    for sequence, event in enumerate(record["events"], start=1):
        event["sequence"] = sequence
    return record


class MatchKeyValidationTests(unittest.TestCase):
    def test_unknown_empty_and_non_list_keys_are_rejected(self):
        for keys in [[], ["nonsense"], "sibling_count", [3], None]:
            with self.subTest(keys=keys):
                with self.assertRaises(AnalysisError):
                    validate_match_keys(keys)

    def test_duplicate_keys_collapse_and_registry_lists_revision_keys(self):
        self.assertEqual(validate_match_keys(["event_count", "event_count", "sibling_count"]),
                         ["event_count", "sibling_count"])
        self.assertIn("revision_number", MATCH_KEYS)
        self.assertIn("revision_recency", MATCH_KEYS)


class MatchedCohortEngineTests(unittest.TestCase):
    def test_shared_cell_selects_one_record_per_tradition(self):
        records = [story("a", tradition="coast"), story("b", tradition="hill")]
        matching, selected = build_matched_cohort(records, ["sibling_count"])
        self.assertEqual(matching["cell_counts"], {"total": 1, "comparable": 1, "dropped": 0})
        self.assertEqual(matching["selected_story_revisions"], ["a@1", "b@1"])
        self.assertEqual(set(selected), {("a", 1), ("b", 1)})
        cell = matching["cells"][0]
        self.assertEqual(cell["candidates"], {"coast": ["a@1"], "hill": ["b@1"]})
        self.assertEqual(cell["selected"], {"coast": ["a@1"], "hill": ["b@1"]})
        self.assertEqual(cell["key"], {"sibling_count": 3})

    def test_unshared_cells_explain_which_traditions_are_missing(self):
        coast = story("a", tradition="coast")
        hill = story("b", tradition="hill")
        hill["characters"].append({"character_id": "fourth", "name": "Four", "sibling_order": 4})
        matching, selected = build_matched_cohort([coast, hill], ["sibling_count"])
        self.assertEqual(selected, {})
        reasons = {item["story_id"]: item for item in matching["exclusions"]}
        self.assertEqual(reasons["a"]["reason"], "no_shared_cell")
        self.assertIn("hill", reasons["a"]["detail"])
        self.assertIn("coast", reasons["b"]["detail"])
        self.assertEqual(matching["cell_counts"]["dropped"], 2)

    def test_tie_rule_keeps_lowest_story_id_and_records_the_rest(self):
        records = [story("b", tradition="coast"), story("a", tradition="coast"),
                   story("c", tradition="hill")]
        matching, selected = build_matched_cohort(records, ["sibling_count"])
        self.assertEqual(set(selected), {("a", 1), ("c", 1)})
        ties = [item for item in matching["exclusions"] if item["reason"] == "tie_not_selected"]
        self.assertEqual([item["story_id"] for item in ties], ["b"])
        cell = matching["cells"][0]
        self.assertEqual(cell["kept_per_tradition"], 1)
        self.assertEqual(cell["candidates"]["coast"], ["a@1", "b@1"])
        again, _ = build_matched_cohort(records, ["sibling_count"])
        self.assertEqual(again, matching)

    def test_revision_number_key_pairs_matching_revision_states(self):
        records = [story("a", revision=1, tradition="coast"),
                   story("a", revision=2, tradition="coast"),
                   story("b", revision=1, tradition="hill")]
        matching, selected = build_matched_cohort(records, ["revision_number"])
        self.assertEqual(set(selected), {("a", 1), ("b", 1)})
        reasons = {(item["story_id"], item["revision"]): item["reason"]
                   for item in matching["exclusions"]}
        self.assertEqual(reasons[("a", 2)], "no_shared_cell")

    def test_revision_recency_key_separates_latest_from_superseded(self):
        records = [story("a", revision=1, tradition="coast"),
                   story("a", revision=2, tradition="coast"),
                   story("b", revision=1, tradition="hill"),
                   story("b", revision=2, tradition="hill")]
        matching, selected = build_matched_cohort(records, ["revision_recency"])
        self.assertEqual(set(selected), {("a", 1), ("a", 2), ("b", 1), ("b", 2)})
        self.assertEqual(matching["cell_counts"], {"total": 2, "comparable": 2, "dropped": 0})
        labels = sorted(tuple(sorted(cell["key"].items())) for cell in matching["cells"])
        self.assertEqual(labels, [(("revision_recency", "latest"),),
                                  (("revision_recency", "superseded"),)])

    def test_single_tradition_marks_every_record_not_comparable(self):
        matching, selected = build_matched_cohort([story("a"), story("b")], ["sibling_count"])
        self.assertEqual(selected, {})
        self.assertEqual({item["reason"] for item in matching["exclusions"]},
                         {"no_other_tradition"})


class MatchedComparisonReportTests(AppCase, unittest.TestCase):
    def import_pair(self):
        self.app.import_batch(batch([shaped("coast-a", "coast"), shaped("hill-a", "hill")],
                                    "matched-pair"))
        self.add_votes("coast-a")
        self.add_votes("hill-a")

    def import_mixed_structures(self):
        self.app.import_batch(batch([shaped("coast-a", "coast"),
                                     shaped("coast-b", "coast", siblings=4),
                                     shaped("hill-a", "hill")], "mixed-structures"))
        self.add_votes("coast-a")
        harm_votes = lambda sid: [
            decision(sid, annotator="reader-a", pattern="harm", outcome="loses"),
            decision(sid, annotator="reader-b", pattern="harm", outcome="loses"),
        ]
        self.add_votes("coast-b", values=harm_votes("coast-b"))
        self.add_votes("hill-a", values=harm_votes("hill-a"))

    def test_chained_report_links_all_stages_and_freezes(self):
        self.import_pair()
        report = self.app.compare_traditions_matched(["sibling_count"])
        for section in ("sample_profile", "revision_changes", "revision_lineage",
                        "reader_consensus", "matching", "not_comparable",
                        "unrestricted_comparison", "matched_sensitivity",
                        "warnings", "interpretation_limits", "story_results", "provenance"):
            self.assertIn(section, report)
        self.assertEqual(report["sample_profile"]["traditions"], {"coast": 1, "hill": 1})
        self.assertEqual(report["unrestricted_comparison"]["groups"][0]["pattern_rates"],
                         {"parallel": 1.0})
        self.assertEqual(report["matched_sensitivity"]["groups"][0]["pattern_rates"],
                         {"parallel": 1.0})
        again = self.app.compare_traditions_matched(["sibling_count"])
        self.assertEqual(report["report_id"], again["report_id"])
        self.assertEqual(self.app.stored_report(report["report_id"])["matching"],
                         report["matching"])
        self.assertTrue(self.app.audit()["ok"])

    def test_unrestricted_rates_are_kept_next_to_matched_sensitivity(self):
        self.import_mixed_structures()
        report = self.app.compare_traditions_matched(["sibling_count"])
        unrestricted = {g["tradition"]: g for g in report["unrestricted_comparison"]["groups"]}
        matched = {g["tradition"]: g for g in report["matched_sensitivity"]["groups"]}
        self.assertEqual(unrestricted["coast"]["pattern_rates"], {"harm": 0.5, "parallel": 0.5})
        self.assertEqual(matched["coast"]["pattern_rates"], {"parallel": 1.0})
        self.assertEqual(matched["hill"]["pattern_rates"], {"harm": 1.0})
        self.assertEqual(report["not_comparable"]["excluded_story_revisions"], ["coast-b@1"])
        exclusion = report["matching"]["exclusions"][0]
        self.assertEqual((exclusion["story_id"], exclusion["reason"]),
                         ("coast-b", "no_shared_cell"))
        coverage = {row["tradition"]: row for row in report["matching"]["coverage_by_tradition"]}
        self.assertEqual(coverage["coast"]["story_revisions"], 2)
        self.assertEqual(coverage["coast"]["matched"], 1)
        self.assertEqual(coverage["coast"]["matched_share"], 0.5)

    def test_story_results_carry_match_status_cell_and_reasons(self):
        self.import_mixed_structures()
        report = self.app.compare_traditions_matched(["sibling_count"])
        rows = {row["story_id"]: row for row in report["story_results"]}
        self.assertTrue(rows["coast-a"]["matched"])
        self.assertEqual(rows["coast-a"]["match_cell"], {"sibling_count": 3})
        self.assertFalse(rows["coast-b"]["matched"])
        self.assertEqual(rows["coast-b"]["exclusion_reason"], "no_shared_cell")
        self.assertIn("hill", rows["coast-b"]["exclusion_detail"])

    def test_tie_handling_and_candidates_are_saved_with_the_report(self):
        self.app.import_batch(batch([shaped("coast-b", "coast"), shaped("coast-a", "coast"),
                                     shaped("hill-a", "hill")], "ties"))
        report = self.app.compare_traditions_matched(["sibling_count"])
        cell = report["matching"]["cells"][0]
        self.assertEqual(cell["candidates"]["coast"], ["coast-a@1", "coast-b@1"])
        self.assertEqual(cell["selected"]["coast"], ["coast-a@1"])
        self.assertEqual(report["not_comparable"]["exclusion_counts_by_reason"],
                         {"tie_not_selected": 1})
        self.assertIn("(story_id, revision)", report["criteria"]["tie_handling"])
        self.assertTrue(any("tie rule" in warning for warning in report["warnings"]))

    def test_sparse_and_unmatched_scope_is_stated_not_hidden(self):
        self.app.import_batch(batch([shaped("coast-a", "coast", siblings=3),
                                     shaped("hill-a", "hill", siblings=5)], "disjoint"))
        report = self.app.compare_traditions_matched(["sibling_count"])
        self.assertEqual(report["matched_sensitivity"]["groups"], [])
        self.assertEqual(report["not_comparable"]["exclusion_counts_by_reason"],
                         {"no_shared_cell": 2})
        self.assertEqual(sorted(report["not_comparable"]["excluded_story_revisions"]),
                         ["coast-a@1", "hill-a@1"])
        self.assertTrue(any("empty" in warning for warning in report["warnings"]))
        self.assertTrue(any("no matched records" in warning for warning in report["warnings"]))
        self.assertTrue(any("not causal" in limit for limit in report["interpretation_limits"]))
        self.assertTrue(any("not population estimates" in limit
                            for limit in report["interpretation_limits"]))

    def test_sparse_matched_samples_are_flagged_as_fragile(self):
        self.import_pair()
        report = self.app.compare_traditions_matched(["sibling_count"])
        self.assertTrue(any("fragile descriptives" in warning for warning in report["warnings"]))

    def test_revision_state_change_is_visible_and_changes_report_id(self):
        self.import_pair()
        first = self.app.compare_traditions_matched(["sibling_count"])
        self.app.import_batch(batch([shaped("coast-a", "coast", revision=2)], "rev2"))
        second = self.app.compare_traditions_matched(["sibling_count"])
        self.assertNotEqual(first["report_id"], second["report_id"])
        self.assertEqual(len(second["revision_changes"]), 1)
        change = second["revision_changes"][0]
        self.assertEqual((change["story_id"], change["from_revision"], change["to_revision"]),
                         ("coast-a", 1, 2))
        self.assertTrue(any("revision state is not a match key" in warning
                            for warning in second["warnings"]))

    def test_revision_keys_make_revision_states_comparable(self):
        self.app.import_batch(batch([
            shaped("coast-a", "coast", revision=1), shaped("coast-a", "coast", revision=2),
            shaped("hill-a", "hill", revision=1), shaped("hill-a", "hill", revision=2),
        ], "revision-keyed"))
        report = self.app.compare_traditions_matched(["revision_number"])
        self.assertEqual(report["matching"]["cell_counts"],
                         {"total": 2, "comparable": 2, "dropped": 0})
        self.assertEqual(len(report["matching"]["selected_story_revisions"]), 4)
        self.assertFalse(any("revision state is not a match key" in warning
                             for warning in report["warnings"]))

    def test_adjudication_enters_the_chained_report_and_matched_final_counts(self):
        self.import_pair()
        self.app.record_adjudication({
            "adjudication_id": "adj-1", "story_id": "coast-a", "story_revision": 1,
            "moderator": "editor-1", "sequence": 1, "pattern": "harm",
            "youngest_outcome": "loses", "evidence_event_ids": ["first"],
            "rationale": "Editor review of the harm reading.",
        })
        report = self.app.compare_traditions_matched(["sibling_count"])
        coast = next(group for group in report["matched_sensitivity"]["groups"]
                     if group["tradition"] == "coast")
        self.assertEqual(coast["pattern_counts"], {"parallel": 1})
        self.assertEqual(coast["final_pattern_counts"], {"harm": 1})
        self.assertEqual(report["reader_consensus"]["adjudicated_story_revisions"], 1)
        self.assertEqual(report["provenance"]["adjudication_ids"], ["adj-1"])

    def test_empty_sample_states_that_no_comparison_is_possible(self):
        report = self.app.compare_traditions_matched(["sibling_count"])
        self.assertEqual(report["matched_sensitivity"]["groups"], [])
        self.assertTrue(any("fewer than two traditions" in warning
                            for warning in report["warnings"]))
        self.assertEqual(report["not_comparable"]["excluded_story_revisions"], [])

    def test_invalid_minimum_or_keys_are_rejected_before_any_report_is_stored(self):
        self.import_pair()
        with self.assertRaises(AnalysisError):
            self.app.compare_traditions_matched(["sibling_count"], minimum_reviewers=1)
        with self.assertRaises(AnalysisError):
            self.app.compare_traditions_matched(["bogus"])
        self.assertEqual(self.app.store.catalog_audit_snapshot()["reports"], [])


class MatchedReportRenderingTests(AppCase, unittest.TestCase):
    def test_markdown_and_json_exports_carry_the_matched_report(self):
        self.app.import_batch(batch([shaped("coast-a", "coast"), shaped("hill-a", "hill")],
                                    "matched-pair"))
        self.add_votes("coast-a")
        self.add_votes("hill-a")
        report = self.app.compare_traditions_matched(["sibling_count"])
        markdown = render_report(report)
        self.assertIn("Matched tradition comparison", markdown)
        self.assertIn("Matched sensitivity comparison", markdown)
        self.assertIn("Interpretation limits", markdown)
        self.assertIn("Matching coverage", markdown)
        with tempfile.TemporaryDirectory() as directory:
            path = export_json(report, Path(directory) / "matched.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["report_id"], report["report_id"])
        self.assertEqual(loaded["not_comparable"], report["not_comparable"])
        self.assertEqual(loaded["matching"]["cells"], report["matching"]["cells"])

    def test_csv_export_lists_one_row_per_record_without_crashing(self):
        self.app.import_batch(batch([shaped("coast-a", "coast"), shaped("hill-a", "hill")],
                                    "matched-pair"))
        report = self.app.compare_traditions_matched(["sibling_count"])
        with tempfile.TemporaryDirectory() as directory:
            path = export_csv(report, Path(directory) / "matched.csv")
            with path.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
        self.assertEqual([row["story_id"] for row in rows], ["coast-a", "hill-a"])


class MatchedCompareCliTests(AppCase, unittest.TestCase):
    def seed(self):
        self.app.import_batch(batch([shaped("coast-a", "coast"), shaped("hill-a", "hill")],
                                    "matched-pair"))
        self.add_votes("coast-a")
        self.add_votes("hill-a")

    def test_cli_runs_the_chain_and_prints_the_frozen_report(self):
        self.seed()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["matched-compare", "--database", self.database,
                         "--match-by", "sibling_count, event_count"])
        self.assertEqual(code, 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["criteria"]["match_keys"], ["sibling_count", "event_count"])
        self.assertIn("matched_sensitivity", output)
        self.assertEqual(self.app.stored_report(output["report_id"])["kind"],
                         "matched_tradition_comparison")

    def test_cli_rejects_unknown_match_keys_with_an_error(self):
        self.seed()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["matched-compare", "--database", self.database, "--match-by", "bogus"])
        self.assertEqual(code, 2)
        self.assertIn("unknown match key", json.loads(stderr.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
