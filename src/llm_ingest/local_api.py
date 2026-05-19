#!/usr/bin/env python3
"""Local HTTP API for LLM Ingest.

The server is designed for desktop agent integrations. It binds to localhost by
default, uses JSON over HTTP, and delegates conversion and graph work to the
same functions used by the CLI and GUI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


API_VERSION = "1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class APIError(Exception):
    """Expected API error that should be returned without a traceback."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


class APIConfig:
    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        token: str = "",
        allow_remote: bool = False,
        debug: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.allow_remote = allow_remote
        self.debug = debug


class LLMIngestHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], config: APIConfig):
        super().__init__(server_address, LLMIngestAPIHandler)
        self.config = config


class LLMIngestAPIHandler(BaseHTTPRequestHandler):
    server_version = "LLMIngestAPI/1"

    @property
    def api_config(self) -> APIConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("llm-ingest-api: " + (format % args) + "\n")

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        if self.path in {"/", "/docs"}:
            self._send_json(_docs_payload())
            return
        if self.path == "/health":
            self._send_json({"status": "ok", "service": "llm-ingest-api", "version": API_VERSION})
            return
        if self.path in {"/openapi.json", "/schema"}:
            self._send_json(_openapi_payload())
            return
        self._send_error("Unknown endpoint.", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            self._require_auth()
            payload = self._read_json()
            if self.path == "/convert":
                self._send_json(convert_payload(payload))
                return
            if self.path == "/graph/build":
                self._send_json(graph_build_payload(payload))
                return
            if self.path == "/graph/query":
                self._send_json(graph_query_payload(payload))
                return
            raise APIError("Unknown endpoint.", HTTPStatus.NOT_FOUND)
        except APIError as exc:
            self._send_error(str(exc), exc.status)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            body: dict[str, Any] = {"error": str(exc), "type": type(exc).__name__}
            if self.api_config.debug:
                body["traceback"] = traceback.format_exc()
            self._send_json(body, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _require_auth(self) -> None:
        token = self.api_config.token
        if not token:
            return
        auth_header = self.headers.get("Authorization", "")
        header_token = self.headers.get("X-LLM-Ingest-Token", "")
        if auth_header == f"Bearer {token}" or header_token == token:
            return
        raise APIError("Missing or invalid API token.", HTTPStatus.UNAUTHORIZED)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        if length > 8 * 1024 * 1024:
            raise APIError("Request body is too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise APIError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise APIError("JSON body must be an object.")
        return data

    def _send_error(self, message: str, status: HTTPStatus) -> None:
        self._send_json({"error": message}, status=status)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(_json_safe(payload), indent=2, sort_keys=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-LLM-Ingest-Token")
        self.end_headers()
        self.wfile.write(raw)


def convert_payload(payload: dict[str, Any]) -> dict[str, Any]:
    import llm_ingest

    input_value = str(payload.get("input_path") or "").strip()
    if not input_value:
        raise APIError("input_path is required.")
    input_path = Path(input_value).expanduser()
    if not input_path.exists():
        raise APIError(f"Input path does not exist: {input_path}", HTTPStatus.NOT_FOUND)

    chunk_size = _int_payload(payload, "chunk_size", 0)
    pdf_config = _pdf_config_from_payload(payload)
    write_sidecars = bool(payload.get("write_sidecars", False))

    if input_path.is_file():
        output_path = _single_output_path(input_path, payload)
        result = llm_ingest.convert_file_with_details(
            input_path,
            output_path,
            chunk_size=chunk_size,
            pdf_config=pdf_config,
            write_sidecars=write_sidecars,
        )
        return {
            "status": "ok",
            "mode": "file",
            "input_path": str(input_path),
            "output_path": str(output_path),
            "result": result,
        }

    if not input_path.is_dir():
        raise APIError(f"Input path is not a file or folder: {input_path}")

    output_dir = Path(str(payload.get("output_dir") or input_path.parent / "llm_ready")).expanduser()
    files = llm_ingest.list_supported_files(input_path, output_dir)
    batch_plan = llm_ingest.build_batch_targets(files, input_path, output_dir)
    results: list[dict[str, Any]] = []
    converted = 0
    skipped = 0
    failed = 0
    for source, target in batch_plan:
        try:
            detail = llm_ingest.convert_file_with_details(
                source,
                target,
                chunk_size=chunk_size,
                pdf_config=pdf_config,
                write_sidecars=write_sidecars,
            )
            status = str(detail.get("status", ""))
            converted += 1 if status == "converted" else 0
            skipped += 1 if status.startswith("skipped") else 0
            results.append({"input_path": str(source), "output_path": str(target), **detail})
        except Exception as exc:
            failed += 1
            results.append({"input_path": str(source), "output_path": str(target), "status": "failed", "error": str(exc)})
    return {
        "status": "ok" if failed == 0 else "partial",
        "mode": "folder",
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "file_count": len(batch_plan),
        "converted": converted,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


def graph_build_payload(payload: dict[str, Any]) -> dict[str, Any]:
    import llm_knowledge_graph

    source_value = str(payload.get("source_dir") or "").strip()
    index_value = str(payload.get("index_dir") or "").strip()
    if not source_value:
        raise APIError("source_dir is required.")
    if not index_value:
        raise APIError("index_dir is required.")
    source_dir = Path(source_value).expanduser()
    index_dir = Path(index_value).expanduser()

    report = llm_knowledge_graph.build_knowledge_graph(
        source_dir,
        index_dir,
        max_chunk_tokens=_int_payload(payload, "max_chunk_tokens", 850),
        top_terms_per_chunk=_int_payload(payload, "top_terms", 14),
        embedding_model=str(payload.get("embedding_model") or llm_knowledge_graph.DEFAULT_EMBEDDING_MODEL),
        embedding_dimensions=_int_payload(payload, "embedding_dimensions", llm_knowledge_graph.DEFAULT_EMBEDDING_DIMENSIONS),
        max_source_files=_int_payload(payload, "max_source_files", 2000),
        max_chunk_text_bytes=_int_payload(payload, "max_chunk_text_bytes", llm_knowledge_graph.DEFAULT_MAX_GRAPH_CHUNK_TEXT_BYTES),
    )
    return {"status": "ok", "report": report}


def graph_query_payload(payload: dict[str, Any]) -> dict[str, Any]:
    import llm_knowledge_graph

    index_value = str(payload.get("index_dir") or "").strip()
    query = str(payload.get("query") or payload.get("question") or "").strip()
    if not index_value:
        raise APIError("index_dir is required.")
    if not query:
        raise APIError("query is required.")
    index_dir = Path(index_value).expanduser()
    result = llm_knowledge_graph.query_knowledge_graph(
        index_dir,
        query,
        limit=_int_payload(payload, "limit", 8),
        retrieval_mode=str(payload.get("mode") or payload.get("retrieval_mode") or "hybrid"),
    )
    return {"status": "ok", "result": result}


def create_server(config: APIConfig) -> LLMIngestHTTPServer:
    if not config.allow_remote and config.host not in LOCAL_HOSTS:
        raise APIError("Refusing to bind a non-local host without --allow-remote.")
    return LLMIngestHTTPServer((config.host, config.port), config)


def _pdf_config_from_payload(payload: dict[str, Any]) -> Any:
    import llm_ingest

    security = llm_ingest.SecurityLimits(
        max_input_mb=_int_payload(payload, "max_input_mb", llm_ingest.DEFAULT_MAX_INPUT_MB),
        max_pdf_pages=_int_payload(payload, "max_pdf_pages", llm_ingest.DEFAULT_MAX_PDF_PAGES),
        max_extracted_assets=_int_payload(payload, "max_extracted_assets", llm_ingest.DEFAULT_MAX_EXTRACTED_ASSETS),
        backend_timeout_seconds=_int_payload(payload, "backend_timeout_seconds", llm_ingest.DEFAULT_BACKEND_TIMEOUT_SECONDS),
        hardened_mode=bool(payload.get("hardened_mode", True)),
        privacy_mode=bool(payload.get("privacy_mode", False)),
    )
    return llm_ingest.PDFConfig(
        ocr_language=str(payload.get("ocr_language") or "eng"),
        ocr_dpi=_int_payload(payload, "ocr_dpi", 200),
        tessdata=str(payload.get("tessdata") or "") or None,
        ocr_mode=str(payload.get("ocr_mode") or "auto"),
        pdf_backend=str(payload.get("pdf_backend") or "auto"),
        table_strategy=str(payload.get("table_strategy") or "lines_strict"),
        marker_python=str(payload.get("marker_python") or "") or None,
        security=security,
    )


def _single_output_path(input_path: Path, payload: dict[str, Any]) -> Path:
    if payload.get("output_path"):
        return Path(str(payload["output_path"])).expanduser()
    output_dir = Path(str(payload.get("output_dir") or input_path.parent / "llm_ready")).expanduser()
    return output_dir / f"{input_path.stem}.md"


def _int_payload(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise APIError(f"{key} must be an integer.") from exc


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _docs_payload() -> dict[str, Any]:
    return {
        "service": "LLM Ingest Local API",
        "version": API_VERSION,
        "local_only_default": True,
        "endpoints": {
            "GET /health": "Check that the server is running.",
            "GET /openapi.json": "Return a compact OpenAPI schema for local agent tools.",
            "POST /convert": "Convert one file or a folder to Markdown.",
            "POST /graph/build": "Build a local Markdown knowledge graph index.",
            "POST /graph/query": "Query a graph index and return an evidence pack.",
        },
        "auth": "Set LLM_INGEST_API_TOKEN or pass --token, then send Authorization: Bearer <token>.",
    }


def _openapi_payload() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "LLM Ingest Local API", "version": API_VERSION},
        "servers": [{"url": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"}],
        "paths": {
            "/health": {"get": {"summary": "Health check"}},
            "/convert": {"post": {"summary": "Convert a file or folder to Markdown"}},
            "/graph/build": {"post": {"summary": "Build a local knowledge graph"}},
            "/graph/query": {"post": {"summary": "Query a graph index for LLM evidence"}},
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "localToken": {"type": "apiKey", "in": "header", "name": "X-LLM-Ingest-Token"},
            }
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the LLM Ingest local API server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port. Defaults to 8765.")
    parser.add_argument("--token", default=os.environ.get("LLM_INGEST_API_TOKEN", ""), help="Optional bearer token.")
    parser.add_argument("--allow-remote", action="store_true", help="Allow binding to non-local hosts.")
    parser.add_argument("--debug", action="store_true", help="Return tracebacks in JSON errors.")
    parser.add_argument("--print-openapi", action="store_true", help="Print the OpenAPI schema and exit.")
    parser.add_argument("--self-test", action="store_true", help="Validate server configuration and exit.")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.print_openapi:
        print(json.dumps(_openapi_payload(), indent=2, sort_keys=True))
        return 0

    config = APIConfig(host=args.host, port=args.port, token=args.token, allow_remote=args.allow_remote, debug=args.debug)
    if args.self_test:
        create_server(APIConfig(host=args.host, port=0, token=args.token, allow_remote=args.allow_remote, debug=args.debug)).server_close()
        print(json.dumps({"status": "ok", "service": "llm-ingest-api", "host": args.host, "port": args.port}, indent=2))
        return 0

    server = create_server(config)
    actual_host, actual_port = server.server_address[:2]
    print(f"LLM Ingest API listening on http://{actual_host}:{actual_port}")
    if config.token:
        print("Authentication: bearer token required")
    else:
        print("Authentication: disabled; server is local-only by default")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LLM Ingest API")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
