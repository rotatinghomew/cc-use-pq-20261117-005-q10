import json
import tempfile
import unittest
from pathlib import Path

from story_patterns.catalog.ndjson import read_story_file, read_story_lines
from story_patterns.errors import ValidationError
from tests.support import story


class NdjsonReaderTests(unittest.TestCase):
    def test_rows_are_parsed_in_original_order_and_blank_lines_are_ignored(self):
        first = story("first")
        second = story("second")
        content = "\n" + json.dumps(first) + "\n\n" + json.dumps(second) + "\n"
        rows = read_story_lines(content)
        self.assertEqual([row["story_id"] for row in rows], ["first", "second"])

    def test_malformed_line_reports_its_physical_line_number(self):
        content = json.dumps(story("first")) + "\nnot-json\n"
        with self.assertRaisesRegex(ValidationError, "line 2"):
            read_story_lines(content)

    def test_row_must_be_an_object_not_a_scalar_or_array(self):
        for line in ["[]", "3", "null", '"text"']:
            with self.subTest(line=line):
                with self.assertRaisesRegex(ValidationError, "object"):
                    read_story_lines(line)

    def test_blank_only_stream_is_not_a_successful_empty_batch(self):
        with self.assertRaisesRegex(ValidationError, "no story records"):
            read_story_lines("\n  \n")

    def test_json_array_loader_preserves_rows_for_domain_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stories.json"
            path.write_text(json.dumps([story("a"), story("b")]), encoding="utf-8")
            rows = read_story_file(path, "json")
        self.assertEqual([row["story_id"] for row in rows], ["a", "b"])

    def test_json_loader_rejects_batch_object_to_avoid_format_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            path.write_text(json.dumps({"batch_id": "id", "stories": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "array"):
                read_story_file(path, "json")

    def test_unknown_format_fails_before_trying_to_parse_contents(self):
        with self.assertRaisesRegex(ValidationError, "format"):
            read_story_file("unneeded.json", "yaml")

    def test_file_reader_reports_missing_file_as_domain_error(self):
        with self.assertRaisesRegex(ValidationError, "cannot read"):
            read_story_file("does-not-exist.ndjson", "ndjson")

    def test_utf8_file_reader_rejects_invalid_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.ndjson"
            path.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(ValidationError, "cannot read"):
                read_story_file(path, "ndjson")


if __name__ == "__main__":
    unittest.main()
