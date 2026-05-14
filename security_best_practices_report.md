# Security Best Practices Report

## Threat Model

Trusted local desktop user processing untrusted PDFs, Markdown files, audit manifests, downloaded audit PDFs, and knowledge graph indexes.

## Implemented Hardening

- Added `SecurityLimits` for file size, PDF page count, backend timeout, audit download size, hardened mode, external Marker allowance, and privacy mode.
- Routed hardened PDF extraction through `pdf_worker_runner.py` with structured JSON results and timeout handling.
- Restricted arbitrary Marker interpreters unless explicitly allowed, and minimized the Marker subprocess environment.
- Hardened audit downloads to HTTPS-only by default, streamed partial files, enforced size caps, and required SHA-256 unless explicitly allowed.
- Added safe atomic writers and guarded generated asset directory deletion.
- Added knowledge graph index validation, chunk/schema caps, prompt-injection flags, source hashes, and an explicit untrusted-evidence RAG contract.
- Added GUI controls for hardened mode, privacy mode, backend timeout, max input size, and max PDF pages.
- Disabled GitNexus `npx` fallback by default and capped hook log detail length.

## Remaining Risk

- PDF metadata probing still relies on native PDF libraries, but hardened conversion now performs the page-limit check inside the worker path.
- The local hash embedding backend is deterministic and private, but it is not a semantic model. It is intended as a safe default, not a replacement for a vetted embedding service.
- Privacy mode redacts common local path exposure, but graph indexes still intentionally contain extracted document text.
