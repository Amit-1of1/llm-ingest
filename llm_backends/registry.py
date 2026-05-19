"""Compatibility wrapper for backend registry helpers."""

import sys

from src.llm_ingest.backends import registry as _impl

sys.modules[__name__] = _impl
