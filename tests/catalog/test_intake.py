import copy
import unittest

from story_patterns.catalog.validate import normalize_batch, normalize_story
from story_patterns.errors import ConflictError, ValidationError
from tests.support import AppCase, batch, story


class StoryNormalizationTests(unittest.TestCase):
    def test_normalization_trims_labels_and_orders_events(self):
        source = story()
        source["title"] = "  Local tale  "
        source["events"].reverse()
        normalized = normalize_story(source)
        self.assertEqual(normalized["title"], "Local tale")
        self.assertEqual([item["sequence"] for item in normalized["events"]], [1, 2, 3])
        self.assertEqual([item["sibling_order"] for item in normalized["characters"]], [1, 2, 3])

    def test_normalization_does_not_mutate_callers_document(self):
        source = story()
        before = copy.deepcopy(source)
        normalize_story(source)
        self.assertEqual(source, before)

    def test_story_identity_and_revision_are_required(self):
        for field, value in [("story_id", " "), ("revision", 0), ("revision", True), ("title", "")]:
            with self.subTest(field=field, value=value):
                source = story()
                source[field] = value
                with self.assertRaises(ValidationError):
                    normalize_story(source)

    def test_source_kind_is_a_bounded_vocabulary(self):
        for kind in ["book", "oral_record", "local_synthetic"]:
            with self.subTest(kind=kind):
                source = story()
                source["source"]["kind"] = kind
                self.assertEqual(normalize_story(source)["source"]["kind"], kind)
        source = story()
        source["source"]["kind"] = "internet"
        with self.assertRaisesRegex(ValidationError, "source.kind"):
            normalize_story(source)

    def test_source_reference_and_shape_are_checked(self):
        for value in [None, "", {"reference": "x"}, {"reference": " ", "kind": "book"}]:
            with self.subTest(value=value):
                source = story()
                source["source"] = value
                with self.assertRaises(ValidationError):
                    normalize_story(source)

    def test_character_identifiers_and_orders_must_be_unique(self):
        duplicate_id = story()
        duplicate_id["characters"][1]["character_id"] = "eldest"
        duplicate_order = story()
        duplicate_order["characters"][1]["sibling_order"] = 1
        for source in [duplicate_id, duplicate_order]:
            with self.subTest(source=source["characters"]):
                with self.assertRaisesRegex(ValidationError, "unique"):
                    normalize_story(source)

    def test_character_order_rejects_boolean_and_non_positive_values(self):
        for order in [True, 0, -1, "2"]:
            with self.subTest(order=order):
                source = story()
                source["characters"][0]["sibling_order"] = order
                with self.assertRaisesRegex(ValidationError, "positive integer"):
                    normalize_story(source)

    def test_event_references_must_resolve_to_a_character(self):
        source = story()
        source["events"][0]["actor_id"] = "missing"
        with self.assertRaisesRegex(ValidationError, "unknown actor"):
            normalize_story(source)

    def test_event_ids_and_sequences_must_be_unique(self):
        duplicate_id = story()
        duplicate_id["events"][1]["event_id"] = "first"
        duplicate_sequence = story()
        duplicate_sequence["events"][1]["sequence"] = 1
        for source in [duplicate_id, duplicate_sequence]:
            with self.subTest(events=source["events"]):
                with self.assertRaisesRegex(ValidationError, "unique"):
                    normalize_story(source)

    def test_event_sequence_must_be_contiguous(self):
        source = story()
        source["events"][2]["sequence"] = 4
        with self.assertRaisesRegex(ValidationError, "contiguous"):
            normalize_story(source)

    def test_event_text_has_limits_and_requires_content(self):
        for field, value in [("action", " "), ("consequence", "x" * 301), ("evidence", "x" * 1001)]:
            with self.subTest(field=field):
                source = story()
                source["events"][0][field] = value
                with self.assertRaises(ValidationError):
                    normalize_story(source)

    def test_empty_collections_and_wrong_top_level_types_are_rejected(self):
        for field in ["characters", "events"]:
            source = story()
            source[field] = []
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    normalize_story(source)
        for value in [None, [], "story"]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalize_story(value)


class BatchImportTests(AppCase, unittest.TestCase):
    def test_import_persists_each_revision_and_lists_by_tradition(self):
        records = [story("tale-a"), story("tale-b", tradition="mountain")]
        result = self.app.import_batch(batch(records, "mixed-set"))
        self.assertEqual(result, {"batch_id": "mixed-set", "status": "imported", "story_count": 2})
        self.assertEqual([item["story_id"] for item in self.app.catalog.list_stories("mountain")], ["tale-b"])
        self.assertEqual(self.app.catalog.get_story("tale-a", 1)["title"], "Local tale tale-a")

    def test_same_batch_retry_is_idempotent(self):
        request = batch(batch_id="retry-me")
        first = self.app.import_batch(request)
        second = self.app.import_batch(request)
        self.assertEqual(first["status"], "imported")
        self.assertEqual(second["status"], "already_imported")
        self.assertEqual(len(self.app.catalog.list_stories()), 1)

    def test_reusing_batch_id_for_new_content_fails_without_partial_add(self):
        self.import_story()
        altered = story("tale-b")
        with self.assertRaises(ConflictError):
            self.app.import_batch(batch([altered], "batch-a"))
        self.assertEqual([item["story_id"] for item in self.app.catalog.list_stories()], ["tale-a"])

    def test_story_revision_is_immutable_across_batch_ids(self):
        self.import_story()
        changed = story()
        changed["title"] = "Rewritten under same revision"
        with self.assertRaises(ConflictError):
            self.app.import_batch(batch([changed], "different-batch"))
        self.assertEqual(self.app.catalog.get_story("tale-a", 1)["title"], "Local tale tale-a")

    def test_new_revision_is_separately_addressable(self):
        self.app.import_batch(batch([story(revision=1)], "first"))
        second = story(revision=2)
        second["title"] = "Revised telling"
        self.app.import_batch(batch([second], "second"))
        self.assertEqual(self.app.catalog.get_story("tale-a", 2)["title"], "Revised telling")
        self.assertEqual(len(self.app.catalog.list_stories()), 2)

    def test_validation_failure_precedes_any_database_write(self):
        malformed = story("tale-b")
        malformed["events"][0]["actor_id"] = "ghost"
        with self.assertRaises(ValidationError):
            self.app.import_batch(batch([story("tale-a"), malformed], "broken"))
        self.assertEqual(self.app.catalog.list_stories(), [])

    def test_conflict_in_later_record_rolls_back_batch_marker_and_earlier_rows(self):
        self.import_story()
        new_story = story("tale-b")
        conflicting = story("tale-a")
        conflicting["title"] = "Conflict"
        with self.assertRaises(ConflictError):
            self.app.import_batch(batch([new_story, conflicting], "two-record-batch"))
        self.assertEqual(len(self.app.catalog.list_stories()), 1)
        retry = self.app.import_batch(batch([new_story], "two-record-batch"))
        self.assertEqual(retry["status"], "imported")

    def test_empty_batch_and_duplicate_revision_in_batch_are_rejected(self):
        for request in [batch([], "empty"), batch([story(), story()], "repeated")]:
            with self.subTest(request=request["batch_id"]):
                with self.assertRaises(ValidationError):
                    self.app.import_batch(request)

    def test_same_story_can_be_reimported_from_a_second_batch_without_duplication(self):
        self.app.import_batch(batch([story()], "source-one"))
        result = self.app.import_batch(batch([story()], "source-two"))
        self.assertEqual(result["status"], "imported")
        self.assertEqual(len(self.app.catalog.list_stories()), 1)


if __name__ == "__main__":
    unittest.main()
