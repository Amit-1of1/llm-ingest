"""Compatibility wrapper for the Marker sidecar runner."""

import sys

from src.llm_ingest import marker_sidecar_runner as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl
