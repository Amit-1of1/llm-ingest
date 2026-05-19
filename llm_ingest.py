"""Compatibility wrapper for the restructured LLM Ingest CLI."""

import sys

from src.llm_ingest import ingest as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
