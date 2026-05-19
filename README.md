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
- Optionally write `.extraction.json` and `.quality.json` sidecars beside generated Markdown.
- Benchmark Markdown quality and graph retrieval utility offline.

## Quick Start

On a new Windows computer, clone or unzip this repo, then double-click:

```powershell
install_llm_ingest.bat
```

That creates a local `.venv`, downloads the core Python dependencies, verifies imports, and lets `launch_llm_ingest_app.bat` run from the local environment.

Heavier optional installs:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_llm_ingest.ps1 -Optional
powershell -ExecutionPolicy Bypass -File .\install_llm_ingest.ps1 -All -InstallTesseract
```

Use `-InstallPython` if Python is missing and you want the installer to try `winget install Python.Python.3.12`.

To build a Python-free Windows executable and self-contained installer package for other users:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows_release.ps1 -Clean
```

The build creates:

- `dist\LLMIngest\LLMIngest.exe`
- `dist\LLMIngest\LLMIngestWorker.exe`
- `dist\LLMIngest\LLMIngestAPI.exe`
- `release\LLMIngest-Windows\Install-LLMIngest.bat`
- `release\LLMIngest-Windows.zip`
- `release\LLMIngestSetup.exe` when Inno Setup 6 is installed

Best distribution option: send `release\LLMIngestSetup.exe`.

If Inno Setup is not installed, the zip package is still usable: users can unzip `LLMIngest-Windows.zip` and double-click `Install-LLMIngest.bat`. The installed app runs from `LLMIngest.exe` and does not require Python on the target computer.

To let the builder install Inno Setup with winget:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows_release.ps1 -Clean -InstallInno
```

Manual setup:

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

Write structured sidecars while converting:

```powershell
python llm_ingest.py downloaded --out-dir llm_ready --write-sidecars
```

Query the graph:

```powershell
python llm_ingest.py graph query "acid treatment imine bonds mechanical recovery" --index-dir _knowledge_graph --mode hybrid --limit 8
```

Graph retrieval uses a local hybrid stack:

- BM25-style sparse retrieval for exact scientific terms, units, citations, and figure labels.
- Dense/vector retrieval when embeddings are enabled.
- Graph expansion over document, heading, term, citation, figure, table, and community nodes.
- Reciprocal rank fusion plus a lightweight reranker.
- Corrective evidence grading with answerability labels and extraction-quality warnings.

Graph builds also write:

- `sparse_index.json`
- `multimodal_index.json`
- `figure_embeddings.jsonl` when optional image embeddings are enabled
- `community_summaries.json`
- `rag_pack.json` after the latest query
- `last_query.md` after the latest query

Cheap optional figure OCR:

```powershell
set LLM_KG_FIGURE_OCR=1
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model hash
```

This uses `tesseract` from PATH when available, otherwise it tries optional `pytesseract` plus `pillow`. OCR text is cached into `multimodal_index.json` with asset hashes.

Cheap optional image embeddings:

```powershell
set LLM_KG_IMAGE_EMBEDDINGS=1
set LLM_KG_IMAGE_EMBEDDING_MODEL=clip-ViT-B-32
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model hash
```

This writes `figure_embeddings.jsonl` when `sentence-transformers` and `pillow` are installed. It is off by default so normal graph builds do not download models.

Optional OpenAI-compatible local summary endpoint:

```powershell
set LLM_KG_SUMMARY_BASE_URL=http://127.0.0.1:11434/v1
set LLM_KG_SUMMARY_MODEL=local-summary-model
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model hash
```

If the endpoint is missing or fails, the app falls back to deterministic local community summaries.

## Local API for Agent Tools

The installed package includes a local HTTP API executable for tools that can call localhost services, including Claude, Codex, and other LLM agent runners.

Start it from the Start Menu with **LLM Ingest API Server**, or run:

```powershell
%LOCALAPPDATA%\Programs\LLMIngest\LLMIngestAPI.exe --port 8765
```

The API binds to `127.0.0.1` by default and exposes:

- `GET /health`
- `GET /openapi.json`
- `POST /convert`
- `POST /graph/build`
- `POST /graph/query`

Optional local auth:

```powershell
set LLM_INGEST_API_TOKEN=choose-a-local-token
%LOCALAPPDATA%\Programs\LLMIngest\LLMIngestAPI.exe --port 8765
```

Then send `Authorization: Bearer choose-a-local-token` or `X-LLM-Ingest-Token: choose-a-local-token`.

Example graph query:

```powershell
curl -X POST http://127.0.0.1:8765/graph/query `
  -H "Content-Type: application/json" `
  -d "{\"index_dir\":\"C:\\Users\\User\\Desktop\\Research\\papers\\_knowledge_graph\",\"query\":\"acid treatment imine bonds mechanical recovery\",\"mode\":\"hybrid\",\"limit\":8}"
```

Example conversion:

```powershell
curl -X POST http://127.0.0.1:8765/convert `
  -H "Content-Type: application/json" `
  -d "{\"input_path\":\"C:\\Research\\papers\\downloaded\",\"output_dir\":\"C:\\Research\\papers\\llm_ready\",\"pdf_backend\":\"auto\",\"ocr_mode\":\"auto\"}"
```

Run Markdown regression assertions:

```powershell
python llm_audit_assertions.py llm_ready
```

Create a before/after quality report:

```powershell
python llm_quality_report.py --before old_llm_ready --after llm_ready --output _audit_reports\quality_compare.md
```

Run an offline benchmark:

```powershell
python llm_benchmark.py quality llm_ready --output-dir _benchmark_runs\quality
```

Run a retrieval benchmark against an existing graph:

```powershell
python llm_benchmark.py retrieval --questions benchmarks\questions.json --index-dir _knowledge_graph --output-dir _benchmark_runs\retrieval
```

## Audit Workflow

The repo includes `config/audit_corpus_manifest.json`, which tracks public/open sample PDFs by URL and SHA-256. The PDFs themselves are not committed.

Run an audit:

```powershell
python llm_ingest.py audit --manifest config/audit_corpus_manifest.json --cache-dir _audit_corpus_cache --report-dir _audit_reports --backends auto,custom:off,pymupdf4llm
```

Add `--download-missing` to populate the local cache. Audit outputs include:

- `audit_report.json`
- `audit_summary.md`
- `audit_assertions.md`
- rendered Markdown outputs under `renders/`

## Optional Marker Backend

Marker, Docling, MinerU, and Unstructured are treated as optional because they are heavier and may require sidecar environments or model/data downloads. The default app remains usable with PyMuPDF and PyMuPDF4LLM.

If you configure Marker, prefer a dedicated sidecar interpreter and keep hardened mode enabled.

Optional install files:

- `requirements/docling.txt`
- `requirements/mineru.txt`
- `requirements/unstructured.txt`
- `requirements/optional.txt` for Marker and richer local embeddings
- `requirements/optional.txt` also includes `pillow` and `pytesseract` for optional figure OCR/image workflows

Docling and Unstructured have first-class adapter paths when their optional packages are installed. MinerU is detected through its Python package plus a supported local CLI executable (`magic-pdf` or `mineru`) because its install layouts vary more across environments.

## Graph Embeddings

The knowledge graph stays local by default. Supported embedding modes are:

- `hash`: dependency-free local vectors
- `tfidf-hash`: stronger dependency-free local vectors
- `sentence-transformers`: optional richer local embeddings
- `none`: graph and lexical retrieval only

Example:

```powershell
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model sentence-transformers
```

Set `LLM_KG_SENTENCE_TRANSFORMER_MODEL` to choose a local Sentence Transformers model. The default is `sentence-transformers/all-MiniLM-L6-v2`.

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
python -m py_compile llm_ingest.py llm_ingest_app.pyw llm_knowledge_graph.py llm_pdf_cleanup.py llm_figure_cleanup.py llm_audit_assertions.py llm_quality_report.py llm_benchmark.py llm_structured_output.py llm_local_api.py llm_ingest_api_entry.py pdf_worker_runner.py marker_sidecar_runner.py
```

## Project Docs

See `docs/APP_TECHNICAL_WORKFLOW.md` for a deeper architecture and workflow explanation.
