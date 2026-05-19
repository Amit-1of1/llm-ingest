# Changes

## Repository Restructure

- Moved implementation modules into `src/llm_ingest/`.
- Moved cleanup modules into `src/llm_ingest/cleanup/`.
- Moved knowledge graph code into `src/llm_ingest/graph/`.
- Moved backend adapters into `src/llm_ingest/backends/`.
- Moved audit, benchmark, and quality tools into `src/llm_ingest/tools/`.
- Added package `__init__.py` files for the new source layout.

## Compatibility Wrappers

- Kept root-level Python wrappers for existing imports and commands:
  - `llm_ingest.py`
  - `llm_ingest_app.pyw`
  - `llm_local_api.py`
  - `llm_knowledge_graph.py`
  - `llm_pdf_cleanup.py`
  - `llm_figure_cleanup.py`
  - `llm_structured_output.py`
  - `llm_audit_assertions.py`
  - `llm_quality_report.py`
  - `llm_benchmark.py`
  - `pdf_worker_runner.py`
  - `marker_sidecar_runner.py`
  - `llm_backends/*`

## Config, Assets, Docs, and Requirements

- Moved `audit_corpus_manifest.json` to `config/audit_corpus_manifest.json`.
- Moved `fonts/` to `assets/fonts/`.
- Moved detailed reports and workflow docs into `docs/`.
- Moved dependency files into `requirements/`.
- Kept root requirement wrapper files for compatibility.

## Scripts and Packaging

- Moved implementation build/install/launch scripts into `scripts/`.
- Kept root wrapper scripts for existing user commands.
- Moved `LLMIngest.spec` into `packaging/LLMIngest.spec`.
- Updated build and install scripts to resolve the project root from `scripts/`.
- Updated PyInstaller data paths for `assets/`, `config/`, `requirements/`, and package-side worker scripts.
- Preserved the Tkinter frozen-payload guard in the build flow.

## Deleted Confirmed Dead Artifacts

- Deleted `_tmp_packaging_smoke/` after reference search found no source, docs, config, or test references.
- Deleted `manual_downloads.txt` after reference search found no source, docs, config, or test references.
- Deleted `report.json` after reference search found no source, docs, config, or test references.

## Deployment and CI

- Updated `.github/workflows/tests.yml` to compile root wrappers and the full `src` package.
- Updated `.gitignore` to include `_tmp_packaging_smoke/` and `_benchmark_reports/`.
- Updated README/docs paths for the new `config/`, `docs/`, and `requirements/` folders.

## Verification

- `python -m py_compile ...` passed for root compatibility wrappers.
- `python -m compileall -q src` passed.
- PowerShell script parsing passed for build/install wrappers and implementation scripts.
- `python -m unittest discover -s tests` passed: 45 tests.
- CLI smoke check passed: `python llm_ingest.py --help`.
- API smoke check passed: `python llm_ingest_api_entry.py --help`.
