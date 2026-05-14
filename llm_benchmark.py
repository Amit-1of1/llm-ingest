#!/usr/bin/env python3
"""Offline benchmark harness for Markdown quality and graph retrieval utility."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import llm_audit_assertions
import llm_knowledge_graph


def run_quality_benchmark(markdown_dirs: list[Path], output_dir: Path) -> dict[str, Any]:
    """Scan generated Markdown folders and write quality benchmark artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    directory_reports: list[dict[str, Any]] = []
    per_file_rows: list[dict[str, Any]] = []
    all_findings: list[dict[str, Any]] = []
    all_rules: set[str] = set()

    for markdown_dir in markdown_dirs:
        root = Path(markdown_dir)
        findings = llm_audit_assertions.scan_markdown_tree(root)
        markdown_files = sorted(path for path in root.rglob("*.md") if path.is_file())
        rule_counts = Counter(finding.rule for finding in findings)
        file_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)

        for finding in findings:
            file_counts[finding.path][finding.rule] += 1
            all_rules.add(finding.rule)
            finding_payload = asdict(finding)
            finding_payload["directory"] = str(root)
            all_findings.append(finding_payload)

        for file_path in markdown_files:
            relative = file_path.relative_to(root).as_posix()
            row: dict[str, Any] = {
                "directory": str(root),
                "file": relative,
                "finding_count": sum(file_counts[relative].values()),
            }
            for rule, count in file_counts[relative].items():
                row[f"rule:{rule}"] = count
            per_file_rows.append(row)

        directory_reports.append(
            {
                "path": str(root),
                "markdown_file_count": len(markdown_files),
                "finding_count": len(findings),
                "findings_by_rule": dict(sorted(rule_counts.items())),
            }
        )

    report = {
        "benchmark_type": "markdown_quality",
        "created_at": _utc_now(),
        "output_directories": directory_reports,
        "totals": {
            "directory_count": len(directory_reports),
            "markdown_file_count": sum(item["markdown_file_count"] for item in directory_reports),
            "finding_count": sum(item["finding_count"] for item in directory_reports),
        },
        "findings": all_findings,
    }

    _write_json(output_dir / "benchmark_report.json", report)
    _write_text(output_dir / "benchmark_summary.md", _format_quality_summary(report))
    _write_per_file_csv(output_dir / "per_file_metrics.csv", per_file_rows, sorted(all_rules))
    return report


def run_retrieval_benchmark(questions_path: Path, index_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run local graph/RAG retrieval questions and write benchmark artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = _load_questions(Path(questions_path))

    results: list[dict[str, Any]] = []
    for index, question_record in enumerate(questions, 1):
        question_id = str(question_record.get("id") or f"q{index}")
        question = _required_string(question_record, "question", question_id)
        expected_terms = _string_list(question_record.get("expected_terms", []), "expected_terms", question_id)
        expected_files = _string_list(question_record.get("expected_files", []), "expected_files", question_id)
        retrieval_mode = str(question_record.get("mode") or "hybrid")
        limit = int(question_record.get("limit") or 8)

        query_result = llm_knowledge_graph.query_knowledge_graph(
            Path(index_dir),
            question,
            retrieval_mode=retrieval_mode,
            limit=limit,
        )
        hits = [_json_ready(asdict(hit)) for hit in query_result.hits]
        matched_files = _matched_expected_files(expected_files, hits)
        matched_terms = _matched_expected_terms(expected_terms, hits)
        hits_returned = len(hits)

        result = {
            "id": question_id,
            "question": question,
            "mode": query_result.retrieval_mode,
            "limit": limit,
            "hits_returned": hits_returned,
            "expected_files": expected_files,
            "matched_expected_files": matched_files,
            "expected_file_hit": bool(matched_files) if expected_files else None,
            "expected_file_recall": _ratio(len(matched_files), len(expected_files)) if expected_files else None,
            "expected_file_precision_proxy": _file_precision_proxy(expected_files, hits) if expected_files else None,
            "expected_terms": expected_terms,
            "matched_expected_terms": matched_terms,
            "expected_term_hit": bool(matched_terms) if expected_terms else None,
            "expected_term_recall": _ratio(len(matched_terms), len(expected_terms)) if expected_terms else None,
            "hits": hits,
        }
        results.append(result)

    report = {
        "benchmark_type": "retrieval",
        "created_at": _utc_now(),
        "index_dir": str(Path(index_dir)),
        "questions_path": str(Path(questions_path)),
        "summary": _retrieval_summary(results),
        "questions": results,
    }
    _write_json(output_dir / "benchmark_report.json", report)
    _write_text(output_dir / "benchmark_summary.md", _format_retrieval_summary(report))
    return report


def _format_quality_summary(report: dict[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        "# Markdown Quality Benchmark",
        "",
        f"- Output directories: {totals['directory_count']}",
        f"- Markdown files: {totals['markdown_file_count']}",
        f"- Known issue findings: {totals['finding_count']}",
        "",
        "| Directory | Files | Findings |",
        "| --- | ---: | ---: |",
    ]
    for item in report["output_directories"]:
        lines.append(f"| `{item['path']}` | {item['markdown_file_count']} | {item['finding_count']} |")

    rule_totals = Counter()
    for item in report["output_directories"]:
        rule_totals.update(item["findings_by_rule"])
    if rule_totals:
        lines.extend(["", "## Findings by Rule", "", "| Rule | Count |", "| --- | ---: |"])
        for rule, count in rule_totals.most_common():
            lines.append(f"| `{rule}` | {count} |")
    else:
        lines.extend(["", "No known Markdown quality regressions were found."])
    return "\n".join(lines).strip() + "\n"


def _format_retrieval_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Retrieval Benchmark",
        "",
        f"- Questions: {summary['question_count']}",
        f"- Average hits returned: {summary['average_hits_returned']:.2f}",
        f"- Expected file hit rate: {_format_optional_rate(summary['expected_file_hit_rate'])}",
        f"- Expected term hit rate: {_format_optional_rate(summary['expected_term_hit_rate'])}",
        "",
        "| ID | Mode | Hits | File Hit | Term Hit |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for item in report["questions"]:
        lines.append(
            "| {id} | `{mode}` | {hits} | {file_hit} | {term_hit} |".format(
                id=item["id"],
                mode=item["mode"],
                hits=item["hits_returned"],
                file_hit=_format_optional_bool(item["expected_file_hit"]),
                term_hit=_format_optional_bool(item["expected_term_hit"]),
            )
        )
    return "\n".join(lines).strip() + "\n"


def _write_per_file_csv(path: Path, rows: list[dict[str, Any]], rules: list[str]) -> None:
    fieldnames = ["directory", "file", "finding_count"] + [f"rule:{rule}" for rule in rules]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, 0 if field.startswith("rule:") else "") for field in fieldnames})


def _load_questions(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("questions")
    if not isinstance(payload, list):
        raise ValueError("Questions JSON must be a list or an object with a 'questions' list.")
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Question record #{index} must be an object.")
    return payload


def _required_string(record: dict[str, Any], key: str, question_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Question {question_id!r} is missing a non-empty {key!r}.")
    return value.strip()


def _string_list(value: Any, key: str, question_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Question {question_id!r} field {key!r} must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _matched_expected_files(expected_files: list[str], hits: list[dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    hit_paths = [_normalize_path(str(hit.get("path", ""))) for hit in hits]
    for expected in expected_files:
        expected_norm = _normalize_path(expected)
        if any(path == expected_norm or path.endswith("/" + expected_norm) for path in hit_paths):
            matched.append(expected)
    return matched


def _matched_expected_terms(expected_terms: list[str], hits: list[dict[str, Any]]) -> list[str]:
    pieces: list[str] = []
    for hit in hits:
        pieces.extend(
            [
                str(hit.get("heading", "")),
                str(hit.get("path", "")),
                str(hit.get("text", "")),
                " ".join(str(term) for term in hit.get("terms", ())),
            ]
        )
    haystack = "\n".join(pieces).lower()
    return [term for term in expected_terms if term.lower() in haystack]


def _file_precision_proxy(expected_files: list[str], hits: list[dict[str, Any]]) -> float:
    if not hits:
        return 0.0
    expected = [_normalize_path(path) for path in expected_files]
    hit_matches = 0
    for hit in hits:
        hit_path = _normalize_path(str(hit.get("path", "")))
        if any(hit_path == item or hit_path.endswith("/" + item) for item in expected):
            hit_matches += 1
    return _ratio(hit_matches, len(hits))


def _retrieval_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    file_scored = [item for item in results if item["expected_file_hit"] is not None]
    term_scored = [item for item in results if item["expected_term_hit"] is not None]
    return {
        "question_count": len(results),
        "average_hits_returned": _ratio(sum(item["hits_returned"] for item in results), len(results)),
        "expected_file_hit_rate": _ratio(sum(1 for item in file_scored if item["expected_file_hit"]), len(file_scored)) if file_scored else None,
        "expected_term_hit_rate": _ratio(sum(1 for item in term_scored if item["expected_term_hit"]), len(term_scored)) if term_scored else None,
        "average_expected_file_recall": _average_optional(item["expected_file_recall"] for item in results),
        "average_expected_term_recall": _average_optional(item["expected_term_recall"] for item in results),
    }


def _average_optional(values: Any) -> float | None:
    kept = [value for value in values if value is not None]
    if not kept:
        return None
    return _ratio(sum(kept), len(kept))


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip("/").lower()


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def _format_optional_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline benchmark harness for LLM Ingest outputs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    quality = subparsers.add_parser("quality", help="Benchmark Markdown quality over one or more output directories.")
    quality.add_argument("markdown_dirs", nargs="+", help="Generated Markdown output directories to scan.")
    quality.add_argument("--output-dir", default="_benchmark_reports", help="Directory for benchmark_report.json, benchmark_summary.md, and per_file_metrics.csv.")

    retrieval = subparsers.add_parser("retrieval", help="Benchmark graph/RAG retrieval against a questions JSON file.")
    retrieval.add_argument("--index-dir", required=True, help="Existing graph index directory.")
    retrieval.add_argument("--questions", required=True, help="Questions JSON file.")
    retrieval.add_argument("--output-dir", default="_benchmark_reports", help="Directory for benchmark_report.json and benchmark_summary.md.")

    args = parser.parse_args(argv)
    try:
        if args.command == "quality":
            run_quality_benchmark([Path(item) for item in args.markdown_dirs], Path(args.output_dir))
        elif args.command == "retrieval":
            run_retrieval_benchmark(Path(args.questions), Path(args.index_dir), Path(args.output_dir))
        else:
            parser.error(f"Unknown command: {args.command}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
