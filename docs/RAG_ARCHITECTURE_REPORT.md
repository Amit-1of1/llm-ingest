# LLM Ingest RAG Architecture Report

Date: 2026-05-18

## Executive Summary

The app currently uses a **local hybrid graph-enhanced RAG architecture**.

From the five architectures in the attached image, our current system maps most closely to:

1. **Hybrid RAG**: implemented in a local, dependency-light form.
2. **GraphRAG**: partially implemented as a graph-enhanced retrieval layer.
3. **Multimodal RAG**: partially present at ingest time through extracted image assets and captions, but not yet true multimodal retrieval.

Implementation update: the first local/private pass of these upgrades has now been added. The app now writes BM25-style sparse, multimodal, and community-summary artifacts; query results use RRF plus reranking; and retrieved chunks receive corrective evidence grades. A second cheap-path pass adds opt-in local figure OCR, opt-in CLIP-style image embeddings, asset hashes, and optional OpenAI-compatible local LLM community summaries with deterministic fallback.

The app still does **not** yet implement full:

- **Agentic RAG**
- **LLM-based Corrective RAG over every query**
- **Full GraphRAG with community summaries and global search**
- **Always-on image-embedding multimodal retrieval over figure pixels, charts, and tables**

The best next architecture for this use case is not a total rewrite. The strongest path is:

```text
PDF/document cleanup
  -> structured Markdown + assets + metadata
  -> hybrid retrieval over text
  -> graph expansion over papers, sections, citations, figures, terms
  -> reranking / corrective evidence grading
  -> optional multimodal figure/table retrieval
  -> local API for LLM tools
```

In other words: **Hybrid GraphRAG + Corrective RAG + optional multimodal indexing**.

## Current Architecture

### Ingest Layer

The app converts source documents into cleaner Markdown:

- PDFs
- DOCX
- PPTX
- HTML
- CSV
- TXT
- Markdown

Important files:

- `llm_ingest.py`: conversion engine, CLI, backend routing, audit, safety limits.
- `llm_pdf_cleanup.py`: document cleanup, frontmatter, titles, references, boilerplate, headings.
- `llm_figure_cleanup.py`: figure and caption cleanup.
- `pdf_worker_runner.py`: hardened subprocess for PDF extraction.
- `marker_sidecar_runner.py`: optional Marker sidecar.

This layer is the foundation. For scientific papers, retrieval quality is only as good as the cleaned Markdown, figure captions, references, and extracted table/formula text.

### Knowledge Graph Layer

The graph builder reads generated Markdown and writes a local index.

Important file:

- `llm_knowledge_graph.py`

The graph includes:

- documents
- headings
- chunks
- terms
- citations
- links
- similarity/community-style relationships

The graph artifacts include:

- `index_meta.json`
- `graph.json`
- `chunks.jsonl`
- `embeddings.jsonl`
- `graph_context.md`
- `last_query.md`
- `rag_pack.json`

### Retrieval Layer

The query system supports:

- lexical retrieval
- vector retrieval
- hybrid retrieval
- graph expansion

Current default retrieval weights:

```text
lexical: 0.40
vector:  0.45
graph:   0.15
```

Supported embedding modes:

- `hash`
- `tfidf-hash`
- `sentence-transformers`
- `none`

This means the app is already more than naive vector RAG. It combines keyword matching, vector similarity, and graph signals.

### API Layer

The app now includes a local API executable:

- `LLMIngestAPI.exe`
- `llm_local_api.py`

Endpoints:

- `GET /health`
- `GET /openapi.json`
- `POST /convert`
- `POST /graph/build`
- `POST /graph/query`

This makes the app callable from local LLM tools such as Claude, Codex, and agent runners.

## Mapping Against the Five Architectures

## 1. Hybrid RAG

### What Hybrid RAG Means

Hybrid RAG combines sparse keyword search with dense vector search, usually fusing results with a method such as reciprocal rank fusion or weighted scoring.

### What We Have

We have a local hybrid retriever:

- lexical term scoring
- optional vector embeddings
- weighted fusion
- graph score

### What Is Missing

We do not yet have a production-grade sparse index like BM25/SQLite FTS5/Lucene.

We do not yet have:

- RRF-based fusion
- cross-encoder reranking
- dedicated vector database
- document-level grouping after chunk retrieval

### Value for Our Use Case

Very high.

Scientific papers contain exact terms, abbreviations, units, citations, formulas, gene/protein/material names, and figure labels. Dense embeddings alone often miss exact technical tokens. A stronger hybrid retriever would be one of the highest-impact improvements.

Recommended upgrade:

```text
Current weighted lexical + vector scoring
  -> SQLite FTS5 or BM25 sparse index
  -> sentence-transformers dense vectors
  -> RRF fusion
  -> optional reranker
```

## 2. GraphRAG

### What GraphRAG Means

Full GraphRAG builds an entity/relation graph, creates community summaries, and supports both local entity-focused queries and global corpus-level questions.

### What We Have

We have a graph-enhanced retrieval index:

- document nodes
- heading nodes
- chunk nodes
- term nodes
- citation nodes
- link nodes
- similarity edges
- community-like relationships

This is best described as **GraphRAG-light** or **graph-enhanced hybrid RAG**.

### What Is Missing

We do not yet have:

- LLM-based entity extraction
- relation extraction
- community summaries
- global search over corpus themes
- map-reduce style summarization
- entity-centered local search

### Value for Our Use Case

Medium to high.

Full GraphRAG would significantly improve questions like:

- "What are the main themes across all spider silk papers?"
- "Which papers discuss mechanical recovery versus synthesis?"
- "How do methods cluster across the corpus?"
- "Which materials are connected to which properties?"

It is less necessary for precise local questions like:

- "What did this paper say about pH 5.5 tensile stress?"
- "Which figure reports toughness?"

Recommended upgrade:

```text
Current graph
  -> extract entities: material, protein, method, metric, condition, figure, citation
  -> extract typed relationships
  -> build paper-level and corpus-level summaries
  -> add local/global query modes
```

## 3. Agentic RAG

### What Agentic RAG Means

Agentic RAG uses a planner or controller that can choose tools, refine the query, inspect results, run retrieval again, and decide when enough evidence has been gathered.

### What We Have

We have the foundation for agentic use:

- local API
- graph query endpoint
- conversion endpoint
- graph build endpoint
- OpenAPI-like schema

But the app itself is not agentic.

### What Is Missing

We do not yet have:

- planner agent
- iterative retrieval loop
- tool choice
- self-checking answer workflow
- automatic follow-up query generation

### Value for Our Use Case

Medium.

Agentic RAG can help for broad research questions, but it also adds complexity, latency, and less deterministic behavior. For this app, agentic orchestration should sit outside the core engine and call the local API.

Recommended approach:

```text
Keep app deterministic.
Expose local tools through API.
Let Claude/Codex/other agents plan over those tools.
Add optional built-in agent later only after retrieval quality is stronger.
```

## 4. Corrective RAG

### What Corrective RAG Means

Corrective RAG grades retrieved evidence before trusting it. If evidence is weak, irrelevant, ambiguous, or contradictory, the system rewrites the query, retrieves again, or asks for fallback information.

### What We Have

We have early trust-boundary work:

- untrusted evidence labeling
- prompt-injection flags
- source hashes
- structured `rag_pack.json`

But we do not yet grade retrieval quality.

### What Is Missing

We do not yet have:

- evidence relevance grading
- answerability scoring
- citation coverage checking
- contradiction checking
- query rewriting
- "insufficient evidence" response mode

### Value for Our Use Case

Very high.

This app processes messy scientific PDFs. Some chunks contain OCR errors, broken formulas, orphan figure text, duplicate references, or caption fragments. Corrective RAG would prevent weak or polluted chunks from entering the LLM context window.

Recommended upgrade:

```text
Retrieve top 20-40 candidate chunks
  -> score chunk relevance
  -> score extraction quality
  -> require citation/source coverage
  -> keep top 6-10 evidence chunks
  -> mark answerability: high / partial / insufficient
```

This should be implemented before full agentic RAG.

## 5. Multimodal RAG

### What Multimodal RAG Means

Multimodal RAG indexes and retrieves across text, figures, charts, tables, and images.

### What We Have

The app extracts image assets and tries to preserve captions and nearby context.

This is useful, but it is not true multimodal retrieval.

### What Is Missing

We do not yet have:

- image embeddings
- chart/table embeddings
- OCR over extracted figure images
- figure caption-to-image linking as first-class graph edges
- vision model summaries of figures
- figure/table retrieval endpoint

### Value for Our Use Case

High for scientific papers.

The papers you are processing are figure-heavy. A lot of the scientific content lives in:

- graphs
- mechanical-property charts
- microscopy images
- protein structures
- schematic figures
- table layouts

Recommended upgrade:

```text
Extract figure image
  -> preserve caption
  -> OCR any text inside figure
  -> create figure summary
  -> embed caption + OCR + image summary
  -> link figure node to paper section and nearby chunks
```

This would significantly improve questions about figures, plots, and visual evidence.

## Best Target Architecture for This App

The best architecture is:

```text
                 +----------------------+
                 |  Local LLM / Agent   |
                 | Claude / Codex / etc |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |  Local API Server    |
                 |  /convert /graph/*   |
                 +----------+-----------+
                            |
        +-------------------+-------------------+
        |                                       |
        v                                       v
+------------------+                 +----------------------+
| Ingest Pipeline  |                 | Query Pipeline        |
| PDF/DOCX/etc     |                 | Hybrid + Graph RAG    |
+--------+---------+                 +----------+-----------+
         |                                      |
         v                                      v
+------------------+                 +----------------------+
| Markdown Cleanup |                 | Corrective Reranker   |
| Titles/refs/etc  |                 | Evidence Grader       |
+--------+---------+                 +----------+-----------+
         |                                      |
         v                                      v
+------------------+                 +----------------------+
| Structured Notes |                 | Trusted Evidence Pack |
| MD + JSON assets |                 | last_query/rag_pack   |
+--------+---------+                 +----------+-----------+
         |                                      |
         v                                      v
+------------------+                 +----------------------+
| Graph Builder    |                 | Answer-ready Context  |
| Text/Figures     |                 | for LLMs              |
+------------------+                 +----------------------+
```

## Priority Ranking

### Priority 1: Stronger Hybrid Retrieval

Impact: very high

Add:

- BM25 or SQLite FTS5 sparse index
- RRF fusion
- document-level grouping
- optional reranker

This improves almost every query type.

### Priority 2: Corrective RAG Evidence Gate

Impact: very high

Add:

- relevance scoring
- source-quality scoring
- citation coverage
- insufficient-evidence mode
- query rewrite when confidence is low

This directly addresses the messy-PDF problem.

### Priority 3: Figure/Table-Aware Multimodal Index

Impact: high

Add:

- OCR for figure images
- local vision summaries
- figure/table nodes
- caption-image links
- retrieval over figure evidence

This is especially valuable for scientific papers.

### Priority 4: Full GraphRAG Summaries

Impact: medium to high

Add:

- entity extraction
- typed relations
- community summaries
- global/local query modes

This helps corpus-level research questions.

### Priority 5: Agentic RAG

Impact: medium

Add later:

- planner loop
- multi-step retrieval
- optional web/library fallback
- tool orchestration through local API

This should not be the first major upgrade because the retrieval substrate should be stronger first.

## Should We Switch to Another Implementation?

No full rewrite is recommended.

The current implementation is well aligned with the use case:

- local/private
- Windows-friendly
- installable
- PDF-focused
- graph-aware
- API-callable
- testable
- audit-oriented

A rewrite into a full external framework would likely slow the project down. The better path is to selectively add the best pieces:

- BM25/FTS sparse index
- RRF
- reranking
- corrective evidence grading
- multimodal figure/table nodes
- optional full GraphRAG summaries

## Implementation Recommendation

The next development phase should be:

1. Add a real sparse retriever.
2. Replace simple weighted fusion with RRF or configurable fusion.
3. Add candidate reranking.
4. Add corrective evidence grading.
5. Add figure/table nodes to the graph.
6. Add local vision/OCR summaries for figures.
7. Add corpus-level GraphRAG summaries.

This gives the app the biggest quality jump while preserving local/private defaults.

## External References Checked

- Microsoft GraphRAG overview: https://microsoft.github.io/graphrag/query/overview/
- Microsoft Research GraphRAG paper page: https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/
- Qdrant hybrid queries and RRF: https://qdrant.tech/documentation/concepts/hybrid-queries/
- LangGraph Corrective RAG tutorial: https://langchain-ai.lang.chat/langgraph/tutorials/rag/langgraph_crag/
- Recent retrieval benchmark over text/table documents: https://arxiv.org/abs/2604.01733
