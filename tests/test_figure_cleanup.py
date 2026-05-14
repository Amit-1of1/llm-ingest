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

    def test_groups_multipanel_images_with_base_caption(self) -> None:
        text = """# Paper

![Figure 2a](assets/fig2a.png)

![Figure 2b](assets/fig2b.png)

![Figure 2](assets/fig2-full.png)

Intervening extracted prose.

Figure 2

> **Figure 2.** Multi-panel recovery across treatments.
"""
        groups = llm_figure_cleanup.recover_caption_groups(text)
        self.assertEqual(1, len(groups))
        self.assertEqual("figure 2", groups[0].group_label)
        self.assertEqual(["figure 2a", "figure 2b", "figure 2"], [image.label for image in groups[0].images])

        cleaned = llm_figure_cleanup.align_figure_images_with_captions(text)
        self.assertIn(
            "![Figure 2a](assets/fig2a.png)\n"
            "![Figure 2b](assets/fig2b.png)\n"
            "![Figure 2](assets/fig2-full.png)\n\n"
            "> **Figure 2.** Multi-panel recovery",
            cleaned,
        )
        self.assertNotIn("\nFigure 2\n\n> **Figure 2", cleaned)
        self.assertIn("Intervening extracted prose.", cleaned)

    def test_groups_supplementary_panels_with_s_number_caption(self) -> None:
        text = """![Supplementary Fig. S1A](assets/s1a.png)

![Supplementary Figure S1B](assets/s1b.png)

Methods prose.

> **Supplementary Figure S1.** Replicate traces and controls.
"""
        cleaned = llm_figure_cleanup.align_figure_images_with_captions(text)
        self.assertIn(
            "![Supplementary Fig. S1A](assets/s1a.png)\n"
            "![Supplementary Figure S1B](assets/s1b.png)\n\n"
            "> **Supplementary Figure S1.** Replicate traces",
            cleaned,
        )

    def test_preserves_unmatched_panel_asset_when_other_caption_matches(self) -> None:
        text = """![Figure 7a](assets/fig7a.png)

![Figure 8](assets/fig8.png)

Bridge text.

> **Figure 8.** Matched caption.
"""
        cleaned = llm_figure_cleanup.align_figure_images_with_captions(text)
        self.assertIn("![Figure 7a](assets/fig7a.png)", cleaned)
        self.assertIn("![Figure 8](assets/fig8.png)\n\n> **Figure 8.** Matched caption.", cleaned)


if __name__ == "__main__":
    unittest.main()
