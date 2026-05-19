import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import llm_knowledge_graph


class RAGArchitectureUpgradeTests(unittest.TestCase):
    def test_bm25_rrf_and_evidence_grading_prefer_exact_scientific_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "md"
            index = root / "kg"
            source.mkdir()
            (source / "mechanics.md").write_text(
                "# Mechanical recovery paper\n\n"
                "## Results\n\n"
                "Acid treatment at pH 5.5 improves dynamic imine bond recovery and tensile strength in protein fibers.\n",
                encoding="utf-8",
                newline="\n",
            )
            (source / "general.md").write_text(
                "# General polymer paper\n\n"
                "## Overview\n\n"
                "This review discusses broad polymer manufacturing and unrelated coating examples.\n",
                encoding="utf-8",
                newline="\n",
            )

            llm_knowledge_graph.build_knowledge_graph(
                source,
                index,
                max_chunk_tokens=100,
                top_terms_per_chunk=5,
                embedding_model="hash",
                embedding_dimensions=64,
            )
            result = llm_knowledge_graph.query_knowledge_graph(
                index,
                "pH 5.5 imine bond tensile strength",
                retrieval_mode="hybrid",
                limit=2,
            )

        self.assertGreaterEqual(len(result.hits), 1)
        self.assertIn("mechanics.md", result.hits[0].path)
        self.assertGreater(result.hits[0].rrf_score, 0)
        self.assertIn(result.hits[0].evidence_grade, {"strong", "usable"})
        self.assertIn(result.answerability, {"high", "partial"})

    def test_figure_and_table_records_are_indexed_as_multimodal_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "md"
            index = root / "kg"
            source.mkdir()
            (source / "figures.md").write_text(
                "# Figure-rich paper\n\n"
                "## Results\n\n"
                "![Figure 2 tensile stress curve](fig_assets/page_002.png)\n\n"
                "| Sample | Toughness |\n"
                "| --- | --- |\n"
                "| Fiber A | 120 MJ/m^3 |\n\n"
                "The figure and table summarize stress strain behavior.\n",
                encoding="utf-8",
                newline="\n",
            )

            report = llm_knowledge_graph.build_knowledge_graph(
                source,
                index,
                max_chunk_tokens=100,
                top_terms_per_chunk=5,
                embedding_model="none",
            )
            result = llm_knowledge_graph.query_knowledge_graph(
                index,
                "Figure 2 toughness stress strain table",
                retrieval_mode="lexical",
                limit=1,
            )
            multimodal = json.loads((index / "multimodal_index.json").read_text(encoding="utf-8"))
            community = json.loads((index / "community_summaries.json").read_text(encoding="utf-8"))
            sparse = json.loads((index / "sparse_index.json").read_text(encoding="utf-8"))

        self.assertEqual(1, report.figure_count)
        self.assertEqual(1, report.table_count)
        self.assertEqual(2, multimodal["record_count"])
        self.assertEqual("bm25", sparse["algorithm"])
        self.assertIn("figure", result.hits[0].modalities)
        self.assertIn("table", result.hits[0].modalities)
        self.assertIn("communities", community)

    def test_optional_figure_ocr_records_text_without_requiring_image_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "md"
            index = root / "kg"
            asset_dir = source / "fig_assets"
            asset_dir.mkdir(parents=True)
            (asset_dir / "figure.png").write_bytes(b"fake-image-bytes")
            (source / "figures.md").write_text(
                "# Figure OCR paper\n\n"
                "## Results\n\n"
                "![Figure 3 stress plot](fig_assets/figure.png)\n\n"
                "The plotted curve reports tensile stress.\n",
                encoding="utf-8",
                newline="\n",
            )

            with mock.patch.dict("os.environ", {"LLM_KG_FIGURE_OCR": "1"}, clear=False):
                with mock.patch.object(llm_knowledge_graph, "_figure_ocr_text", return_value=("OCR stress axis MPa", "ok:test")):
                    llm_knowledge_graph.build_knowledge_graph(
                        source,
                        index,
                        max_chunk_tokens=100,
                        top_terms_per_chunk=5,
                        embedding_model="none",
                    )
            multimodal = json.loads((index / "multimodal_index.json").read_text(encoding="utf-8"))

        figure_records = [record for record in multimodal["records"] if record["type"] == "figure"]
        self.assertEqual(1, len(figure_records))
        self.assertEqual("ok:test", figure_records[0]["ocr_status"])
        self.assertIn("OCR stress axis MPa", figure_records[0]["ocr_text"])
        self.assertTrue(figure_records[0]["asset_hash"])

    def test_optional_llm_community_summary_uses_configured_backend_when_available(self) -> None:
        terms = {"tensile": 3, "stress": 2}
        counter = llm_knowledge_graph.Counter(terms)
        with mock.patch.dict("os.environ", {"LLM_KG_SUMMARY_BASE_URL": "http://127.0.0.1:9999/v1"}, clear=False):
            with mock.patch.object(llm_knowledge_graph, "_openai_compatible_summary", return_value="LLM summary of tensile stress community."):
                summary = llm_knowledge_graph._maybe_llm_community_summary(
                    "tensile",
                    counter,
                    ["paper.md"],
                    ["paper.md :: Results"],
                    "fallback summary",
                )

        self.assertEqual("openai-compatible", summary["backend"])
        self.assertIn("LLM summary", summary["text"])


if __name__ == "__main__":
    unittest.main()
