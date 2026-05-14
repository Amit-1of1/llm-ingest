import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import llm_knowledge_graph


class KnowledgeGraphEmbeddingTests(unittest.TestCase):
    def test_tfidf_hash_backend_builds_and_queries_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "md"
            index = root / "kg"
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
            report = llm_knowledge_graph.build_knowledge_graph(
                source,
                index,
                max_chunk_tokens=100,
                top_terms_per_chunk=3,
                embedding_model="tfidf-hash",
                embedding_dimensions=64,
            )
            result = llm_knowledge_graph.query_knowledge_graph(index, "imine bond mechanical recovery", retrieval_mode="vector", limit=1)

        self.assertEqual("tfidf-hash", report.embedding_model)
        self.assertEqual(2, report.embedding_count)
        self.assertEqual(1, len(result.hits))
        self.assertIn("fibers.md", result.hits[0].path)

    def test_sentence_transformers_backend_is_optional_and_queryable(self) -> None:
        class FakeSentenceTransformer:
            def __init__(self, model_name: str) -> None:
                self.model_name = model_name

            def encode(self, texts: list[str], **kwargs: object) -> list[list[float]]:
                vectors = []
                for text in texts:
                    lower = text.lower()
                    vectors.append([1.0, 0.0, 0.0] if "imine" in lower else [0.0, 1.0, 0.0])
                return vectors

        fake_module = types.ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = FakeSentenceTransformer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "md"
            index = root / "kg"
            source.mkdir()
            (source / "fibers.md").write_text(
                "# Dynamic imine protein fibers\n\nRecovery via imine bonds.\n",
                encoding="utf-8",
                newline="\n",
            )
            (source / "tables.md").write_text(
                "# Metrology tables\n\nWeights and calibration.\n",
                encoding="utf-8",
                newline="\n",
            )
            with mock.patch.dict(sys.modules, {"sentence_transformers": fake_module}):
                report = llm_knowledge_graph.build_knowledge_graph(
                    source,
                    index,
                    max_chunk_tokens=100,
                    top_terms_per_chunk=3,
                    embedding_model="sentence-transformers",
                    embedding_dimensions=32,
                )
                result = llm_knowledge_graph.query_knowledge_graph(index, "imine recovery", retrieval_mode="vector", limit=1)

        self.assertEqual("sentence-transformers", report.embedding_model)
        self.assertEqual(2, report.embedding_count)
        self.assertIn("fibers.md", result.hits[0].path)

    def test_sentence_transformers_missing_dependency_has_clear_error(self) -> None:
        with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
            with self.assertRaisesRegex(RuntimeError, "pip install sentence-transformers"):
                llm_knowledge_graph._sentence_transformer_embedding("query", 3)


if __name__ == "__main__":
    unittest.main()
