#!/usr/bin/env python3
"""Isolated PDF extraction worker for llm_ingest hardened mode."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path


def main() -> int:
    os.environ["LLM_INGEST_PDF_WORKER"] = "1"
    try:
        import llm_ingest

        payload = json.loads(sys.stdin.read() or "{}")
        input_path = Path(payload["input_path"])
        output_path = Path(payload["output_path"])
        temp_output = Path(payload["temp_output"])
        config = llm_ingest.pdf_config_from_payload(payload["pdf_config"])
        log_buffer = io.StringIO()
        with contextlib.redirect_stdout(log_buffer), contextlib.redirect_stderr(log_buffer):
            llm_ingest._validate_input_file_limits(input_path, config.security)
            llm_ingest._validate_pdf_page_limit(input_path, config.security)
            text, backend = llm_ingest._extract_pdf_direct(input_path, output_path, config)
        llm_ingest.safe_atomic_write_text(temp_output, text, encoding="utf-8")
        sys.stdout.write(
            json.dumps(
                {
                    "status": "ok",
                    "backend": backend,
                    "log": log_buffer.getvalue()[-4000:],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except BaseException as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
