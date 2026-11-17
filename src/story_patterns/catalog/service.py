from __future__ import annotations

from story_patterns.errors import ConflictError
from story_patterns.catalog.validate import canonical_json, normalize_batch


class CatalogService:
    def __init__(self, store):
        self.store = store

    def import_batch(self, raw: dict) -> dict:
        batch_id, stories, digest = normalize_batch(raw)
        with self.store.transaction() as connection:
            previous = connection.execute(
                "SELECT digest, story_count FROM import_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if previous:
                if previous["digest"] != digest:
                    raise ConflictError(f"batch {batch_id} already identifies different content")
                return {"batch_id": batch_id, "status": "already_imported", "story_count": previous["story_count"]}
            for story in stories:
                existing = connection.execute(
                    "SELECT document FROM stories WHERE story_id = ? AND revision = ?",
                    (story["story_id"], story["revision"]),
                ).fetchone()
                document = canonical_json(story)
                if existing and existing["document"] != document:
                    raise ConflictError(f"story {story['story_id']} revision {story['revision']} conflicts")
            connection.execute(
                "INSERT INTO import_batches(batch_id, digest, story_count) VALUES(?,?,?)",
                (batch_id, digest, len(stories)),
            )
            for story in stories:
                connection.execute(
                    "INSERT OR IGNORE INTO stories(story_id, revision, title, tradition, source_kind, document) "
                    "VALUES(?,?,?,?,?,?)",
                    (story["story_id"], story["revision"], story["title"], story["tradition"],
                     story["source"]["kind"], canonical_json(story)),
                )
                connection.execute(
                    "INSERT INTO batch_stories(batch_id, story_id, revision) VALUES(?,?,?)",
                    (batch_id, story["story_id"], story["revision"]),
                )
        return {"batch_id": batch_id, "status": "imported", "story_count": len(stories)}

    def get_story(self, story_id: str, revision: int) -> dict | None:
        return self.store.story_document(story_id, revision)

    def list_stories(self, tradition: str | None = None) -> list[dict]:
        return self.store.list_stories(tradition)

    def preview(self, rows: list[dict]) -> dict:
        from story_patterns.catalog.preview import preview_rows

        result = preview_rows(rows)
        result.pop("normalized_stories")
        return result

    def lineage(self) -> list[dict]:
        from story_patterns.catalog.history import revision_lineage

        return revision_lineage(self.store.list_stories())

    def manifest(self) -> dict:
        from story_patterns.catalog.manifest import build_manifest

        batches, stories = self.store.catalog_manifest()
        return build_manifest(batches, stories)

    def search(self, **criteria) -> list[dict]:
        from story_patterns.catalog.query import search_stories

        return search_stories(self.store.list_stories(), **criteria)

    def audit(self) -> dict:
        from story_patterns.catalog.audit import audit_catalog

        result = audit_catalog(self.store.catalog_audit_snapshot())
        database_issues = self.store.integrity_issues()
        result["database_issues"] = database_issues
        result["issues"].extend({"scope": "sqlite", "identity": "database", "problem": issue}
                                for issue in database_issues)
        result["issue_count"] = len(result["issues"])
        result["ok"] = result["issue_count"] == 0
        return result
