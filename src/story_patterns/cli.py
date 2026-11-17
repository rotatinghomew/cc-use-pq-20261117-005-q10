from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from story_patterns.application import StoryPatternApplication
from story_patterns.analysis.export import export_csv, export_json
from story_patterns.catalog.ndjson import read_story_file
from story_patterns.errors import NotFoundError, StoryPatternError


def read_json(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StoryPatternError(f"cannot read JSON input {path}: {error}") from error


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="story-patterns")
    commands = root.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import", help="validate and import a story batch")
    importer.add_argument("--database", required=True)
    importer.add_argument("--file", required=True)
    importer.add_argument("--format", choices=("batch", "json", "ndjson"), default="batch")
    importer.add_argument("--batch-id")
    reviewer = commands.add_parser("decide", help="record one evidence-backed review")
    reviewer.add_argument("--database", required=True)
    reviewer.add_argument("--file", required=True)
    adjudicator = commands.add_parser("adjudicate", help="record a moderator resolution separately from votes")
    adjudicator.add_argument("--database", required=True)
    adjudicator.add_argument("--file", required=True)
    history = commands.add_parser("history", help="inspect all reader and moderator revisions")
    history.add_argument("--database", required=True)
    history.add_argument("--story-id", required=True)
    history.add_argument("--revision", required=True, type=int)
    report = commands.add_parser("report", help="compute consensus with explicit coverage")
    report.add_argument("--database", required=True)
    report.add_argument("--tradition")
    report.add_argument("--minimum-reviewers", type=int, default=2)
    queue = commands.add_parser("queue", help="show stories needing review or evidence")
    queue.add_argument("--database", required=True)
    queue.add_argument("--tradition")
    queue.add_argument("--minimum-reviewers", type=int, default=2)
    exporter = commands.add_parser("export", help="export a saved report as JSON or CSV")
    exporter.add_argument("--database", required=True)
    exporter.add_argument("--report-id", required=True)
    exporter.add_argument("--format", choices=("json", "csv", "md"), required=True)
    exporter.add_argument("--output", required=True)
    exporter.add_argument("--force", action="store_true")
    audit = commands.add_parser("audit", help="check local SQLite storage integrity")
    audit.add_argument("--database", required=True)
    preview = commands.add_parser("preview", help="validate all rows without writing to SQLite")
    preview.add_argument("--file", required=True)
    preview.add_argument("--format", choices=("json", "ndjson"), required=True)
    compare = commands.add_parser("compare", help="compare tradition cohorts descriptively")
    compare.add_argument("--database", required=True)
    compare.add_argument("--minimum-reviewers", type=int, default=2)
    lineage = commands.add_parser("lineage", help="show available story revisions")
    lineage.add_argument("--database", required=True)
    manifest = commands.add_parser("manifest", help="summarize imported batches and source references")
    manifest.add_argument("--database", required=True)
    search = commands.add_parser("search", help="find stories by narrative evidence and cohort labels")
    search.add_argument("--database", required=True)
    search.add_argument("--text")
    search.add_argument("--tradition")
    search.add_argument("--source-kind", choices=("book", "oral_record", "local_synthetic"))
    search.add_argument("--sibling-order", type=int)
    search.add_argument("--revision-policy", choices=("all", "latest"), default="all")
    demo = commands.add_parser("demo", help="replay the bundled synthetic workflow")
    demo.add_argument("--database", required=True)
    demo.add_argument("--fixture", required=True)
    return root


def execute(arguments: argparse.Namespace) -> dict:
    app = StoryPatternApplication(arguments.database)
    if arguments.command == "import":
        if arguments.format == "batch":
            return app.import_batch(read_json(arguments.file))
        if not arguments.batch_id:
            raise StoryPatternError("--batch-id is required for JSON array and NDJSON imports")
        stories = read_story_file(arguments.file, arguments.format)
        return app.import_batch({"batch_id": arguments.batch_id, "stories": stories})
    if arguments.command == "decide":
        return app.record_decision(read_json(arguments.file))
    if arguments.command == "adjudicate":
        return app.record_adjudication(read_json(arguments.file))
    if arguments.command == "history":
        return app.review_history(arguments.story_id, arguments.revision)
    if arguments.command == "report":
        return app.create_report(arguments.tradition, arguments.minimum_reviewers)
    if arguments.command == "queue":
        return app.review_queue(arguments.minimum_reviewers, arguments.tradition)
    if arguments.command == "export":
        report = app.stored_report(arguments.report_id)
        if report is None:
            raise NotFoundError(f"report {arguments.report_id} was not found")
        if arguments.format == "md":
            from story_patterns.analysis.markdown import render_report
            from story_patterns.analysis.export import _atomic_write
            path = _atomic_write(arguments.output, render_report(report), arguments.force)
        else:
            writer = export_csv if arguments.format == "csv" else export_json
            path = writer(report, arguments.output, arguments.force)
        return {"report_id": arguments.report_id, "format": arguments.format, "output": str(path)}
    if arguments.command == "audit":
        return app.audit()
    if arguments.command == "preview":
        rows = read_story_file(arguments.file, arguments.format)
        return app.preview_stories(rows)
    if arguments.command == "compare":
        return app.compare_traditions(arguments.minimum_reviewers)
    if arguments.command == "lineage":
        return {"stories": app.revision_lineage()}
    if arguments.command == "manifest":
        return app.catalog_manifest()
    if arguments.command == "search":
        return app.search_stories(text=arguments.text, tradition=arguments.tradition,
                                  source_kind=arguments.source_kind, sibling_order=arguments.sibling_order,
                                  revision_policy=arguments.revision_policy)
    fixture = read_json(arguments.fixture)
    imported = app.import_batch(fixture["batch"])
    decisions = [app.record_decision(item) for item in fixture["decisions"]]
    report = app.create_report(fixture.get("tradition"), fixture.get("minimum_reviewers", 2))
    return {"import": imported, "decisions_recorded": len(decisions), "report": report}


def main(argv: list[str] | None = None) -> int:
    try:
        result = execute(parser().parse_args(argv))
    except StoryPatternError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
