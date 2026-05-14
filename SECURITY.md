# Security Policy

## Threat Model

This project is designed for a trusted local desktop user processing untrusted PDFs, Markdown, audit manifests, and graph indexes.

The app is not a network service and does not add a multi-user permission model. Generated outputs may contain full extracted document text.

## Safe Defaults

- PDF extraction can run in a worker subprocess with timeout and file/page/asset limits.
- Audit downloads require HTTPS by default and are size-limited.
- Public audit PDFs are cached locally and verified by SHA-256 when hashes are available.
- Graph/RAG query packs mark retrieved text as untrusted evidence.
- Generated outputs are git-ignored by default.

## Sensitive Artifacts

Do not publish these folders unless you have reviewed their contents:

- `downloaded/`
- `llm_ready/`
- `_knowledge_graph/`
- `_audit_reports/`
- `_audit_corpus_cache/`
- `*_assets/`

## Reporting

If you find a security issue, open a private advisory or contact the repository owner privately. Include reproduction steps and the smallest possible sample file.
