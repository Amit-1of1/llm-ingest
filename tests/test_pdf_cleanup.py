import unittest
from pathlib import Path

import llm_pdf_cleanup

FIXTURE_DIR = Path(__file__).with_name("fixtures") / "pdf_cleanup"


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class PDFCleanupTests(unittest.TestCase):
    def test_bad_sentence_h1_prefers_title_heading_and_syncs_frontmatter(self) -> None:
        text = fixture_text("bad_title_sentence.md")
        cleaned = llm_pdf_cleanup.normalize_document_structure(
            text,
            source_path=Path("Protein_fibers_with_self-recoverable_mechanical_properties_via_dynamic_imine_che.pdf"),
        )
        self.assertIn('title: "Protein fibers with self-recoverable mechanical properties via dynamic imine chemistry"', cleaned)
        self.assertIn("# Protein fibers with self-recoverable mechanical properties via dynamic imine chemistry", cleaned)
        self.assertNotIn("# Herein, we introduce", cleaned)

    def test_split_title_headings_are_merged_and_removed_from_body(self) -> None:
        text = fixture_text("split_recombinant_title.md")
        cleaned = llm_pdf_cleanup.normalize_document_structure(
            text,
            source_path=Path("Recombinant_Spidroins_Fully_Replicate_Primary_Mechanical_Properties_of_Natural_S.pdf"),
        )
        self.assertIn('title: "Recombinant Spidroins Fully Replicate Primary Mechanical Properties of Natural Spider Silk"', cleaned)
        self.assertIn("# Recombinant Spidroins Fully Replicate Primary Mechanical Properties of Natural Spider Silk", cleaned)
        self.assertNotIn("## 1 **Title:", cleaned)
        self.assertNotIn("## 2 **of Natural", cleaned)

    def test_empty_headings_are_removed_and_duplicate_sections_are_qualified(self) -> None:
        text = """# Example Paper

##

## Methods

One.

## Methods

Two.
"""
        cleaned = llm_pdf_cleanup.normalize_document_structure(text, source_path=Path("Example_Paper.pdf"))
        self.assertNotIn("\n##\n", cleaned)
        self.assertIn("## Methods\n", cleaned)
        self.assertIn("## Methods (continued 2)", cleaned)

    def test_caption_copyright_is_preserved(self) -> None:
        text = """# Bi-terminal fusion of intrinsically-disordered mussel foot protein fragments boosts mechanical strength for protein fibers

Data reproduced from previous publication (reproduced with permission[10], Copyright 2021 American Chemical Society) serve as a comparison.
"""
        cleaned = llm_pdf_cleanup.normalize_document_structure(text, source_path=Path("Bi-terminal_fusion.pdf"))
        self.assertIn("Copyright 2021 American Chemical Society", cleaned)

    def test_packed_references_are_split(self) -> None:
        text = fixture_text("packed_references.md")
        cleaned = llm_pdf_cleanup.normalize_document_structure(text, source_path=Path("Example.pdf"))
        self.assertIn("1. Alpha, A. First article.", cleaned)
        self.assertIn("\n2. Beta, B. Second article.", cleaned)

    def test_reference_continuations_are_joined_and_doi_spacing_is_cleaned(self) -> None:
        text = """# Example

## References

1. Alpha, A. Domain common to dragline proteins.

Biomacromolecules 7, 3120-3124 (2006).

2. Beta, B. Second article. doi: doi: 10. 1038/example

## Methods

Body.
"""
        cleaned = llm_pdf_cleanup.normalize_document_structure(text, source_path=Path("Example.pdf"))
        self.assertIn("1. Alpha, A. Domain common to dragline proteins. Biomacromolecules 7, 3120-3124 (2006).", cleaned)
        self.assertIn("2. Beta, B. Second article. doi: 10.1038/example", cleaned)
        self.assertIn("## Methods", cleaned)

    def test_missing_formula_after_equation_intro_is_marked(self) -> None:
        text = """# Example

The modulus was calculated using following equation:

## Results

More text.
"""
        cleaned = llm_pdf_cleanup.normalize_document_structure(text, source_path=Path("Example.pdf"))
        self.assertIn("[Formula omitted by PDF extraction; review source PDF.]", cleaned)

    def test_real_empty_heading_fixture_removes_blank_headings(self) -> None:
        cleaned = llm_pdf_cleanup.normalize_document_structure(
            fixture_text("empty_headings.md"),
            source_path=Path("The_hidden_link_between_structure_and_properties.pdf"),
        )
        self.assertNotRegex(cleaned, r"(?m)^##\s*$")
        self.assertIn("## Results", cleaned)


if __name__ == "__main__":
    unittest.main()
