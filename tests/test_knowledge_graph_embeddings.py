import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
