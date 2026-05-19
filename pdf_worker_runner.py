"""Compatibility wrapper for the hardened PDF worker."""

import sys

from src.llm_ingest import pdf_worker_runner as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl
