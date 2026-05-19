import tempfile
import unittest
from pathlib import Path
from unittest import mock

import llm_ingest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_PAYLOAD_ROOTS = (
    PROJECT_ROOT / "dist" / "LLMIngest",
    PROJECT_ROOT / "release" / "LLMIngest-Windows" / "LLMIngest",
)
FROZEN_TKINTER_FILES = (
    Path("_internal") / "_tkinter.pyd",
    Path("_internal") / "tcl86t.dll",
    Path("_internal") / "tk86t.dll",
)
FROZEN_TKINTER_DIRS = (
    Path("_internal") / "tcl",
    Path("_internal") / "tk",
)


class PackagingRuntimeTests(unittest.TestCase):
    def test_pipeline_signature_survives_missing_source_file(self) -> None:
        with mock.patch.object(llm_ingest, "_PIPELINE_SIGNATURE", None):
            with mock.patch.object(llm_ingest, "__file__", r"C:\not-present\llm_ingest.py"):
                signature = llm_ingest._pipeline_signature()

        self.assertRegex(signature, r"^[0-9a-f]{16}$")

    def test_empty_input_file_is_rejected_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / "empty.pdf"
            empty.write_bytes(b"")

            with self.assertRaisesRegex(ValueError, "empty"):
                llm_ingest._validate_input_file_limits(empty, llm_ingest.SecurityLimits())

    def test_build_script_fails_when_frozen_tkinter_payload_is_missing(self) -> None:
        script = (
            (PROJECT_ROOT / "build_windows_release.ps1").read_text(encoding="utf-8")
            + "\n"
            + (PROJECT_ROOT / "scripts" / "build_windows_release.ps1").read_text(encoding="utf-8")
        )

        self.assertIn("Assert-FrozenTkinterPayload", script)
        self.assertIn("_internal\\_tkinter.pyd", script)
        self.assertIn("_internal\\tcl86t.dll", script)
        self.assertIn("_internal\\tk86t.dll", script)

    def test_existing_frozen_payloads_bundle_tkinter_runtime(self) -> None:
        payload_roots = [root for root in FROZEN_PAYLOAD_ROOTS if root.exists()]
        if not payload_roots:
            self.skipTest("No frozen LLMIngest payload exists in dist/ or release/.")

        for root in payload_roots:
            with self.subTest(root=str(root)):
                missing_files = [
                    str(path)
                    for path in FROZEN_TKINTER_FILES
                    if not (root / path).is_file()
                ]
                missing_dirs = [
                    str(path)
                    for path in FROZEN_TKINTER_DIRS
                    if not (root / path).is_dir()
                ]
                self.assertEqual([], missing_files + missing_dirs)


if __name__ == "__main__":
    unittest.main()
