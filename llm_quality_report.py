#!/usr/bin/env python3
"""Compare Markdown quality before and after a cleanup pass."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import llm_audit_assertions


def build_quality_comparison(before_dir: Path, after_dir: Path) -> str:
    before = _issue_counts(before_dir) if before_dir.exists() else {}
    after = _issue_counts(after_dir) if after_dir.exists() else {}
    files = sorted(set(before) | set(after))

    total_before = sum(before.values())
    total_after = sum(after.values())
    lines = [
        "# Markdown Quality Comparison",
        "",
        f"- Before: `{before_dir}`",
        f"- After: `{after_dir}`",
        f"- Total known issues before: {total_before}",
        f"- Total known issues after: {total_after}",
        f"- Net change: {total_after - total_before:+d}",
        "",
        "| File | Before | After | Change |",
        "| --- | ---: | ---: | ---: |",
    ]
    for file in files:
        before_count = before.get(file, 0)
        after_count = after.get(file, 0)
        lines.append(f"| `{file}` | {before_count} | {after_count} | {after_count - before_count:+d} |")

    lines.extend(["", "## Issue Types", "", "| Scope | Rule | Count |", "| --- | --- | ---: |"])
    for scope, directory in (("before", before_dir), ("after", after_dir)):
        for rule, count in _rule_counts(directory).most_common():
            lines.append(f"| {scope} | `{rule}` | {count} |")
    return "\n".join(lines).strip() + "\n"


def write_quality_comparison(before_dir: Path, after_dir: Path, output_path: Path) -> Path:
    text = build_quality_comparison(before_dir, after_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8", newline="\n")
    return output_path


def _issue_counts(root: Path) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    if not root.exists() or not root.is_dir():
        return {}
    for finding in llm_audit_assertions.scan_markdown_tree(root):
        counts[finding.path] += 1
    return dict(counts)


def _rule_counts(root: Path) -> Counter[str]:
    if not root.exists() or not root.is_dir():
        return Counter()
    return Counter(finding.rule for finding in llm_audit_assertions.scan_markdown_tree(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a before/after Markdown quality comparison report.")
    parser.add_argument("--before", required=True, help="Baseline generated Markdown directory.")
    parser.add_argument("--after", required=True, help="New generated Markdown directory.")
    parser.add_argument("--output", required=True, help="Output Markdown report path.")
    args = parser.parse_args(argv)
    output = write_quality_comparison(Path(args.before), Path(args.after), Path(args.output))
    print(f"Wrote quality comparison: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
