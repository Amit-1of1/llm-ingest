#!/usr/bin/env python3
"""Frozen executable entrypoint for the hardened PDF worker."""

from __future__ import annotations

import pdf_worker_runner


if __name__ == "__main__":
    raise SystemExit(pdf_worker_runner.main())
