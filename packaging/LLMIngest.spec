# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path.cwd()


def existing_data(path: str, target: str = "."):
    item = ROOT / path
    if item.exists():
        return [(str(item), target)]
    return []


def collect_tcl_tk():
    """Collect tcl/tk data directories needed by tkinter."""
    result = []
    # PyInstaller's hook-tkinter finds these via TCL_LIBRARY / TK_LIBRARY env vars
    # or relative to the Python executable. We also probe the bundled runtime.
    probe_roots = [
        Path(sys.executable).parent,
        ROOT / "_python313" / "runtime",
    ]
    for root in probe_roots:
        tcl_src = root / "tcl" / "tcl8.6"
        tk_src = root / "tcl" / "tk8.6"
        if tcl_src.is_dir():
            result.append((str(tcl_src), "tcl"))
        if tk_src.is_dir():
            result.append((str(tk_src), "tk"))
        if result:
            break
    return result


datas = []
datas += collect_tcl_tk()
datas += existing_data("assets/fonts", "assets/fonts")
datas += existing_data("benchmarks", "benchmarks")
datas += existing_data("src/llm_ingest/pdf_worker_runner.py", "src/llm_ingest")
datas += existing_data("src/llm_ingest/marker_sidecar_runner.py", "src/llm_ingest")
for filename in (
    "config/audit_corpus_manifest.json",
    "requirements.txt",
    "requirements-optional.txt",
    "requirements-docling.txt",
    "requirements-mineru.txt",
    "requirements-unstructured.txt",
    "requirements/base.txt",
    "requirements/optional.txt",
    "requirements/docling.txt",
    "requirements/mineru.txt",
    "requirements/unstructured.txt",
    "pdf_worker_runner.py",
    "marker_sidecar_runner.py",
    "llm_local_api.py",
    "README.md",
    "LICENSE",
):
    datas += existing_data(filename, ".")

for package_name in ("tiktoken", "pymupdf4llm"):
    try:
        datas += collect_data_files(package_name)
    except Exception:
        pass

hiddenimports = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.font",
    "tkinter.colorchooser",
    "tkinter.simpledialog",
    "tkinter.scrolledtext",
    "fitz",
    "pymupdf",
    "pymupdf4llm",
    "docx",
    "pptx",
    "bs4",
    "pandas",
    "tiktoken",
    "llm_ingest",
    "llm_knowledge_graph",
    "llm_pdf_cleanup",
    "llm_figure_cleanup",
    "llm_audit_assertions",
    "llm_quality_report",
    "llm_benchmark",
    "llm_structured_output",
    "llm_local_api",
    "pdf_worker_runner",
    "marker_sidecar_runner",
]

for package_name in ("src.llm_ingest", "llm_backends", "tiktoken_ext"):
    try:
        hiddenimports += collect_submodules(package_name)
    except Exception:
        pass


a = Analysis(
    ["llm_ingest_app.pyw"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "matplotlib",
        "notebook",
        "pytest",
        "tests",
    ],
    noarchive=False,
)
worker_a = Analysis(
    ["llm_ingest_worker_entry.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "matplotlib",
        "notebook",
        "pytest",
        "tests",
    ],
    noarchive=False,
)
api_a = Analysis(
    ["llm_ingest_api_entry.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "matplotlib",
        "notebook",
        "pytest",
        "tests",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
worker_pyz = PYZ(worker_a.pure)
api_pyz = PYZ(api_a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LLMIngest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
worker_exe = EXE(
    worker_pyz,
    worker_a.scripts,
    [],
    exclude_binaries=True,
    name="LLMIngestWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
api_exe = EXE(
    api_pyz,
    api_a.scripts,
    [],
    exclude_binaries=True,
    name="LLMIngestAPI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    worker_exe,
    api_exe,
    a.binaries,
    worker_a.binaries,
    api_a.binaries,
    a.datas,
    worker_a.datas,
    api_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LLMIngest",
)
