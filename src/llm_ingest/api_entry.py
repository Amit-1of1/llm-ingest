"""PyInstaller entry point for the LLM Ingest local API executable."""

from __future__ import annotations

import llm_local_api


if __name__ == "__main__":
    raise SystemExit(llm_local_api.main())
