import unittest

from tests.support import AppCase, batch, decision, story


class ReviewQueueTests(AppCase, unittest.TestCase):
    def test_empty_and_unreviewed_tales_are_actionable(self):
        self.app.import_batch(batch([story("a"), story("b")], "two"))
        queue = self.app.review_queue()
        self.assertEqual(queue["by_status"]["unreviewed"], 2)
        self.assertEqual(queue["by_status"]["ready"], 0)
        self.assertEqual(queue["stories"][0]["missing_evidence_event_ids"], ["first", "second", "third"])

    def test_split_labels_are_visible_as_disputes_not_as_ready(self):
        self.import_story()
        self.add_votes(values=[
            decision(annotator="reader-a", pattern="parallel", outcome="wins"),
            decision(annotator="reader-b", pattern="harm", outcome="loses"),
        ])
        queue = self.app.review_queue()
        self.assertEqual(queue["by_status"]["disputed"], 1)
        self.assertEqual(queue["stories"][0]["status"], "disputed")

    def test_low_review_count_waits_for_more_independent_readers(self):
        self.import_story()
        self.app.record_decision(decision(annotator="reader-a"))
        queue = self.app.review_queue(minimum_reviewers=2)
        self.assertEqual(queue["by_status"]["needs_more_reviews"], 1)

    def test_unreferenced_events_are_reported_even_after_consensus(self):
        self.import_story()
        self.add_votes(values=[
            decision(annotator="reader-a", evidence=["first"]),
            decision(annotator="reader-b", evidence=["first"]),
        ])
        row = self.app.review_queue()["stories"][0]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["missing_evidence_event_ids"], ["second", "third"])

    def test_latest_revision_vote_replaces_old_queue_view(self):
        self.import_story(story(revision=1), "first")
        revised = story(revision=2)
        self.app.import_batch(batch([revised], "second"))
        self.app.record_decision(decision(revision=1, annotator="reader-a"))
        queue = self.app.review_queue()
        self.assertEqual([row["revision"] for row in queue["stories"]], [1, 2])
        self.assertEqual(queue["stories"][1]["status"], "unreviewed")

    def test_tradition_selection_reduces_queue_and_totals_consistently(self):
        self.app.import_batch(batch([story("coast", tradition="coast"), story("hill", tradition="hill")], "two"))
        queue = self.app.review_queue(tradition="hill")
        self.assertEqual(queue["total"], 1)
        self.assertEqual(queue["stories"][0]["story_id"], "hill")
        self.assertEqual(sum(queue["by_status"].values()), 1)

    def test_queue_orders_by_tradition_then_identity(self):
        rows = [story("z", tradition="hill"), story("b", tradition="coast"), story("a", tradition="coast")]
        self.app.import_batch(batch(rows, "ordered"))
        ids = [(item["tradition"], item["story_id"]) for item in self.app.review_queue()["stories"]]
        self.assertEqual(ids, [("coast", "a"), ("coast", "b"), ("hill", "z")])


if __name__ == "__main__":
    unittest.main()
