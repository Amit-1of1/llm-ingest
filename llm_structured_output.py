#!/usr/bin/env python3
"""Lightweight structured sidecars for generated Markdown."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import llm_audit_assertions
import llm_figure_cleanup


@dataclass(frozen=True)
class MarkdownStructureSummary:
    source_path: str
    output_path: str
    title: str
    headings: list[dict[str, Any]]
    figures: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    formulas: list[dict[str, Any]]
    links: list[dict[str, Any]]


def build_structure_summary(markdown_text: str, *, source_path: Path, output_path: Path) -> MarkdownStructureSummary:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    headings: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    formulas: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    title = ""
    in_formula = False

    for line_number, line in enumerate(lines, 1):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            label = heading.group(2).strip()
            headings.append({"line": line_number, "level": level, "text": label})
            if level == 1 and not title:
                title = label

        image_label = llm_figure_cleanup.figure_label_from_image_line(line)
        if image_label:
            figures.append(
                {
                    "line": line_number,
                    "label": image_label,
                    "markdown": line.strip(),
                    "caption_nearby": _nearby_caption(lines, line_number - 1, image_label),
                }
            )

        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            tables.append({"line": line_number, "markdown": line.strip()[:240]})

        if line.strip().startswith("$$"):
            if not in_formula:
                formulas.append({"line": line_number, "kind": "display_math"})
            in_formula = not in_formula
        elif "> [!NOTE] Equation omitted" in line:
            formulas.append({"line": line_number, "kind": "missing_formula_note"})

        for match in re.finditer(r"(?<!!)\[([^\]]{1,120})\]\(([^)\s]+)\)", line):
            links.append({"line": line_number, "text": match.group(1), "target": match.group(2)})

    return MarkdownStructureSummary(
        source_path=str(source_path),
        output_path=str(output_path),
        title=title,
        headings=headings,
        figures=figures,
        tables=tables,
        formulas=formulas,
        links=links,
    )


def write_markdown_sidecars(markdown_path: Path, source_path: Path, markdown_text: str) -> tuple[Path, Path]:
    structure = build_structure_summary(markdown_text, source_path=source_path, output_path=markdown_path)
    structure_path = markdown_path.with_suffix(".extraction.json")
    quality_path = markdown_path.with_suffix(".quality.json")

    structure_path.write_text(json.dumps(asdict(structure), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    findings = [
        {
            "path": finding.path,
            "line": finding.line,
            "rule": finding.rule,
            "message": finding.message,
            "excerpt": finding.excerpt,
        }
        for finding in llm_audit_assertions.scan_markdown_file(markdown_path)
    ]
    quality_payload = {
        "source_path": str(source_path),
        "output_path": str(markdown_path),
        "assertion_count": len(findings),
        "assertions": findings,
        "counts": {
            "headings": len(structure.headings),
            "figures": len(structure.figures),
            "tables": len(structure.tables),
            "formulas": len(structure.formulas),
            "links": len(structure.links),
        },
    }
    quality_path.write_text(json.dumps(quality_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return structure_path, quality_path


def _nearby_caption(lines: list[str], image_index: int, image_label: str) -> str:
    start = max(0, image_index - 2)
    end = min(len(lines), image_index + 8)
    for line in lines[start:end]:
        if llm_figure_cleanup.figure_label_from_caption_line(line) == image_label:
            return re.sub(r"\s+", " ", line.strip().lstrip("> ").strip())[:500]
    return ""
