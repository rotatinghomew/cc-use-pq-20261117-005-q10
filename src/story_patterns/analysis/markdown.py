from __future__ import annotations

import json


def _table(rows: list[dict], columns: list[tuple[str, str]]) -> list[str]:
    headings = [label for _, label in columns]
    lines = ["| " + " | ".join(headings) + " |", "| " + " | ".join("---" for _ in headings) + " |"]
    for row in rows:
        cells = [str(row.get(key, "" )).replace("|", "\\|").replace("\n", " ") for key, _ in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render_report(report: dict) -> str:
    if report.get("kind") == "matched_tradition_comparison":
        return render_matched_report(report)
    population = report["population"]
    criteria = report["criteria"]
    lines = [
        f"# Narrative analysis report {report['report_id']}", "",
        "This report summarizes annotated local records. It does not make literary claims on its own.", "",
        "## Scope", "",
        f"- Tradition filter: {criteria['tradition'] or 'all'}",
        f"- Minimum independent readers: {criteria['minimum_reviewers']}",
        f"- Story revisions: {population['story_revisions']}",
        f"- Pattern consensus: {population['pattern_consensus']}",
        f"- Outcome consensus: {population['outcome_consensus']}", "",
        "## Independent-reader consensus counts", "",
    ]
    lines.extend(_table([{"pattern": key, "count": value} for key, value in report["pattern_counts"].items()],
                        [("pattern", "Pattern"), ("count", "Stories")]))
    lines.extend(["", "## Final pattern counts", ""])
    lines.extend(_table([{"pattern": key, "count": value}
                         for key, value in report["final_pattern_counts"].items()],
                        [("pattern", "Pattern"), ("count", "Stories")]))
    lines.extend(["", "## Coverage", "", "Status counts retain unresolved records in the denominator.", ""])
    coverage = report["coverage"]["pattern"]
    lines.extend(_table([{"status": key, "count": value} for key, value in coverage.items()],
                        [("status", "Pattern review status"), ("count", "Stories")]))
    lines.extend(["", "## Provenance", "", "Story revisions and decision IDs used:", "",
                  "```json", json.dumps(report["provenance"], ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def _comparison_rows(comparison: dict) -> list[dict]:
    rows = []
    for group in comparison["groups"]:
        rates = ", ".join(f"{key}={value:.3f}" for key, value in group["pattern_rates"].items())
        rows.append({
            "tradition": group["tradition"],
            "story_revisions": group["story_revisions"],
            "pattern_consensus": group["pattern_consensus"],
            "pattern_rates": rates or "(none)",
        })
    return rows


def render_matched_report(report: dict) -> str:
    criteria = report["criteria"]
    matching = report["matching"]
    profile = report["sample_profile"]
    lines = [
        f"# Matched tradition comparison {report['report_id']}", "",
        "Chained descriptive analysis over local records: sample profile, revision changes, "
        "reader consensus/adjudication, then an unrestricted and a matched comparison. "
        "Nothing here is a causal or population claim.", "",
        "## Matching criteria", "",
        f"- Match keys: {', '.join(criteria['match_keys'])}",
        f"- Minimum independent readers: {criteria['minimum_reviewers']}",
        f"- Tie handling: {criteria['tie_handling']}", "",
        "## Sample profile", "",
    ]
    lines.extend(_table(
        [{"tradition": key, "story_revisions": value}
         for key, value in profile["traditions"].items()],
        [("tradition", "Tradition"), ("story_revisions", "Story revisions")]))
    coverage_rows = [{
        "tradition": row["tradition"],
        "story_revisions": row["story_revisions"],
        "matched": row["matched"],
        "excluded": row["excluded"],
        "matched_share": f"{row['matched_share']:.3f}" if row["matched_share"] is not None else "",
    } for row in matching["coverage_by_tradition"]]
    lines.extend(["", "## Matching coverage", ""])
    lines.extend(_table(coverage_rows,
                        [("tradition", "Tradition"), ("story_revisions", "Records"),
                         ("matched", "Matched"), ("excluded", "Excluded"),
                         ("matched_share", "Matched share")]))
    lines.extend(["", "## Exclusions", "",
                  f"Comparable cells: {matching['cell_counts']['comparable']} of "
                  f"{matching['cell_counts']['total']}", ""])
    lines.extend(_table(
        [{"reason": key, "records": value}
         for key, value in report["not_comparable"]["exclusion_counts_by_reason"].items()],
        [("reason", "Exclusion reason"), ("records", "Records")]))
    lines.extend(["", "## Unrestricted comparison", ""])
    lines.extend(_table(_comparison_rows(report["unrestricted_comparison"]),
                        [("tradition", "Tradition"), ("story_revisions", "Records"),
                         ("pattern_consensus", "Pattern consensus"),
                         ("pattern_rates", "Pattern rates")]))
    lines.extend(["", "## Matched sensitivity comparison", ""])
    if report["matched_sensitivity"]["groups"]:
        lines.extend(_table(_comparison_rows(report["matched_sensitivity"]),
                            [("tradition", "Tradition"), ("story_revisions", "Records"),
                             ("pattern_consensus", "Pattern consensus"),
                             ("pattern_rates", "Pattern rates")]))
    else:
        lines.append("(no comparable records; the sensitivity comparison is empty)")
    lines.extend(["", "## Scope that cannot be compared", ""])
    excluded = report["not_comparable"]["excluded_story_revisions"]
    lines.append(", ".join(excluded) if excluded else "(none)")
    lines.extend(["", "## Revision changes", ""])
    if report["revision_changes"]:
        for change in report["revision_changes"]:
            lines.append(f"- {change['story_id']}: revision {change['from_revision']} -> "
                         f"{change['to_revision']}")
    else:
        lines.append("(no revision-to-revision changes in scope)")
    lines.extend(["", "## Warnings", ""])
    for warning in report["warnings"] or ["(none)"]:
        lines.append(f"- {warning}")
    lines.extend(["", "## Interpretation limits", ""])
    for limit in report["interpretation_limits"]:
        lines.append(f"- {limit}")
    lines.extend(["", "## Provenance", "",
                  "```json", json.dumps(report["provenance"], ensure_ascii=False, indent=2),
                  "```", ""])
    return "\n".join(lines)
