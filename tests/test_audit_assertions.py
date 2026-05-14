import tempfile
import unittest
from pathlib import Path

import llm_audit_assertions
import llm_ingest
import llm_quality_report


class AuditAssertionTests(unittest.TestCase):
    def test_flags_known_markdown_regressions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad = root / "bad.md"
            bad.write_text(
                "# Herein, we introduce a method fragment\n\n##\n\nNature Communications| (2023) 14:2127\n\n## References\n\n1. Alpha. 2. Beta.\n",
                encoding="utf-8",
                newline="\n",
            )
            findings = llm_audit_assertions.scan_markdown_tree(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("bad_sentence_title", rules)
        self.assertIn("empty_heading", rules)
        self.assertIn("running_header", rules)
        self.assertIn("packed_references", rules)

    def test_clean_markdown_passes_assertions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "good.md").write_text(
                "# Protein fibers with self-recoverable mechanical properties via dynamic imine chemistry\n\n## Abstract\n\nClean prose.\n",
                encoding="utf-8",
                newline="\n",
            )
            findings = llm_audit_assertions.scan_markdown_tree(root)
        self.assertEqual([], findings)

    def test_quality_report_compares_issue_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            after.mkdir()
            (before / "paper.md").write_text("# Bad_Title_slug\n\n##\n", encoding="utf-8", newline="\n")
            (after / "paper.md").write_text("# Good Title\n\n## Abstract\n\nText.\n", encoding="utf-8", newline="\n")
            report = llm_quality_report.build_quality_comparison(before, after)
        self.assertIn("Total known issues before: 2", report)
        self.assertIn("Total known issues after: 0", report)

    def test_ingest_audit_report_writes_assertion_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "bad.md"
            output.write_text("# Bad_Title_slug\n\n##\n", encoding="utf-8", newline="\n")
            issue_counts = llm_ingest._audit_issue_counts(output)
            report = llm_ingest.AuditReport(
                created_at="now",
                manifest_path="manifest.json",
                cache_dir="cache",
                report_dir=str(root),
                baseline_dirs=(),
                backend_labels=("custom_off",),
                backend_plan={},
                missing_samples=(),
                results=(
                    llm_ingest.AuditRunResult(
                        sample_id="bad",
                        sample_label="bad.pdf",
                        source_kind="baseline",
                        category="baseline",
                        backend_requested="custom",
                        backend_label="custom_off",
                        backend_used="custom",
                        status="ok",
                        output_path=str(output),
                        asset_dir=str(root / "bad_assets"),
                        tokens=10,
                        asset_count=0,
                        issue_counts=issue_counts,
                        issue_total=sum(issue_counts.values()),
                        log_excerpt="",
                    ),
                ),
            )
            llm_ingest._write_audit_report(root, report)
            assertion_report = (root / "audit_assertions.md").read_text(encoding="utf-8")

        self.assertIn("assertion_empty_heading", issue_counts)
        self.assertIn("empty_heading", assertion_report)


if __name__ == "__main__":
    unittest.main()
