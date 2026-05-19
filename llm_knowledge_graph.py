"""Compatibility wrapper for knowledge graph helpers."""

import sys

from src.llm_ingest.graph import knowledge_graph as _impl

sys.modules[__name__] = _impl
