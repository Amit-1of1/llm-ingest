# LLM Ingest App: Technical Architecture and Workflow

This document explains the local PDF/document ingest app, its CLI workflows, the PDF cleanup pipeline, audit system, and knowledge graph/RAG functionality.

## Purpose

The app converts local research papers and related documents into Markdown that is easier for LLMs to read, chunk, retrieve, and cite. It is designed for a trusted local desktop user who may process untrusted PDFs and Markdown.

Core capabilities:

- Convert PDFs, DOCX, PPTX, HTML, CSV, TXT, and Markdown into LLM-ready Markdown.
- Extract and group PDF figures/assets where possible.
- Repair common PDF extraction artifacts, titles, references, section headings, and metadata.
- Run audit jobs across local and public sample PDFs.
- Build a queryable knowledge graph over generated Markdown.
- Query that graph with lexical, vector, or hybrid RAG retrieval.
- Run PDF extraction in a hardened subprocess with file/page/time limits.

## Main Files

| File | Role |
| --- | --- |
| `llm_ingest.py` | Main conversion engine, CLI, PDF backend routing, audit workflow, non-PDF extraction, manifest caching, security controls. |
| `llm_pdf_cleanup.py` | Document-level Markdown cleanup: titles, frontmatter, boilerplate, headings, references, dehyphenation. |
| `llm_ingest_app.pyw` | Tkinter desktop GUI for workflow conversion, PDF settings, diagnostics, audit, activity log, and knowledge graph operations. |
| `llm_knowledge_graph.py` | Knowledge graph and RAG engine for generated Markdown. |
| `llm_backends/` | Optional backend adapter registry for PyMuPDF4LLM, Docling, Marker, MinerU, and Unstructured. |
| `llm_benchmark.py` | Offline benchmark harness for Markdown quality and graph retrieval utility. |
| `llm_structured_output.py` | Optional `.extraction.json` and `.quality.json` sidecars for generated Markdown. |
| `pdf_worker_runner.py` | Isolated subprocess runner for hardened PDF extraction. |
| `marker_sidecar_runner.py` | Sidecar runner for Marker PDF extraction. |
| `launch_llm_ingest_app.bat` | Windows launcher for the GUI. |
| `audit_corpus_manifest.json` | Repo-tracked audit corpus manifest; binaries are cached locally, not committed. |
| `tests/test_pdf_cleanup.py` | Focused regression tests for document-level cleanup. |

## Desktop App Structure

The GUI lives in `llm_ingest_app.pyw`.

The main class is `IngestApp`. It owns:

- Tk root/window setup.
- Sidebar navigation.
- Workflow form.
- PDF settings.
- Diagnostics/audit views.
- Knowledge graph builder/query view.
- Activity log.
- Background worker threads.

Navigation pages:

- `Workflow`: choose input/output and run ingest.
- `PDF Settings`: choose backend, OCR mode, limits, hardened mode, table strategy.
- `Diagnostics`: backend health, audit corpus, audit action/results.
- `Knowledge Graph`: build graph from Markdown and query it.
- `Activity`: log output and progress.

Long-running work never runs directly on the UI thread. The app starts worker threads for:

- Conversion: `_run_worker()` -> `_run_conversion()` -> `llm_ingest.convert_file()`.
- Audit: `_run_audit_worker()` -> `llm_ingest.run_audit()`.
- Graph build: `_run_kg_build_worker()` -> `llm_knowledge_graph.build_knowledge_graph()`.
- Graph query: `_run_kg_query_worker()` -> `llm_knowledge_graph.query_knowledge_graph()`.

Worker output is sent through a queue and displayed in the app log/status panels.

## CLI Entry Points

The CLI entry is `llm_ingest.py`.

### Convert

```powershell
python llm_ingest.py downloaded --out-dir llm_ready
```

Single file:

```powershell
python llm_ingest.py downloaded\paper.pdf --output llm_ready\paper.md
```

### Audit

```powershell
python llm_ingest.py audit --manifest audit_corpus_manifest.json --cache-dir _audit_corpus_cache --report-dir _audit_reports --download-missing
```

### Graph Build

```powershell
python llm_ingest.py graph build --source-dir llm_ready --index-dir _knowledge_graph --embedding-model hash
```

### Graph Query

```powershell
python llm_ingest.py graph query "acid treatment imine bonds mechanical recovery" --index-dir _knowledge_graph --mode hybrid --limit 8
```

### Structured Sidecars

```powershell
python llm_ingest.py downloaded --out-dir llm_ready --write-sidecars
```

This writes `paper.extraction.json` and `paper.quality.json` beside generated Markdown.

### Benchmarks

```powershell
python llm_benchmark.py quality llm_ready --output-dir _benchmark_runs/quality
python llm_benchmark.py retrieval --questions benchmarks/questions.json --index-dir _knowledge_graph --output-dir _benchmark_runs/retrieval
```

## Conversion Workflow

High-level flow:

```text
Input path
  -> list supported files
  -> build output targets
  -> convert_file()
  -> convert_file_with_details()
  -> extractor by extension
  -> PDF normalization / non-PDF extraction
  -> optional chunking
  -> atomic Markdown write
  -> manifest cache update
```

Important functions:

- `list_supported_files()`: discovers supported input files.
- `build_batch_targets()`: maps inputs to output paths.
- `convert_file_with_details()`: central conversion coordinator.
- `convert_file()`: small wrapper used by CLI and GUI.
- `_is_already_processed()`: skips unchanged files using `.llm_ingest_manifest.json`.
- `safe_atomic_write_text()`: writes with LF line endings via temp file replace.

Supported extensions:

- `.pdf`
- `.docx`
- `.pptx`
- `.html`, `.htm`
- `.csv`
- `.txt`
- `.md`

## PDF Backend Routing

PDF conversion starts at `extract_pdf()`.

If hardened mode is enabled, it runs through `pdf_worker_runner.py`; otherwise it runs in-process through `_extract_pdf_direct()`.

Backend planning is handled by `inspect_pdf_backend_plan()`.

Backends:

| Backend | Purpose |
| --- | --- |
| `custom` | PyMuPDF-based extractor with local figure/table/reference handling. |
| `pymupdf4llm` | Uses PyMuPDF4LLM, then post-processes Markdown and injects assets. |
| `marker` | Uses Marker through a sidecar Python runtime. |
| `auto` | Chooses and falls back based on runtime health and PDF traits. |

The planner distinguishes:

- `importable`: package can be imported.
- `runnable`: backend can actually run with current settings.
- `selected`: first runnable backend in route order.

Examples:

- `custom` with OCR enabled is not runnable if tessdata is unresolved.
- `marker` is not runnable if sidecar interpreter or model weights are unavailable.
- `auto` can prefer `custom` with OCR off for born-digital PDFs and fall back to `pymupdf4llm`.

## Hardened PDF Mode

Hardened mode is enabled by default in the GUI.

Security settings are represented by `SecurityLimits`:

- Max input file MB.
- Max PDF pages.
- Max extracted assets.
- Max audit download MB.
- Backend timeout seconds.
- Hardened mode on/off.
- Privacy mode.
- External Marker interpreter allowance.

In hardened mode:

```text
main process
  -> _extract_pdf_in_worker()
  -> launches pdf_worker_runner.py
  -> worker validates file/page limits
  -> worker runs extraction
  -> worker writes temp Markdown
  -> parent reads result or kills on timeout
```

This protects the GUI/main process from parser hangs and native PDF crashes.

## PDF Cleanup Pipeline

PDF cleanup is split into two layers.

### 1. Line/Math/Prose Cleanup in `llm_ingest.py`

`_normalize_pdf_markdown_math()` handles line-level and scientific text repairs:

- Math/unit normalization.
- Citation cleanup.
- Unicode/mojibake fixes.
- Table cleanup.
- Known formula/unit artifacts.
- Figure/caption alignment.

### 2. Document Structure Cleanup in `llm_pdf_cleanup.py`

`normalize_document_structure()` handles document-level Markdown structure:

- H1/title repair.
- YAML frontmatter creation and synchronization.
- Bad title rejection, such as abstract sentence fragments or author lines.
- Split title heading merge.
- Publisher/journal/cover-sheet boilerplate removal.
- Empty heading removal.
- Repeated section heading qualification.
- Packed reference splitting.
- Leading duplicate title/author line removal.
- CRLF -> LF normalization.
- Common PDF dehyphenation.

Examples fixed by this layer:

- H1 is filename slug instead of title.
- H1 is journal name.
- H1 is a sentence from the abstract.
- Real title appears as an H2.
- Split title appears across two H2 headings.
- Empty `##` headings.
- References packed into one massive line.

Focused tests live in `tests/test_pdf_cleanup.py`.

Run:

```powershell
python -m unittest discover -s tests
```

## Figure and Asset Handling

Figure extraction is primarily handled in `llm_ingest.py`.

Key responsibilities:

- Detect image blocks and drawing candidates.
- Expand/clamp figure bounding boxes.
- Merge nearby multi-panel figure regions.
- Find nearby or continuation captions.
- Generate Markdown image links.
- Keep asset counts under configured limits.

Assets are written beside Markdown using a folder like:

```text
paper_assets/
  page_002_figure_01.png
  page_007_figure_01.png
```

Known limitation: asset placement is improved but still not a full semantic layout engine. Dense multi-panel pages and publisher-specific figure layouts may still require audit review.

## Non-PDF Extraction

Non-PDF extractors are simpler and are selected by extension:

- `extract_docx()`
- `extract_pptx()`
- `extract_html()`
- `extract_csv()`
- `extract_txt()`

They output Markdown-like text, then normal chunking/writing applies.

## Chunking

Chunking is optional during conversion:

```powershell
python llm_ingest.py paper.pdf --chunk 2000
```

If chunking is enabled:

- Frontmatter is preserved.
- Markdown blocks are grouped until the token limit is reached.
- Oversized blocks/lines are split.
- Files are written as `paper_chunk001.md`, `paper_chunk002.md`, etc.

For graph/RAG, the knowledge graph has its own chunking pipeline, so conversion chunking is usually not required.

## Audit Workflow

Audit mode is designed to reveal quality and backend regressions.

Inputs:

- Repo-tracked manifest: `audit_corpus_manifest.json`.
- Local cache: `_audit_corpus_cache/`.
- Local baseline folders, usually `downloaded/`.
- Backend matrix, for example `auto,custom:off,pymupdf4llm,marker`.

Outputs:

- `_audit_reports/.../audit_report.json`
- `_audit_reports/.../audit_summary.md`
- `_audit_reports/.../audit_assertions.md`
- Rendered Markdown outputs per file/backend.
- Issue counts per result.

Audit checks include things like:

- Missing or generic titles.
- Empty headings.
- Broken references.
- Artifact strings.
- Backend failures/fallbacks.
- Asset counts.
- Token counts.

Standalone regression assertions are also available:

```powershell
python llm_audit_assertions.py llm_ready
```

This command exits non-zero when known Markdown regressions are found, including slug H1 titles, empty headings, leaked running headers, placeholder affiliations, fused reference lines, and CRLF line endings.

Audit runs also include these assertions in `issue_counts` as `assertion_*` entries and write detailed findings to `audit_assertions.md`.

Downloads are hardened:

- HTTPS only by default.
- Size cap.
- Stream to partial temp file.
- SHA-256 verification when available.
- No arbitrary `file://` manifest reads.

## Knowledge Graph and RAG Workflow

The graph engine lives in `llm_knowledge_graph.py`.

Build flow:

```text
Markdown source folder
  -> parse frontmatter
  -> determine document titles
  -> chunk by headings/token budget
  -> extract terms/citations/links
  -> create nodes and edges
  -> add document similarity edges
  -> add communities
  -> write graph index
```

Main build function:

- `build_knowledge_graph()`

Main query function:

- `query_knowledge_graph()`

Graph artifacts:

```text
_knowledge_graph/
  graph.json
  chunks.jsonl
  embeddings.jsonl
  index_manifest.json
  graph_context.md
  last_query.md
  rag_pack.json
```

Node types include:

- `document`
- `chunk`
- `heading`
- `term`
- `citation`
- `external_link`
- `community`

Edge types include:

- `contains`
- `under_heading`
- `mentions`
- `cites`
- `links_to`
- `similar_to`
- `member_of`

Retrieval modes:

| Mode | Behavior |
| --- | --- |
| `lexical` | Keyword/BM25-like scoring. |
| `vector` | Local hash embedding scoring only. |
| `hybrid` | Combines lexical, vector, and graph-neighbor boosts. |

Embedding backends:

| Backend | Behavior |
| --- | --- |
| `hash` | Default local/private feature hashing. |
| `tfidf-hash` | Local TF-IDF weighted feature hashing for stronger corpus-aware vector ranking. |
| `none` | Disables vector artifacts and uses lexical/graph ranking only. |

RAG safety:

- Retrieved text is marked as untrusted evidence.
- Prompt-injection phrases are flagged.
- Chunk hashes/source hashes are included.
- Query output is saved to `last_query.md` and `rag_pack.json`.

The app also includes quick-open buttons for `graph_context.md` and `last_query.md` from the Knowledge Graph page.

## Quality Comparison Reports

Before/after Markdown quality reports can be generated without re-running the GUI:

```powershell
python llm_quality_report.py --before old_llm_ready --after llm_ready --output _audit_reports/quality_compare.md
```

The report counts known assertion failures per file and summarizes whether the new cleanup pass reduced or introduced regressions.

## App Data and Generated Artifacts

Common generated folders:

| Folder/File | Purpose |
| --- | --- |
| `llm_ready/` | Main generated Markdown output. |
| `*_assets/` | Extracted figure assets beside output Markdown. |
| `.llm_ingest_manifest.json` | Conversion cache manifest. |
| `_knowledge_graph/` | Default graph index. |
| `_audit_corpus_cache/` | Downloaded audit PDFs. |
| `_audit_reports/` | Audit outputs and reports. |
| `_python313/` | Optional sidecar Python runtime. |
| `_vendor_site/`, `_vendor_manual/` | Local vendored Python packages. |

Most generated folders are git-ignored.

## Privacy Model

Privacy mode can redact local user paths in manifests/reports where possible.

Important caveat: graph indexes and RAG packs contain extracted document text. Treat these folders as sensitive:

- `_knowledge_graph/`
- `_audit_reports/`
- `llm_ready/`

Do not share them unless the source papers and extracted text are safe to share.

## Normal User Workflow

1. Put PDFs in `downloaded/`.
2. Launch the app with `launch_llm_ingest_app.bat`.
3. Choose `Workflow`.
4. Select folder batch mode.
5. Input: `downloaded/`.
6. Output: `llm_ready/`.
7. Keep backend as `auto` unless debugging.
8. Run ingest.
9. Build graph from `llm_ready/`.
10. Query graph in hybrid mode.

## Developer Workflow

After changing cleanup behavior:

```powershell
python -m py_compile llm_pdf_cleanup.py llm_ingest.py llm_knowledge_graph.py
python -m unittest discover -s tests
```

Then run focused conversion smoke tests:

```powershell
python llm_ingest.py downloaded\Protein_fibers_with_self-recoverable_mechanical_properties_via_dynamic_imine_che.pdf --output _tmp_structural_quality\protein.md --pdf-backend pymupdf4llm --ocr-mode off
python llm_ingest.py downloaded\Recombinant_Spidroins_Fully_Replicate_Primary_Mechanical_Properties_of_Natural_S.pdf --output _tmp_structural_quality\recombinant.md --pdf-backend pymupdf4llm --ocr-mode off
```

Then build graph smoke:

```powershell
python llm_ingest.py graph build --source-dir llm_ready --index-dir _kg_smoke --embedding-model hash --embedding-dimensions 384
```

## Current Strengths

- Robust local workflow for PDFs and generated Markdown.
- Runtime-aware backend routing.
- Hardened PDF subprocess option.
- Strong document-level cleanup tests now separated into `llm_pdf_cleanup.py`.
- Audit mode for regression discovery.
- Queryable local graph/RAG index.
- No cloud dependency for embeddings; hash vectors are local and deterministic.

## Current Limitations

- PDF layout recovery is heuristic, not perfect.
- Some dense scientific tables remain ugly.
- Formula recovery is limited when formulas are image-only.
- Figure placement is improved but not guaranteed to match exact source location.
- Marker backend requires a separate compatible sidecar environment and model availability.
- Knowledge graph edges are term/citation/heading/document based, not deep semantic ontology extraction.
- Hash embeddings are lightweight and local; they are useful, but not as semantically rich as model embeddings.

## Suggested Next Improvements

- Split figure/caption recovery into its own module with tests.
- Add more cleanup fixtures from real bad PDFs.
- Add an audit assertion suite that fails on known regressions.
- Expand the real-PDF benchmark corpus with more scored examples.
- Add dedicated formula reconstruction for equations that are only present as images.
- Add dedicated dense-table reconstruction beyond cleanup and backend routing.
