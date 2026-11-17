import csv
import json
import tempfile
import unittest
from pathlib import Path

from story_patterns.analysis.agreement import pairwise_agreement
from story_patterns.analysis.evidence import evidence_coverage
from story_patterns.analysis.export import export_csv, export_json
from story_patterns.analysis.sample_profile import build_sample_profile
from story_patterns.errors import ConflictError
from tests.support import AppCase, batch, decision, story


class AgreementMetricsTests(unittest.TestCase):
    def test_pairwise_rates_use_only_shared_story_revisions(self):
        first = decision("tale-a", annotator="reader-a", pattern="parallel", outcome="wins")
        second = decision("tale-a", annotator="reader-b", pattern="parallel", outcome="loses")
        third = decision("tale-b", annotator="reader-a", pattern="harm", outcome="wins")
        result = pairwise_agreement({("tale-a", 1): [first, second], ("tale-b", 1): [third]})
        pair = result["pairs"][0]
        self.assertEqual(pair["compared_story_revisions"], 1)
        self.assertEqual(pair["pattern_agreement"], 1.0)
        self.assertEqual(pair["outcome_agreement"], 0.0)

    def test_disjoint_annotators_do_not_create_a_zero_denominator_pair(self):
        rows = {("a", 1): [decision("a", annotator="one")], ("b", 1): [decision("b", annotator="two")]}
        self.assertEqual(pairwise_agreement(rows)["pairs"], [])

    def test_three_readers_produce_each_pair_once(self):
        votes = [decision(annotator=name) for name in ["a", "b", "c"]]
        pairs = pairwise_agreement({("tale-a", 1): votes})["pairs"]
        self.assertEqual(len(pairs), 3)
        self.assertEqual([row["annotators"] for row in pairs], [["a", "b"], ["a", "c"], ["b", "c"]])


class EvidenceCoverageTests(unittest.TestCase):
    def test_coverage_counts_unique_events_not_repeated_citations(self):
        votes = [decision(annotator="a", evidence=["first", "third"]),
                 decision(annotator="b", evidence=["first", "third"])]
        result = evidence_coverage([story()], {("tale-a", 1): votes})
        self.assertEqual(result["total_events"], 3)
        self.assertEqual(result["cited_events"], 2)
        self.assertEqual(result["coverage_rate"], 2 / 3)
        self.assertEqual(result["stories"][0]["uncited_event_ids"], ["second"])

    def test_coverage_is_broken_down_by_actual_sibling_order(self):
        votes = [decision(annotator="a", evidence=["first"])]
        result = evidence_coverage([story()], {("tale-a", 1): votes})
        self.assertEqual(result["by_sibling_order"]["1"]["coverage_rate"], 1.0)
        self.assertEqual(result["by_sibling_order"]["2"]["coverage_rate"], 0.0)
        self.assertEqual(result["by_sibling_order"]["3"]["coverage_rate"], 0.0)

    def test_empty_cohort_has_null_rate_instead_of_division_error(self):
        result = evidence_coverage([], {})
        self.assertIsNone(result["coverage_rate"])
        self.assertEqual(result["total_events"], 0)


class SampleCompositionTests(unittest.TestCase):
    def test_profile_counts_sources_and_story_shapes_without_inference(self):
        records = [story("a", tradition="coast"), story("b", tradition="hill")]
        records[1]["characters"].append({"character_id": "fourth", "name": "Four", "sibling_order": 4})
        result = build_sample_profile(records)
        self.assertEqual(result["traditions"], {"coast": 1, "hill": 1})
        self.assertEqual(result["source_kinds"], {"local_synthetic": 2})
        self.assertEqual(result["sibling_roster_sizes"], {"3": 1, "4": 1})
        self.assertEqual(result["structure"]["stories_with_exactly_three_siblings"], 1)
        self.assertEqual(result["total_characters"], 7)
        self.assertEqual(result["mean_siblings_per_story"], 3.5)
        self.assertIn("does not estimate", result["warning"])

    def test_empty_sample_has_explicit_missing_ranges(self):
        result = build_sample_profile([])
        self.assertEqual(result["story_revisions"], 0)
        self.assertIsNone(result["structure"]["min_events"])
        self.assertEqual(result["event_counts"], {})


class ReportExportTests(AppCase, unittest.TestCase):
    def test_report_is_frozen_and_retrievable_by_content_identifier(self):
        self.import_story()
        self.add_votes()
        first = self.app.create_report()
        stored = self.app.stored_report(first["report_id"])
        self.assertEqual(stored["pattern_counts"], {"parallel": 1})
        self.app.record_decision(decision(annotator="reader-a", sequence=2, pattern="harm"))
        later = self.app.create_report()
        self.assertNotEqual(first["report_id"], later["report_id"])
        self.assertEqual(self.app.stored_report(first["report_id"])["pattern_counts"], {"parallel": 1})

    def test_repeated_analysis_of_unchanged_input_returns_same_identifier(self):
        self.import_story()
        self.add_votes()
        self.assertEqual(self.app.create_report()["report_id"], self.app.create_report()["report_id"])

    def test_json_export_round_trips_all_provenance_and_metrics(self):
        self.import_story()
        report = self.app.create_report()
        with tempfile.TemporaryDirectory() as directory:
            path = export_json(report, Path(directory) / "report.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["report_id"], report["report_id"])
        self.assertEqual(loaded["evidence_coverage"], report["evidence_coverage"])

    def test_export_refuses_existing_files_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("preserve", encoding="utf-8")
            with self.assertRaises(ConflictError):
                export_json({"x": 1}, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "preserve")

    def test_explicit_overwrite_replaces_complete_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("old", encoding="utf-8")
            export_json({"x": 2}, path, overwrite=True)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"x": 2})

    def test_csv_has_one_row_per_story_revision_and_keeps_unresolved_status(self):
        self.app.import_batch(batch([story("a"), story("b")], "two"))
        report = self.app.create_report()
        with tempfile.TemporaryDirectory() as directory:
            path = export_csv(report, Path(directory) / "report.csv")
            with path.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
        self.assertEqual([row["story_id"] for row in rows], ["a", "b"])
        self.assertEqual({row["pattern_status"] for row in rows}, {"insufficient"})

    def test_csv_escapes_formula_like_untrusted_story_titles(self):
        unsafe = story()
        unsafe["title"] = " =HYPERLINK(\"https://example.invalid\")"
        self.app.import_batch(batch([unsafe], "unsafe-title"))
        report = self.app.create_report()
        with tempfile.TemporaryDirectory() as directory:
            path = export_csv(report, Path(directory) / "report.csv")
            with path.open(encoding="utf-8", newline="") as source:
                row = next(csv.DictReader(source))
        self.assertEqual(row["title"], "'=HYPERLINK(\"https://example.invalid\")")


if __name__ == "__main__":
    unittest.main()
