"""Compatibility wrapper for backend adapters."""

import sys

from src.llm_ingest.backends import *  # noqa: F401,F403
from src.llm_ingest.backends import adapters as _adapters
from src.llm_ingest.backends import base as _base
from src.llm_ingest.backends import registry as _registry

sys.modules["llm_backends.adapters"] = _adapters
sys.modules["llm_backends.base"] = _base
sys.modules["llm_backends.registry"] = _registry
