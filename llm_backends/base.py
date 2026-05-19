"""Compatibility wrapper for backend adapter base types."""

import sys

from src.llm_ingest.backends import base as _impl

sys.modules[__name__] = _impl
