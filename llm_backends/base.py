from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


BoundingBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class BackendHealth:
    name: str
    display_name: str
    available: bool
    importable: bool
    runnable: bool
    detail: str
    install_hint: str = ""
    missing_modules: tuple[str, ...] = ()
    version: str | None = None


@dataclass(frozen=True)
class ExtractionBlock:
    block_type: str = "text"
    text: str = ""
    page_number: int | None = None
    bbox: BoundingBox | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FigureBlock(ExtractionBlock):
    block_type: str = "figure"
    caption: str = ""
    image_path: str | None = None


@dataclass(frozen=True)
class TableBlock(ExtractionBlock):
    block_type: str = "table"
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class FormulaBlock(ExtractionBlock):
    block_type: str = "formula"
    latex: str = ""


@dataclass(frozen=True)
class DocumentExtraction:
    backend: str
    text: str
    blocks: tuple[ExtractionBlock, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BackendAdapter(Protocol):
    name: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def health(self) -> BackendHealth:
        ...

    def extract(self, input_path: str | Path, **kwargs: Any) -> DocumentExtraction:
        ...


def is_module_importable(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
