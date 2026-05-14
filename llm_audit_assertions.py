#!/usr/bin/env python3
"""Regression assertions for generated Markdown quality."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditAssertionFinding:
    path: str
    line: int
    rule: str
    message: str
    excerpt: str


_LINE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("empty_heading", re.compile(r"^#{1,6}\s*$"), "Empty Markdown heading left in body."),
    ("metadata_cover_sheet", re.compile(r"\b(?:Manuscript title|Number of words)\b", re.IGNORECASE), "Submission cover-sheet metadata leaked into body."),
    ("placeholder_affiliation", re.compile(r"\b\d+\s+TBA\b|\bTBA\b"), "Placeholder affiliation text leaked into body."),
    ("running_header", re.compile(r"Nature Communications\||Article\s+https?://doi\.org/", re.IGNORECASE), "Journal running header/footer leaked into body."),
    ("known_mojibake", re.compile(r"\b(?:fbers|specifc)\b", re.IGNORECASE), "Known legacy OCR/encoding artifact remains."),
    ("known_artifact_phrase", re.compile(r"B\[2\]\s*obs|curve\]\[|MJ/m\^3\s+MPa", re.IGNORECASE), "Known formula/prose artifact remains."),
)

_TITLE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("slug_h1", re.compile(r"^#\s+\S*_[^\n]*$"), "H1 still looks like a filename slug."),
    ("bad_sentence_title", re.compile(r"^#\s+(?:Herein,|Finally,|Feasibility of|Authors?:)", re.IGNORECASE), "H1 appears to be extracted prose or author metadata, not the article title."),
    ("truncated_title", re.compile(r"^#\s+(?:Blueprint for a High-Performance Biomaterial:|Composition and Hierarchical Organisation of a|Robust Biological Fibers Based on)\s*$", re.IGNORECASE), "H1 matches a known truncated title."),
    ("journal_h1", re.compile(r"^#\s+(?:Microbial Cell Factories|Nature Communications)\s*$", re.IGNORECASE), "H1 is a journal name, not the article title."),
)


def scan_markdown_file(path: Path, *, root: Path | None = None) -> list[AuditAssertionFinding]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    rel = path.relative_to(root).as_posix() if root is not None else path.as_posix()
    findings: list[AuditAssertionFinding] = []

    if b"\r\n" in raw or b"\r" in raw:
        findings.append(AuditAssertionFinding(rel, 1, "crlf_line_endings", "CRLF line endings found; generated Markdown should be normalized to LF.", ""))

    lines = text.splitlines()
    for index, line in enumerate(lines, 1):
        if index <= 20 and line.startswith("# "):
            for rule, pattern, message in _TITLE_RULES:
                if pattern.search(line):
                    findings.append(AuditAssertionFinding(rel, index, rule, message, _excerpt(line)))
        for rule, pattern, message in _LINE_RULES:
            if pattern.search(line):
                findings.append(AuditAssertionFinding(rel, index, rule, message, _excerpt(line)))

    in_references = False
    for index, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r"^##\s+References\b", stripped, flags=re.IGNORECASE):
            in_references = True
            continue
        if in_references and stripped.startswith("## "):
            in_references = False
        if in_references and len(re.findall(r"(?:^|\s)\d{1,3}\.\s+[A-Z]", line)) >= 2:
            findings.append(AuditAssertionFinding(rel, index, "packed_references", "Multiple numbered references appear fused on one line.", _excerpt(line)))
    return findings


def scan_markdown_tree(root: Path) -> list[AuditAssertionFinding]:
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Markdown directory does not exist: {root}")
    findings: list[AuditAssertionFinding] = []
    for path in sorted(root.rglob("*.md")):
        if path.is_file():
            findings.extend(scan_markdown_file(path, root=root))
    return findings


def format_findings(findings: list[AuditAssertionFinding]) -> str:
    if not findings:
        return "Audit assertions passed: no known Markdown regressions found.\n"
    lines = [f"Audit assertions failed: {len(findings)} finding(s).", ""]
    for finding in findings:
        location = f"{finding.path}:{finding.line}"
        lines.append(f"- `{finding.rule}` at `{location}`: {finding.message}")
        if finding.excerpt:
            lines.append(f"  `{finding.excerpt}`")
    return "\n".join(lines).strip() + "\n"


def _excerpt(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()[:180]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail on known generated-Markdown quality regressions.")
    parser.add_argument("markdown_dir", help="Folder containing generated Markdown files.")
    args = parser.parse_args(argv)
    try:
        findings = scan_markdown_tree(Path(args.markdown_dir))
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    sys.stdout.write(format_findings(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
