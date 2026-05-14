from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from .base import BackendHealth, DocumentExtraction, ExtractionBlock, is_module_importable


@dataclass(frozen=True)
class ImportOnlyAdapter:
    name: str
    display_name: str
    module_names: tuple[str, ...]
    install_hint: str

    def is_available(self) -> bool:
        return self.health().importable

    def health(self) -> BackendHealth:
        missing = tuple(module for module in self.module_names if not is_module_importable(module))
        importable = not missing
        if importable:
            detail = f"{self.display_name} is importable; extraction is not implemented in this adapter yet."
        else:
            detail = f"{self.display_name} is not importable."
        return BackendHealth(
            name=self.name,
            display_name=self.display_name,
            available=importable,
            importable=importable,
            runnable=False,
            detail=detail,
            install_hint=self.install_hint,
            missing_modules=missing,
        )

    def extract(self, input_path: str | Path, **kwargs: Any) -> DocumentExtraction:
        raise NotImplementedError(
            f"{self.display_name} extraction is not implemented in llm_backends yet. "
            "Use health() to check whether the optional dependency is installed."
        )


class PyMuPDF4LLMAdapter:
    name = "pymupdf4llm"
    display_name = "PyMuPDF4LLM"
    install_hint = "pip install pymupdf pymupdf4llm"

    def is_available(self) -> bool:
        return self.health().runnable

    def health(self) -> BackendHealth:
        has_pymupdf4llm = is_module_importable("pymupdf4llm")
        has_pymupdf = is_module_importable("pymupdf") or is_module_importable("fitz")
        missing = []
        if not has_pymupdf4llm:
            missing.append("pymupdf4llm")
        if not has_pymupdf:
            missing.append("pymupdf")
        runnable = not missing
        if runnable:
            detail = "PyMuPDF4LLM and PyMuPDF are importable."
        elif not has_pymupdf4llm and not has_pymupdf:
            detail = "PyMuPDF4LLM and PyMuPDF are not importable."
        elif not has_pymupdf4llm:
            detail = "PyMuPDF4LLM is not importable."
        else:
            detail = "PyMuPDF is not importable."
        return BackendHealth(
            name=self.name,
            display_name=self.display_name,
            available=runnable,
            importable=has_pymupdf4llm,
            runnable=runnable,
            detail=detail,
            install_hint=self.install_hint,
            missing_modules=tuple(missing),
        )

    def extract(self, input_path: str | Path, **kwargs: Any) -> DocumentExtraction:
        health = self.health()
        if not health.runnable:
            missing = ", ".join(health.missing_modules) or "optional dependencies"
            raise RuntimeError(f"{self.display_name} is unavailable: missing {missing}. {self.install_hint}")

        import pymupdf4llm

        path = Path(input_path)
        markdown = pymupdf4llm.to_markdown(str(path), **kwargs)
        text = _coerce_markdown_text(markdown)
        blocks = (ExtractionBlock(text=text),) if text else ()
        return DocumentExtraction(
            backend=self.name,
            text=text,
            blocks=blocks,
            metadata={"source_path": str(path)},
        )


def _coerce_markdown_text(markdown: Any) -> str:
    if markdown is None:
        return ""
    if isinstance(markdown, str):
        return markdown

    chunks = []
    try:
        iterator = iter(markdown)
    except TypeError:
        return str(markdown)

    for chunk in iterator:
        if isinstance(chunk, dict):
            chunks.append(str(chunk.get("text") or ""))
        elif chunk is not None:
            chunks.append(str(chunk))
    return "\n\n".join(chunk for chunk in chunks if chunk).strip()


class DoclingAdapter(ImportOnlyAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="docling",
            display_name="Docling",
            module_names=("docling",),
            install_hint="pip install docling",
        )

    def health(self) -> BackendHealth:
        missing = tuple(module for module in ("docling", "docling.document_converter") if not is_module_importable(module))
        runnable = not missing
        detail = "Docling is importable and can export Markdown." if runnable else "Docling is not importable."
        return BackendHealth(
            name=self.name,
            display_name=self.display_name,
            available=runnable,
            importable=is_module_importable("docling"),
            runnable=runnable,
            detail=detail,
            install_hint=self.install_hint,
            missing_modules=missing,
        )

    def extract(self, input_path: str | Path, **kwargs: Any) -> DocumentExtraction:
        health = self.health()
        if not health.runnable:
            missing = ", ".join(health.missing_modules) or "docling"
            raise RuntimeError(f"Docling is unavailable: missing {missing}. {self.install_hint}")

        module = import_module("docling.document_converter")
        converter = module.DocumentConverter()
        result = converter.convert(str(input_path), **_filter_none_kwargs(kwargs))
        document = getattr(result, "document", result)
        if hasattr(document, "export_to_markdown"):
            text = document.export_to_markdown()
        elif hasattr(document, "export_to_text"):
            text = document.export_to_text()
        else:
            text = str(document)
        text = str(text or "").strip()
        return DocumentExtraction(
            backend=self.name,
            text=text,
            blocks=(ExtractionBlock(text=text),) if text else (),
            metadata={"source_path": str(Path(input_path))},
        )


class MarkerAdapter(ImportOnlyAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="marker",
            display_name="Marker",
            module_names=("marker",),
            install_hint="pip install marker-pdf",
        )


class MinerUAdapter(ImportOnlyAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="mineru",
            display_name="MinerU",
            module_names=("mineru",),
            install_hint="pip install mineru",
        )

    def health(self) -> BackendHealth:
        importable = is_module_importable("mineru")
        executable = _first_executable("magic-pdf", "mineru")
        runnable = importable and executable is not None
        if runnable:
            detail = f"MinerU is importable and CLI '{executable}' is available."
        elif importable:
            detail = "MinerU is importable, but no supported CLI executable was found."
        else:
            detail = "MinerU is not importable."
        missing = () if importable else ("mineru",)
        return BackendHealth(
            name=self.name,
            display_name=self.display_name,
            available=runnable,
            importable=importable,
            runnable=runnable,
            detail=detail,
            install_hint=self.install_hint,
            missing_modules=missing,
        )

    def extract(self, input_path: str | Path, **kwargs: Any) -> DocumentExtraction:
        health = self.health()
        if not health.runnable:
            raise RuntimeError(f"MinerU is unavailable: {health.detail} {self.install_hint}")

        executable = _first_executable("magic-pdf", "mineru")
        if executable is None:
            raise RuntimeError("MinerU CLI executable was not found.")
        timeout = int(kwargs.get("timeout") or kwargs.get("timeout_seconds") or 600)
        with tempfile.TemporaryDirectory(prefix="llm_ingest_mineru_") as temp:
            out_dir = Path(temp)
            command = [executable, "-p", str(input_path), "-o", str(out_dir)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
            if completed.returncode != 0:
                stderr = (completed.stderr or completed.stdout or "").strip()
                raise RuntimeError(f"MinerU failed with exit code {completed.returncode}: {stderr[:800]}")
            markdown_files = sorted(out_dir.rglob("*.md"))
            if not markdown_files:
                raise RuntimeError("MinerU completed but did not produce Markdown output.")
            text = "\n\n".join(path.read_text(encoding="utf-8", errors="replace") for path in markdown_files).strip()
        return DocumentExtraction(
            backend=self.name,
            text=text,
            blocks=(ExtractionBlock(text=text),) if text else (),
            metadata={"source_path": str(Path(input_path)), "executable": executable},
        )


class UnstructuredAdapter(ImportOnlyAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="unstructured",
            display_name="Unstructured",
            module_names=("unstructured",),
            install_hint="pip install unstructured",
        )

    def health(self) -> BackendHealth:
        missing = tuple(module for module in ("unstructured", "unstructured.partition.pdf") if not is_module_importable(module))
        runnable = not missing
        detail = "Unstructured PDF partitioning is importable." if runnable else "Unstructured PDF partitioning is not importable."
        return BackendHealth(
            name=self.name,
            display_name=self.display_name,
            available=runnable,
            importable=is_module_importable("unstructured"),
            runnable=runnable,
            detail=detail,
            install_hint=self.install_hint,
            missing_modules=missing,
        )

    def extract(self, input_path: str | Path, **kwargs: Any) -> DocumentExtraction:
        health = self.health()
        if not health.runnable:
            missing = ", ".join(health.missing_modules) or "unstructured"
            raise RuntimeError(f"Unstructured is unavailable: missing {missing}. {self.install_hint}")

        module = import_module("unstructured.partition.pdf")
        partition_kwargs = _filter_none_kwargs(kwargs)
        partition_kwargs.setdefault("filename", str(input_path))
        elements = module.partition_pdf(**partition_kwargs)
        blocks: list[ExtractionBlock] = []
        text_parts: list[str] = []
        for element in elements:
            element_text = str(element).strip()
            if not element_text:
                continue
            category = getattr(element, "category", element.__class__.__name__)
            metadata = {"category": str(category)}
            element_metadata = getattr(element, "metadata", None)
            if element_metadata is not None and hasattr(element_metadata, "to_dict"):
                metadata.update(element_metadata.to_dict())
            blocks.append(ExtractionBlock(block_type=str(category).lower(), text=element_text, metadata=metadata))
            text_parts.append(element_text)
        text = "\n\n".join(text_parts).strip()
        return DocumentExtraction(
            backend=self.name,
            text=text,
            blocks=tuple(blocks),
            metadata={"source_path": str(Path(input_path)), "element_count": len(blocks)},
        )


def _filter_none_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    ignored = {"timeout", "timeout_seconds"}
    return {key: value for key, value in kwargs.items() if value is not None and key not in ignored}


def _first_executable(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None
