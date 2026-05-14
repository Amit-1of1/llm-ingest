# Implementation Progress

This log tracks the remaining app goals as they are implemented. Each completed item records what changed, where it landed, and how it was checked.

## Completed

### Optional PDF Backend Adapters

- Added runnable adapter implementations for Docling and Unstructured when their optional packages are installed.
- Added a safer MinerU adapter that only reports runnable when both the Python package and a supported CLI executable are available.
- Kept optional backend imports lazy so importing the app does not load heavy packages.
- Covered adapter behavior with focused unit tests in `tests/test_backend_adapters.py`.

### Richer Local Embeddings

- Added `sentence-transformers` as an optional graph embedding backend.
- Kept `hash`, `tfidf-hash`, and `none` behavior backward-compatible.
- Added `LLM_KG_SENTENCE_TRANSFORMER_MODEL` so users can select a local model without changing code.
- Covered the optional backend with mocked unit tests in `tests/test_knowledge_graph_embeddings.py`.

### Reference-Section Normalization

- Added a reference-only cleanup pass that joins likely continuation lines back into the current numbered citation.
- Split packed numbered references that appear on one line.
- Cleaned duplicated `doi:` prefixes and broken DOI spacing such as `10. 1038/...`.
- Covered the behavior in `tests/test_pdf_cleanup.py` while preserving existing document-structure tests.

### Missing Formula Visibility

- Added detection for prose that introduces an equation or formula and is followed by an empty extraction gap.
- Inserted an explicit review marker instead of letting the Markdown silently imply the formula was present.
- Covered the behavior in `tests/test_pdf_cleanup.py`.

## In Progress

- Larger real-PDF benchmark corpus and scored quality reports.
- Final UI polish around backend selection, benchmark output, and diagnostics.

## Not Started Yet

- Dedicated math/formula reconstruction for equations that only exist as images in the source PDF.
- Dedicated dense-table reconstruction beyond the current cleanup and backend routing.
- End-to-end re-run on the full local paper corpus after the next cleanup pass.
