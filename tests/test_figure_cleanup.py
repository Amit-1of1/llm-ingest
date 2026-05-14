import unittest

import llm_figure_cleanup


class FigureCleanupTests(unittest.TestCase):
    def test_moves_matching_image_to_rich_caption_and_drops_bare_label(self) -> None:
        text = """# Paper

![Figure 2](assets/page_001_00.png)

Some extracted prose that landed between the image and caption.

Figure 2

> **Figure 2.** Mechanical recovery after acid treatment.
"""
        cleaned = llm_figure_cleanup.align_figure_images_with_captions(text)
        self.assertIn("![Figure 2](assets/page_001_00.png)\n\n> **Figure 2.** Mechanical recovery", cleaned)
        self.assertNotIn("\nFigure 2\n\n> **Figure 2", cleaned)
        self.assertIn("Some extracted prose", cleaned)

    def test_unmatched_image_is_preserved(self) -> None:
        text = """# Paper

![Page 009 figure 01](assets/page_009_01.png)

Body text with no usable caption.
"""
        cleaned = llm_figure_cleanup.align_figure_images_with_captions(text)
        self.assertIn("![Page 009 figure 01](assets/page_009_01.png)", cleaned)
        self.assertIn("Body text with no usable caption.", cleaned)

    def test_supplementary_and_fig_abbreviations_normalize_to_same_label(self) -> None:
        text = """![Supplementary Fig. 3](assets/s3.png)

Filler.

> **Supplementary Figure 3.** Extended recovery traces.
"""
        cleaned = llm_figure_cleanup.align_figure_images_with_captions(text)
        self.assertIn("![Supplementary Fig. 3](assets/s3.png)\n\n> **Supplementary Figure 3.**", cleaned)


if __name__ == "__main__":
    unittest.main()
