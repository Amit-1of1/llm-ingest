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

### Windows Installer Bootstrap

- Added `install_llm_ingest.ps1` to create a local `.venv`, download core requirements, optionally install heavier backends, and verify app imports.
- Added `install_llm_ingest.bat` as a double-click wrapper for Windows users.
- Updated `launch_llm_ingest_app.bat` to prefer the local `.venv` before falling back to system Python.
- Documented installer variants in `README.md`.

### Python-Free Windows Executable Packaging

- Added `packaging/LLMIngest.spec` for PyInstaller one-folder executable builds.
- Added `scripts/build_windows_release.ps1` to create `dist\LLMIngest\LLMIngest.exe`, package a self-contained installer folder, and zip it for sharing.
- Added `packaging/windows/Install-LLMIngest.ps1` and `.bat` so end users can install the built executable without Python.
- Added a frozen `--pdf-worker` path so hardened PDF extraction still works from the packaged executable.
- Added an Inno Setup script, `packaging/windows/LLMIngest.iss`, so the release builder can produce `release\LLMIngestSetup.exe`.
- Updated the builder with `-InstallInno` and `-SkipInno` switches for installer-exe builds.

### Packaged Runtime Crash Fix

- Fixed packaged builds so manifest pipeline signatures do not depend on source `.py` files existing beside the executable.
- Added clean rejection for zero-byte inputs such as empty PDFs.
- Updated app folder-batch conversion so one bad file is skipped with a reason instead of stopping the whole run.
- Rebuilt `release\LLMIngestSetup.exe` with the fixes.

### Local Agent API

- Added `llm_local_api.py`, a localhost-only JSON API for conversion and knowledge-graph workflows.
- Added `LLMIngestAPI.exe` to the PyInstaller bundle and installer Start Menu shortcuts.
- Exposed `/health`, `/openapi.json`, `/convert`, `/graph/build`, and `/graph/query` for Claude/Codex-style local agent integrations.
- Added optional bearer-token protection via `LLM_INGEST_API_TOKEN`, `--token`, `Authorization: Bearer ...`, or `X-LLM-Ingest-Token`.
- Covered server health, auth rejection, endpoint schema, and remote-bind protection in `tests/test_local_api.py`.

### Hybrid GraphRAG Retrieval Upgrade

- Replaced simple weighted retrieval with a stronger local fusion stack: BM25-style sparse scoring, vector scoring, graph expansion, reciprocal rank fusion, and heuristic reranking.
- Added corrective evidence grading for query hits, including answerability labels, extraction-quality warnings, prompt-injection warnings, and machine-readable grading fields in `rag_pack.json`.
- Added figure/table-aware graph records so Markdown images and tables become chunk-linked `figure` and `table` nodes.
- Added `sparse_index.json`, `multimodal_index.json`, and `community_summaries.json` artifacts during graph builds.
- Extended query packs with BM25/RRF/rerank breakdowns, modalities, evidence grades, and answerability summaries.
- Covered the new behavior in `tests/test_rag_architecture_upgrades.py`.

### Optional Multimodal and Summary Enhancements

- Added opt-in local figure OCR via `LLM_KG_FIGURE_OCR=1`, using Tesseract CLI when available or optional `pytesseract`/`pillow`.
- Added figure asset hashes, OCR status, OCR text, and richer retrieval text to `multimodal_index.json`.
- Added opt-in local CLIP-style image embeddings via `LLM_KG_IMAGE_EMBEDDINGS=1`, writing `figure_embeddings.jsonl` when `sentence-transformers` and `pillow` are available.
- Added optional OpenAI-compatible local LLM community summaries via `LLM_KG_SUMMARY_BASE_URL` and `LLM_KG_SUMMARY_MODEL`, with deterministic local fallback.
- Added cache keys for community summaries so future runs can avoid regenerating unchanged summary inputs.
- Expanded optional requirements with `pillow` and `pytesseract`.

## In Progress

- Larger real-PDF benchmark corpus and scored quality reports.
- Final UI polish around backend selection, benchmark output, and diagnostics.

## Not Started Yet

- Dedicated math/formula reconstruction for equations that only exist as images in the source PDF.
- Dedicated dense-table reconstruction beyond the current cleanup and backend routing.
- End-to-end re-run on the full local paper corpus after the next cleanup pass.
