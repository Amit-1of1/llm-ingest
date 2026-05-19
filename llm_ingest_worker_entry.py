"""Compatibility wrapper for the PDF worker executable entry point."""

import pdf_worker_runner


if __name__ == "__main__":
    raise SystemExit(pdf_worker_runner.main())
