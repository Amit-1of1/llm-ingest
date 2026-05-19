"""Compatibility wrapper for benchmark CLI tools."""

import sys

from src.llm_ingest.tools import benchmark as _impl

sys.modules[__name__] = _impl
