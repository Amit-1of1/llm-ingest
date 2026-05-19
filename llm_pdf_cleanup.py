"""Compatibility wrapper for PDF cleanup helpers."""

import sys

from src.llm_ingest.cleanup import pdf as _impl

sys.modules[__name__] = _impl
