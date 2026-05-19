"""Compatibility wrapper for figure cleanup helpers."""

import sys

from src.llm_ingest.cleanup import figures as _impl

sys.modules[__name__] = _impl
