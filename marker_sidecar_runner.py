#!/usr/bin/env python3
import argparse
import json
import sys
import traceback
from pathlib import Path


def _build_converter(ocr_mode: str):
    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    config = ConfigParser(
        {
            "output_format": "markdown",
            "force_ocr": ocr_mode == "full",
            "disable_ocr": ocr_mode == "off",
            "paginate_output": False,
            "disable_image_extraction": True,
        }
    )
    converter = PdfConverter(
        artifact_dict=create_model_dict(),
        config=config.generate_config_dict(),
        processor_list=config.get_processors(),
        renderer=config.get_renderer(),
        llm_service=config.get_llm_service(),
    )
    return converter


def _run_probe(mode: str) -> None:
    from marker.output import text_from_rendered  # noqa: F401

    payload = {
        "probe": mode,
        "python": sys.executable,
        "status": "ok",
    }

    if mode == "imports":
        from marker.config.parser import ConfigParser  # noqa: F401
        from marker.converters.pdf import PdfConverter  # noqa: F401
        from marker.models import create_model_dict  # noqa: F401
        payload["detail"] = "Marker imports are available."
    elif mode == "models":
        _build_converter("auto")
        payload["detail"] = "Marker models are available."
    else:
        raise ValueError(f"Unsupported probe mode: {mode}")

    print(json.dumps(payload))


def _run_conversion(input_path: str, output_path: str, ocr_mode: str) -> None:
    from marker.output import text_from_rendered

    converter = _build_converter(ocr_mode)
    rendered = converter(input_path)
    markdown, _, _ = text_from_rendered(rendered)
    Path(output_path).write_text(markdown or "", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Marker extraction in a sidecar Python runtime.")
    parser.add_argument("--input", help="Input PDF path")
    parser.add_argument("--output", help="Output markdown path")
    parser.add_argument("--ocr-mode", default="auto", choices=("auto", "full", "off"))
    parser.add_argument("--probe", choices=("imports", "models"))
    args = parser.parse_args()

    if args.probe:
        _run_probe(args.probe)
        return

    if not args.input or not args.output:
        parser.error("--input and --output are required unless --probe is used.")

    _run_conversion(args.input, args.output, args.ocr_mode)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        traceback.print_exc()
        message = str(exc).strip()
        sys.exit(message or exc.__class__.__name__)
