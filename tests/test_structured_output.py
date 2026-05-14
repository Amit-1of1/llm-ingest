import tempfile
import unittest
from pathlib import Path

import llm_structured_output


class StructuredOutputTests(unittest.TestCase):
    def test_structure_summary_detects_figures_tables_formulas_and_links(self) -> None:
        text = """# Paper Title

![Figure 1](assets/figure1.png)

> **Figure 1.** Caption text.

| A | B |
| --- | --- |
| 1 | 2 |

$$
E = mc^2
$$

[Source](https://example.com)
"""
        summary = llm_structured_output.build_structure_summary(
            text,
            source_path=Path("paper.pdf"),
            output_path=Path("paper.md"),
        )
        self.assertEqual("Paper Title", summary.title)
        self.assertEqual(1, len(summary.figures))
        self.assertEqual("figure 1", summary.figures[0]["label"])
        self.assertGreaterEqual(len(summary.tables), 2)
        self.assertEqual(1, len(summary.formulas))
        self.assertEqual(1, len(summary.links))

    def test_write_sidecars_creates_quality_and_extraction_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown_path = root / "paper.md"
            text = "# Paper\n\n## Abstract\n\nText.\n"
            markdown_path.write_text(text, encoding="utf-8", newline="\n")
            extraction_path, quality_path = llm_structured_output.write_markdown_sidecars(
                markdown_path,
                Path("paper.pdf"),
                text,
            )
            self.assertTrue(extraction_path.exists())
            self.assertTrue(quality_path.exists())
            self.assertIn('"assertion_count": 0', quality_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
