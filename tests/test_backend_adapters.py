import importlib
import sys
import types
import unittest
from unittest import mock


class BackendAdapterRegistryTests(unittest.TestCase):
    def test_registry_returns_known_adapters(self) -> None:
        from llm_backends import available_backend_names, get_backend_adapter

        names = available_backend_names()
        self.assertEqual(("pymupdf4llm", "docling", "marker", "mineru", "unstructured"), names)
        for name in names:
            adapter = get_backend_adapter(name)
            self.assertEqual(name, adapter.name)
            self.assertTrue(adapter.display_name)
            self.assertIsInstance(adapter.is_available(), bool)

    def test_backend_health_is_non_crashing(self) -> None:
        from llm_backends import BackendHealth, backend_health

        health = backend_health()
        self.assertEqual({"pymupdf4llm", "docling", "marker", "mineru", "unstructured"}, set(health))
        for result in health.values():
            self.assertIsInstance(result, BackendHealth)
            self.assertTrue(result.name)
            self.assertTrue(result.detail)
        self.assertEqual({"pymupdf4llm"}, set(backend_health(["PyMuPDF4LLM"])))

    def test_missing_optional_modules_are_reported_cleanly(self) -> None:
        from llm_backends import backend_health

        with mock.patch("importlib.util.find_spec", return_value=None):
            health = backend_health(["docling", "marker", "mineru", "unstructured", "pymupdf4llm"])

        self.assertFalse(health["docling"].importable)
        self.assertEqual(("docling", "docling.document_converter"), health["docling"].missing_modules)
        self.assertIn("pip install docling", health["docling"].install_hint)
        self.assertFalse(health["pymupdf4llm"].runnable)
        self.assertEqual(("pymupdf4llm", "pymupdf"), health["pymupdf4llm"].missing_modules)

    def test_registry_import_does_not_import_heavy_optional_modules(self) -> None:
        heavy_modules = {"pymupdf4llm", "docling", "marker", "mineru", "unstructured", "pymupdf", "fitz"}
        before = set(sys.modules)

        importlib.import_module("llm_backends.registry")

        newly_imported = set(sys.modules) - before
        self.assertFalse(heavy_modules & newly_imported)

    def test_importable_unimplemented_adapters_raise_clear_not_implemented(self) -> None:
        from llm_backends import get_backend_adapter

        with mock.patch("importlib.util.find_spec", return_value=object()):
            adapter = get_backend_adapter("marker")
            health = adapter.health()

        self.assertTrue(health.importable)
        self.assertFalse(health.runnable)
        with self.assertRaisesRegex(NotImplementedError, "not implemented"):
            adapter.extract("paper.pdf")

    def test_docling_adapter_extracts_markdown_when_available(self) -> None:
        from llm_backends import get_backend_adapter

        class FakeDocument:
            def export_to_markdown(self) -> str:
                return "# Paper\n\nDocling text."

        class FakeConverter:
            def convert(self, path: str, **kwargs: object) -> object:
                return types.SimpleNamespace(document=FakeDocument())

        fake_module = types.SimpleNamespace(DocumentConverter=FakeConverter)
        with mock.patch("llm_backends.adapters.is_module_importable", return_value=True):
            with mock.patch("llm_backends.adapters.import_module", return_value=fake_module):
                extraction = get_backend_adapter("docling").extract("paper.pdf")

        self.assertEqual("docling", extraction.backend)
        self.assertIn("Docling text", extraction.text)

    def test_unstructured_adapter_extracts_partitioned_elements(self) -> None:
        from llm_backends import get_backend_adapter

        class FakeElement:
            category = "NarrativeText"

            def __str__(self) -> str:
                return "Recovered paragraph."

        fake_module = types.SimpleNamespace(partition_pdf=lambda **kwargs: [FakeElement()])
        with mock.patch("llm_backends.adapters.is_module_importable", return_value=True):
            with mock.patch("llm_backends.adapters.import_module", return_value=fake_module):
                extraction = get_backend_adapter("unstructured").extract("paper.pdf")

        self.assertEqual("unstructured", extraction.backend)
        self.assertEqual("Recovered paragraph.", extraction.text)
        self.assertEqual(1, len(extraction.blocks))

    def test_unknown_backend_is_rejected(self) -> None:
        from llm_backends import get_backend_adapter

        with self.assertRaisesRegex(ValueError, "Unknown backend"):
            get_backend_adapter("unknown")


if __name__ == "__main__":
    unittest.main()
