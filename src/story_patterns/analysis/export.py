from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path

from story_patterns.errors import ConflictError


def _atomic_write(path: str | Path, content: str, overwrite: bool) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise ConflictError(f"output already exists: {target}; pass --force to replace it")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists() and not overwrite:
            raise ConflictError(f"output appeared during export: {target}")
        os.replace(temporary, target)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return target


def export_json(report: dict, path: str | Path, overwrite: bool = False) -> Path:
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    return _atomic_write(path, content, overwrite)


def export_csv(report: dict, path: str | Path, overwrite: bool = False) -> Path:
    from io import StringIO

    buffer = StringIO(newline="")
    columns = ["story_id", "revision", "title", "tradition", "pattern", "pattern_status",
               "youngest_outcome", "outcome_status", "final_pattern", "final_outcome",
               "resolution", "adjudication_id", "reviewer_count"]
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in report["story_results"]:
        writer.writerow({key: _spreadsheet_safe(value) if isinstance(value, str) else value
                         for key, value in row.items()})
    return _atomic_write(path, buffer.getvalue(), overwrite)


def _spreadsheet_safe(value: str) -> str:
    probe = value.lstrip()
    if probe.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
