"""Compatibility wrapper for Markdown quality reports."""

import sys

from src.llm_ingest.tools import quality_report as _impl

sys.modules[__name__] = _impl
