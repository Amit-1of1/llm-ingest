# LLM Ingest

LLM Ingest is a local Windows-friendly desktop and CLI tool for turning research PDFs and document folders into cleaner Markdown, then building a lightweight knowledge graph over the generated notes for fast RAG-style querying.

The app is built for a trusted local researcher processing untrusted PDFs. It keeps defaults local/private, avoids committing downloaded papers or generated Markdown, and includes audit tooling for catching known PDF extraction regressions.

## Features

- Convert PDF, DOCX, PPTX, HTML, CSV, TXT, and Markdown files to LLM-ready Markdown.
- Extract PDF figures/assets and align them with nearby captions where possible.
- Clean common scientific PDF artifacts: broken titles, duplicate metadata, packed references, running headers, mojibake, hyphenated line breaks, formula/unit fragments, and empty headings.
- Run backend diagnostics and PDF audit jobs from the desktop app.
- Build a local knowledge graph over generated Markdown.
- Query with lexical, vector, or hybrid graph + vector retrieval.
- Use local hash or TF-IDF weighted hash embeddings without sending text to a remote service.
- Run PDF extraction in a hardened subprocess with file, page, asset, and timeout limits.

## Quick Start

Install Python 3.12 or newer, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Launch the desktop app:

```powershell
.\launch_llm_ingest_app.bat
```

Or run the CLI:

```powershell
python llm_ingest.py downloaded --out-dir llm_ready
```

## Recommended Workflow

1. Put PDFs or documents in `downloaded/`.
2. Launch `launch_llm_ingest_app.bat`.
3. Use `Workflow` to select input and output folders.
4. Use `PDF Settings` to choose `auto`, `custom`, `pymupdf4llm`, or `marker`.
5. Run ingest to create Markdown in `llm_ready/`.
6. Use `Knowledge Graph` to build an index from `llm_ready/`.
7. Query the graph and open `graph_context.md` or `last_query.md` from the app.

Generated papers, graph indexes, audit outputs, and downloaded PDFs are ignored by git by default.

## CLI Examples

Convert a folder:

```powershell
python llm_ingest.py downloaded --out-dir llm_ready
```

Convert one PDF:

```powershell
python llm_ingest.py path\to\paper.pdf --output llm_ready\paper.md
```

Build a knowledge graph:

```powershell
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model hash
```

Use the stronger local TF-IDF weighted embedding backend:

```powershell
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model tfidf-hash
```

Query the graph:

```powershell
python llm_ingest.py graph query "acid treatment imine bonds mechanical recovery" --index-dir _knowledge_graph --mode hybrid --limit 8
```

Run Markdown regression assertions:

```powershell
python llm_audit_assertions.py llm_ready
```

Create a before/after quality report:

```powershell
python llm_quality_report.py --before old_llm_ready --after llm_ready --output _audit_reports\quality_compare.md
```

## Audit Workflow

The repo includes `audit_corpus_manifest.json`, which tracks public/open sample PDFs by URL and SHA-256. The PDFs themselves are not committed.

Run an audit:

```powershell
python llm_ingest.py audit --manifest audit_corpus_manifest.json --cache-dir _audit_corpus_cache --report-dir _audit_reports --backends auto,custom:off,pymupdf4llm
```

Add `--download-missing` to populate the local cache. Audit outputs include:

- `audit_report.json`
- `audit_summary.md`
- `audit_assertions.md`
- rendered Markdown outputs under `renders/`

## Optional Marker Backend

Marker is treated as optional because it is heavier and may require a sidecar Python environment and model weights. The default app remains usable with PyMuPDF and PyMuPDF4LLM.

If you configure Marker, prefer a dedicated sidecar interpreter and keep hardened mode enabled.

## Privacy and Safety

Do not commit or share generated folders unless you intentionally want to publish their contents:

- `downloaded/`
- `llm_ready/`
- `_knowledge_graph/`
- `_audit_reports/`
- `_audit_corpus_cache/`
- `*_assets/`

Graph indexes and RAG packs contain extracted document text. Treat them as sensitive research artifacts.

## Tests

Run:

```powershell
python -m unittest discover -s tests
python -m py_compile llm_ingest.py llm_ingest_app.pyw llm_knowledge_graph.py llm_pdf_cleanup.py llm_figure_cleanup.py llm_audit_assertions.py llm_quality_report.py
```

## Project Docs

See `APP_TECHNICAL_WORKFLOW.md` for a deeper architecture and workflow explanation.
