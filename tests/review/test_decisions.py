import unittest

from story_patterns.errors import ConflictError, NotFoundError, ValidationError
from tests.support import AppCase, batch, decision, story


class DecisionValidationTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.import_story()

    def test_valid_decision_keeps_sorted_event_evidence(self):
        record = decision(evidence=["third", "first"])
        self.app.record_decision(record)
        stored = self.app.review.decisions_for("tale-a", 1)[0]
        self.assertEqual(stored["evidence_event_ids"], ["first", "third"])
        self.assertEqual(stored["annotator"], "reader-a")

    def test_review_requires_existing_exact_story_revision(self):
        for story_id, revision in [("missing", 1), ("tale-a", 2)]:
            record = decision(story_id=story_id, revision=revision)
            with self.subTest(story=story_id, revision=revision):
                with self.assertRaises(NotFoundError):
                    self.app.record_decision(record)

    def test_decision_idempotency_and_identifier_conflicts(self):
        record = decision(decision_id="stable-review")
        self.assertEqual(self.app.record_decision(record)["status"], "recorded")
        self.assertEqual(self.app.record_decision(record)["status"], "already_recorded")
        altered = decision(decision_id="stable-review", pattern="harm")
        with self.assertRaises(ConflictError):
            self.app.record_decision(altered)
        self.assertEqual(len(self.app.review.decisions_for("tale-a", 1)), 1)

    def test_annotator_sequence_is_unique_even_with_distinct_decision_ids(self):
        self.app.record_decision(decision(sequence=1, decision_id="one"))
        with self.assertRaises(ConflictError):
            self.app.record_decision(decision(sequence=1, decision_id="two"))
        self.app.record_decision(decision(sequence=2, decision_id="three"))
        self.assertEqual(len(self.app.review.decisions_for("tale-a", 1)), 1)

    def test_new_sequence_supersedes_old_vote_for_one_annotator(self):
        self.app.record_decision(decision(sequence=1, pattern="parallel", outcome="wins"))
        self.app.record_decision(decision(sequence=2, pattern="harm", outcome="loses"))
        latest = self.app.review.decisions_for("tale-a", 1)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["pattern"], "harm")
        self.assertEqual(latest[0]["youngest_outcome"], "loses")

    def test_evidence_must_name_real_events_from_the_same_revision(self):
        invalid_values = [[], ["missing"], ["first", "first"], ["first", 4]]
        for evidence in invalid_values:
            with self.subTest(evidence=evidence):
                with self.assertRaises(ValidationError):
                    self.app.record_decision(decision(evidence=evidence))

    def test_evidence_from_a_different_revision_is_not_accepted(self):
        revised = story(revision=2)
        revised["events"][0]["event_id"] = "rev2-first"
        self.app.import_batch(batch([revised], "revision-two"))
        record = decision(revision=2, evidence=["first"])
        with self.assertRaises(ValidationError):
            self.app.record_decision(record)

    def test_only_supported_categories_are_accepted(self):
        for key, value in [("pattern", "maybe"), ("youngest_outcome", "survives")]:
            with self.subTest(key=key):
                record = decision()
                record[key] = value
                with self.assertRaises(ValidationError):
                    self.app.record_decision(record)

    def test_unknown_values_are_explicit_review_abstentions(self):
        record = decision(pattern="unclear", outcome="unknown")
        self.app.record_decision(record)
        stored = self.app.review.decisions_for("tale-a", 1)[0]
        self.assertEqual(stored["pattern"], "unclear")
        self.assertEqual(stored["youngest_outcome"], "unknown")

    def test_sequence_rejects_bool_and_non_positive_numbers(self):
        for sequence in [True, 0, -2, "1"]:
            with self.subTest(sequence=sequence):
                record = decision(sequence=sequence)
                with self.assertRaises(ValidationError):
                    self.app.record_decision(record)

    def test_review_notes_are_optional_bounded_text(self):
        accepted = decision()
        accepted["note"] = "  Evidence is indirect.  "
        self.app.record_decision(accepted)
        self.assertEqual(self.app.review.decisions_for("tale-a", 1)[0]["note"], "Evidence is indirect.")
        for note in [12, "x" * 1001]:
            with self.subTest(note_type=type(note).__name__):
                another = decision(annotator=f"reader-{type(note).__name__}")
                another["note"] = note
                with self.assertRaises(ValidationError):
                    self.app.record_decision(another)

    def test_annotator_and_decision_id_must_be_nonempty_strings(self):
        for key, value in [("annotator", " "), ("decision_id", "")]:
            with self.subTest(key=key):
                record = decision()
                record[key] = value
                with self.assertRaises(ValidationError):
                    self.app.record_decision(record)

    def test_revision_votes_are_isolated(self):
        revision_two = story(revision=2)
        self.app.import_batch(batch([revision_two], "revision-two"))
        self.app.record_decision(decision(revision=1, annotator="reader-a"))
        self.app.record_decision(decision(revision=2, annotator="reader-a", decision_id="revision-two-vote"))
        self.assertEqual(len(self.app.review.decisions_for("tale-a", 1)), 1)
        self.assertEqual(len(self.app.review.decisions_for("tale-a", 2)), 1)


if __name__ == "__main__":
    unittest.main()
