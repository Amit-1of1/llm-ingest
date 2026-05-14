from __future__ import annotations

from collections.abc import Iterable

from .adapters import DoclingAdapter, MarkerAdapter, MinerUAdapter, PyMuPDF4LLMAdapter, UnstructuredAdapter
from .base import BackendAdapter, BackendHealth


_ADAPTER_FACTORIES = {
    "pymupdf4llm": PyMuPDF4LLMAdapter,
    "docling": DoclingAdapter,
    "marker": MarkerAdapter,
    "mineru": MinerUAdapter,
    "unstructured": UnstructuredAdapter,
}


def available_backend_names() -> tuple[str, ...]:
    return tuple(_ADAPTER_FACTORIES)


def get_backend_adapter(name: str) -> BackendAdapter:
    normalized = _normalize_backend_name(name)
    try:
        factory = _ADAPTER_FACTORIES[normalized]
    except KeyError as exc:
        known = ", ".join(available_backend_names())
        raise ValueError(f"Unknown backend '{name}'. Known backends: {known}.") from exc
    return factory()


def backend_health(names: Iterable[str] | None = None) -> dict[str, BackendHealth]:
    selected_names = available_backend_names() if names is None else tuple(names)
    health_by_name: dict[str, BackendHealth] = {}
    for name in selected_names:
        adapter = get_backend_adapter(name)
        health_by_name[adapter.name] = adapter.health()
    return health_by_name


def _normalize_backend_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace("-", "")
