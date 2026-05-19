"""Compatibility wrapper for audit assertion helpers."""

import sys

from src.llm_ingest.tools import audit_assertions as _impl

sys.modules[__name__] = _impl
