"""Compatibility wrapper for the local API executable entry point."""

import llm_local_api


if __name__ == "__main__":
    raise SystemExit(llm_local_api.main())
