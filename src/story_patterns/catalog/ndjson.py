from __future__ import annotations

import json
from pathlib import Path

from story_patterns.errors import ValidationError


def read_story_lines(text: str) -> list[dict]:
    stories = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValidationError(f"NDJSON line {line_number}: {error.msg}") from error
        if not isinstance(value, dict):
            raise ValidationError(f"NDJSON line {line_number}: each row must be a story object")
        stories.append(value)
    if not stories:
        raise ValidationError("NDJSON input contains no story records")
    return stories


def read_story_file(path: str | Path, format_name: str) -> list[dict]:
    if format_name not in {"json", "ndjson"}:
        raise ValidationError("input format must be json or ndjson")
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValidationError(f"cannot read story file {path}: {error}") from error
    if format_name == "ndjson":
        return read_story_lines(text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValidationError(f"invalid JSON: {error.msg} at line {error.lineno}") from error
    if not isinstance(value, list):
        raise ValidationError("JSON story input must be an array")
    return value
