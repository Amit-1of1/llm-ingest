"""Compatibility wrapper for the restructured local API module."""

import sys

from src.llm_ingest import local_api as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl
