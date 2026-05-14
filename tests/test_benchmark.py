import json
import tempfile
import unittest
from pathlib import Path

import llm_benchmark
import llm_knowledge_graph


class BenchmarkTests(unittest.TestCase):
    def test_quality_benchmark_writes_reports_and_per_file_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            output = root / "benchmark"
            markdown.mkdir()
            (markdown / "bad.md").write_text("# Bad_Title_slug\n\n##\n", encoding="utf-8", newline="\n")
            (markdown / "good.md").write_text("# Clean Title\n\n## Abstract\n\nText.\n", encoding="utf-8", newline="\n")

            report = llm_benchmark.run_quality_benchmark([markdown], output)

            report_json = json.loads((output / "benchmark_report.json").read_text(encoding="utf-8"))
            summary = (output / "benchmark_summary.md").read_text(encoding="utf-8")
            metrics = (output / "per_file_metrics.csv").read_text(encoding="utf-8")

        self.assertEqual("markdown_quality", report["benchmark_type"])
        self.assertEqual(report, report_json)
        self.assertEqual(2, report["totals"]["markdown_file_count"])
        self.assertEqual(2, report["totals"]["finding_count"])
        self.assertIn("Markdown Quality Benchmark", summary)
        self.assertIn("bad.md", metrics)
        self.assertIn("good.md", metrics)
        self.assertIn("rule:slug_h1", metrics)

    def test_retrieval_benchmark_scores_expected_files_and_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "md"
            index = root / "kg"
            output = root / "benchmark"
            questions = root / "questions.json"
            source.mkdir()
            (source / "fibers.md").write_text(
                "# Dynamic imine protein fibers\n\n## Results\n\nAcid treatment improves imine bond recovery and mechanical strength.\n",
                encoding="utf-8",
                newline="\n",
            )
            (source / "tables.md").write_text(
                "# Dense table paper\n\n## Results\n\nCalibration weights and metrology tables.\n",
                encoding="utf-8",
                newline="\n",
            )
            llm_knowledge_graph.build_knowledge_graph(
                source,
                index,
                max_chunk_tokens=100,
                top_terms_per_chunk=3,
                embedding_model="tfidf-hash",
                embedding_dimensions=64,
            )
            questions.write_text(
                json.dumps(
                    {
                        "questions": [
                            {
                                "id": "imine",
                                "question": "Which paper discusses imine bond mechanical recovery?",
                                "expected_terms": ["imine", "mechanical"],
                                "expected_files": ["fibers.md"],
                                "mode": "vector",
                                "limit": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
                newline="\n",
            )

            report = llm_benchmark.run_retrieval_benchmark(questions, index, output)

            report_json = json.loads((output / "benchmark_report.json").read_text(encoding="utf-8"))
            summary = (output / "benchmark_summary.md").read_text(encoding="utf-8")

        result = report["questions"][0]
        self.assertEqual(report, report_json)
        self.assertEqual("retrieval", report["benchmark_type"])
        self.assertEqual(1, result["hits_returned"])
        self.assertTrue(result["expected_file_hit"])
        self.assertTrue(result["expected_term_hit"])
        self.assertEqual(["fibers.md"], result["matched_expected_files"])
        self.assertIn("imine", result["matched_expected_terms"])
        self.assertIn("Retrieval Benchmark", summary)


if __name__ == "__main__":
    unittest.main()
