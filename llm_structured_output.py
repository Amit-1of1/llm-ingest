"""Compatibility wrapper for structured output helpers."""

import sys

from src.llm_ingest.cleanup import structured_output as _impl

sys.modules[__name__] = _impl
