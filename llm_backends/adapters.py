"""Compatibility wrapper for backend adapter implementations."""

import sys

from src.llm_ingest.backends import adapters as _impl

sys.modules[__name__] = _impl
