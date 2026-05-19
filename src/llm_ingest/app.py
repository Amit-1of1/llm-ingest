#!/usr/bin/env python3
"""Desktop GUI for llm_ingest."""

from __future__ import annotations

import atexit
import contextlib
import ctypes
import io
import importlib.util
import json
import os
import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

import llm_ingest
import llm_backends
import llm_benchmark
import llm_knowledge_graph
from llm_ingest import PDFConfig


APP_TITLE = "LLM Ingest"
NAV_ITEMS = (
    ("workflow", "Workflow"),
    ("pdf", "PDF Settings"),
    ("diagnostics", "Diagnostics"),
    ("graph", "Knowledge Graph"),
    ("benchmark", "Benchmark"),
    ("activity", "Activity"),
)

COLORS = {
    "window": "#f2f5fb",
    "sidebar": "#eef2f8",
    "sidebar_border": "#d6deea",
    "content": "#fbfcfe",
    "card": "#ffffff",
    "card_border": "#d7e0ed",
    "text": "#172334",
    "muted": "#516179",
    "subtle": "#7f8ea7",
    "accent": "#2f6df6",
    "accent_hover": "#2458c9",
    "accent_soft": "#e7efff",
    "accent_shadow": "#c8d8ff",
    "success_bg": "#dcfce7",
    "success_fg": "#166534",
    "error_bg": "#fee2e2",
    "error_fg": "#b91c1c",
    "idle_bg": "#e9f0fb",
    "idle_fg": "#314766",
    "surface": "#f6f9fe",
    "surface_alt": "#edf3fb",
    "field": "#fdfefe",
    "field_border": "#ccd7e6",
    "field_focus": "#7ca8ff",
    "log_bg": "#f7faff",
    "log_border": "#d8e2ef",
    "button_border": "#cad6e5",
    "button_shadow": "#dde6f1",
    "button_disabled": "#eef2f7",
    "button_disabled_text": "#8a97aa",
}

FR_PRIVATE = 0x10
WM_FONTCHANGE = 0x001D
HWND_BROADCAST = 0xFFFF
_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parents[1] if _PACKAGE_ROOT.parent.name == "src" else _PACKAGE_ROOT


def _load_private_fonts() -> list[Path]:
    if not hasattr(ctypes, "windll"):
        return []

    font_dir = _PROJECT_ROOT / "assets" / "fonts"
    if not font_dir.exists():
        return []

    loaded: list[Path] = []
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    for font_path in sorted(font_dir.glob("Poppins-*.ttf")):
        added = gdi32.AddFontResourceExW(str(font_path), FR_PRIVATE, 0)
        if added:
            loaded.append(font_path)

    if loaded:
        user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
    return loaded


def _unload_private_fonts(fonts: list[Path]) -> None:
    if not fonts or not hasattr(ctypes, "windll"):
        return

    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    for font_path in fonts:
        gdi32.RemoveFontResourceExW(str(font_path), FR_PRIVATE, 0)
    user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)


def _pick_font_family(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for candidate in (
        "Poppins",
        "Poppins Medium",
        "Segoe UI Variable Text",
        "Segoe UI Variable",
        "Segoe UI",
    ):
        if candidate in available:
            return candidate
    return "TkDefaultFont"


def _rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]


class QueueWriter(io.TextIOBase):
    def __init__(self, log_queue: queue.Queue[tuple[str, str]]) -> None:
        self.log_queue = log_queue

    def write(self, text: str) -> int:
        if text:
            self.log_queue.put(("log", text))
        return len(text)

    def flush(self) -> None:
        return None


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        font: tuple[str, int, str],
        variant: str = "secondary",
        selected: bool = False,
        min_width: int = 0,
        height: int = 46,
        pad_x: int = 24,
    ) -> None:
        super().__init__(
            parent,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
            relief="flat",
            takefocus=0,
            cursor="hand2",
            height=height + 4,
        )
        self.command = command
        self.text = text
        self.font = font
        self.variant = variant
        self.selected = selected
        self.enabled = True
        self.hovered = False
        self.pressed = False
        self.height_px = height
        self.radius = max(18, height // 2)
        self.pad_x = pad_x
        self.min_width = min_width
        self.font_obj = tkfont.Font(font=font)

        measured = self.font_obj.measure(text) + (pad_x * 2)
        self.configure(width=max(min_width, measured))

        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", lambda _event: self._set_hover(True))
        self.bind("<Leave>", lambda _event: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _palette(self) -> dict[str, str | int]:
        if not self.enabled:
            return {
                "fill": COLORS["button_disabled"],
                "border": COLORS["button_border"],
                "shadow": COLORS["button_shadow"],
                "text": COLORS["button_disabled_text"],
                "offset": 2,
            }

        if self.variant == "accent":
            fill = COLORS["accent_hover"] if self.hovered else COLORS["accent"]
            if self.pressed:
                fill = COLORS["accent_hover"]
            return {
                "fill": fill,
                "border": fill,
                "shadow": COLORS["accent_shadow"],
                "text": "#ffffff",
                "offset": 3 if not self.pressed else 1,
            }

        if self.variant == "toggle" and self.selected:
            fill = COLORS["accent_soft"]
            if self.hovered:
                fill = "#dce9ff"
            return {
                "fill": fill,
                "border": COLORS["accent"],
                "shadow": "#d8e4ff",
                "text": COLORS["accent"],
                "offset": 3 if not self.pressed else 1,
            }

        fill = "#ffffff" if not self.hovered else COLORS["surface_alt"]
        return {
            "fill": fill,
            "border": COLORS["button_border"],
            "shadow": COLORS["button_shadow"],
            "text": COLORS["text"],
            "offset": 3 if not self.pressed else 1,
        }

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), int(self.cget("width")))
        height = self.height_px
        palette = self._palette()
        offset = int(palette["offset"])

        shadow_points = _rounded_points(0, offset, width - 1, height + offset, self.radius)
        self.create_polygon(
            shadow_points,
            smooth=True,
            fill=str(palette["shadow"]),
            outline="",
        )

        fill_points = _rounded_points(0, 0, width - 1, height, self.radius)
        self.create_polygon(
            fill_points,
            smooth=True,
            fill=str(palette["fill"]),
            outline=str(palette["border"]),
            width=1,
        )

        self.create_text(
            width / 2,
            (height / 2) + 1,
            text=self.text,
            fill=str(palette["text"]),
            font=self.font,
        )

    def _set_hover(self, hovered: bool) -> None:
        self.hovered = hovered and self.enabled
        if self.enabled:
            self.configure(cursor="hand2")
        self._draw()

    def _on_press(self, _event) -> None:
        if not self.enabled:
            return
        self.pressed = True
        self._draw()

    def _on_release(self, event) -> None:
        if not self.enabled:
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self.pressed = False
        self._draw()
        if inside and callable(self.command):
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._draw()

    def set_text(self, text: str) -> None:
        self.text = text
        measured = self.font_obj.measure(text) + (self.pad_x * 2)
        self.configure(width=max(self.min_width, measured))
        self._draw()


class IngestApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1320x900")
        self.root.minsize(1120, 760)
        self.root.configure(bg=COLORS["window"])

        self.font_family = _pick_font_family(root)
        self.title_font = (self.font_family, 22, "bold")
        self.subtitle_font = (self.font_family, 10, "normal")
        self.section_font = (self.font_family, 13, "bold")
        self.label_font = (self.font_family, 9, "normal")
        self.body_font = (self.font_family, 10, "normal")
        self.body_bold_font = (self.font_family, 10, "bold")
        self.caption_font = (self.font_family, 9, "normal")
        self.button_font = (self.font_family, 10, "bold")
        self.badge_font = (self.font_family, 9, "bold")

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.control_widgets: list[object] = []
        self.nav_buttons: dict[str, RoundedButton] = {}
        self.page_frames: dict[str, tk.Frame] = {}
        self.workflow_inner: tk.Frame | None = None
        self.workflow_cards: dict[tuple[int, int], tk.Frame] = {}
        self.workflow_canvas: tk.Canvas | None = None
        self.workflow_window: int | None = None
        self.audit_tree: ttk.Treeview | None = None
        self.audit_status_lines: list[tk.Label] = []
        self.last_audit_report: llm_ingest.AuditReport | None = None
        self.kg_tree: ttk.Treeview | None = None
        self.kg_results_text: tk.Text | None = None
        self.last_kg_report: llm_knowledge_graph.KGReport | None = None

        self.input_mode = tk.StringVar(value="file")
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.chunk_size = tk.StringVar(value="0")
        self.ocr_language = tk.StringVar(value="eng")
        self.ocr_dpi = tk.StringVar(value="200")
        self.tessdata = tk.StringVar()
        self.ocr_mode = tk.StringVar(value="auto")
        self.pdf_backend = tk.StringVar(value="auto")
        self.table_strategy = tk.StringVar(value="lines_strict")
        self.hardened_mode = tk.BooleanVar(value=True)
        self.privacy_mode = tk.BooleanVar(value=False)
        self.write_sidecars = tk.BooleanVar(value=False)
        self.allow_external_marker_python = tk.BooleanVar(value=False)
        self.backend_timeout_seconds = tk.StringVar(value=str(llm_ingest.DEFAULT_BACKEND_TIMEOUT_SECONDS))
        self.max_input_mb = tk.StringVar(value=str(llm_ingest.DEFAULT_MAX_INPUT_MB))
        self.max_pdf_pages = tk.StringVar(value=str(llm_ingest.DEFAULT_MAX_PDF_PAGES))
        self.max_extracted_assets = tk.StringVar(value=str(llm_ingest.DEFAULT_MAX_EXTRACTED_ASSETS))
        self.active_page = tk.StringVar(value="workflow")
        self.audit_manifest_path = tk.StringVar()
        self.audit_cache_dir = tk.StringVar()
        self.audit_report_dir = tk.StringVar()
        self.audit_baseline_dir = tk.StringVar()
        self.audit_backends = tk.StringVar(value=llm_ingest.DEFAULT_AUDIT_BACKENDS)
        self.audit_download_missing = tk.BooleanVar(value=True)
        self.audit_summary_text = tk.StringVar(value="No audit has been run yet.")
        self.kg_source_dir = tk.StringVar()
        self.kg_index_dir = tk.StringVar()
        self.kg_max_chunk_tokens = tk.StringVar(value="850")
        self.kg_top_terms = tk.StringVar(value="14")
        self.kg_embedding_model = tk.StringVar(value=llm_knowledge_graph.DEFAULT_EMBEDDING_MODEL)
        self.kg_embedding_dimensions = tk.StringVar(value=str(llm_knowledge_graph.DEFAULT_EMBEDDING_DIMENSIONS))
        self.kg_max_source_files = tk.StringVar(value="2000")
        self.kg_max_chunk_text_bytes = tk.StringVar(value=str(llm_knowledge_graph.DEFAULT_MAX_GRAPH_CHUNK_TEXT_BYTES))
        self.kg_query = tk.StringVar()
        self.kg_limit = tk.StringVar(value="8")
        self.kg_retrieval_mode = tk.StringVar(value="hybrid")
        self.kg_summary_text = tk.StringVar(value="No graph has been built yet.")
        self.benchmark_output_dir = tk.StringVar()
        self.benchmark_questions_path = tk.StringVar()
        self.benchmark_summary_text = tk.StringVar(value="No benchmark has been run yet.")

        self.summary_vars = {
            "Mode": tk.StringVar(value="Single file"),
            "Input": tk.StringVar(value="Not selected"),
            "Output": tk.StringVar(value="Not selected"),
            "Chunk size": tk.StringVar(value="0"),
            "PDF backend": tk.StringVar(value="Auto"),
        }

        self.status_text = tk.StringVar(value="Ready")
        self.progress_text = tk.StringVar(value="No active run")

        self._build_shell()
        self._set_default_paths()
        self._wire_variable_updates()
        self._refresh_summary()
        self._refresh_diagnostics_health()
        self._set_status("Ready", "idle")
        self._poll_log_queue()

    def _build_shell(self) -> None:
        shell = tk.Frame(self.root, bg=COLORS["window"])
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(2, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        sidebar = self._build_sidebar(shell)
        sidebar.grid(row=0, column=0, sticky="nsw")

        divider = tk.Frame(shell, bg=COLORS["sidebar_border"], width=1)
        divider.grid(row=0, column=1, sticky="ns")

        content = tk.Frame(shell, bg=COLORS["content"])
        content.grid(row=0, column=2, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        header = self._build_header(content)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        page_host = tk.Frame(content, bg=COLORS["content"])
        page_host.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        page_host.grid_columnconfigure(0, weight=1)
        page_host.grid_rowconfigure(0, weight=1)

        self._build_pages(page_host)
        self._show_page("workflow")

    def _build_sidebar(self, parent: tk.Misc) -> tk.Frame:
        sidebar = tk.Frame(parent, bg=COLORS["sidebar"], width=236, padx=18, pady=20)
        sidebar.grid_propagate(False)

        brand = tk.Label(
            sidebar,
            text=APP_TITLE,
            bg=COLORS["sidebar"],
            fg=COLORS["text"],
            font=(self.font_family, 20, "bold"),
            anchor="w",
        )
        brand.pack(fill="x")

        strap = tk.Label(
            sidebar,
            text="Desktop workflow for turning local research papers into clean Markdown.",
            bg=COLORS["sidebar"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            wraplength=205,
            anchor="w",
        )
        strap.pack(fill="x", pady=(8, 22))

        for key, label in NAV_ITEMS:
            button = RoundedButton(
                sidebar,
                label,
                lambda page=key: self._show_page(page),
                font=self.button_font,
                variant="toggle",
                min_width=182,
                height=42,
            )
            button.pack(fill="x", pady=6)
            self.nav_buttons[key] = button

        sidebar.pack_propagate(False)
        return sidebar

    def _build_header(self, parent: tk.Misc) -> tk.Frame:
        header = tk.Frame(parent, bg=COLORS["content"])
        header.grid_columnconfigure(0, weight=1)

        text_col = tk.Frame(header, bg=COLORS["content"])
        text_col.grid(row=0, column=0, sticky="ew", padx=(0, 16))

        self.header_title = tk.Label(
            text_col,
            text="Research paper ingest workspace",
            bg=COLORS["content"],
            fg=COLORS["text"],
            font=self.title_font,
            anchor="w",
            justify="left",
        )
        self.header_title.pack(fill="x")

        self.header_subtitle = tk.Label(
            text_col,
            text="Pick a file or folder, tune the PDF pipeline, and export LLM-ready Markdown with clearer controls and more readable defaults.",
            bg=COLORS["content"],
            fg=COLORS["muted"],
            font=self.subtitle_font,
            anchor="w",
            justify="left",
        )
        self.header_subtitle.pack(fill="x", pady=(8, 0))

        actions = tk.Frame(header, bg=COLORS["content"])
        actions.grid(row=0, column=1, sticky="e")

        self.status_badge = tk.Label(
            actions,
            textvariable=self.status_text,
            bg=COLORS["idle_bg"],
            fg=COLORS["idle_fg"],
            font=self.badge_font,
            padx=12,
            pady=7,
        )
        self.status_badge.pack(side="left", padx=(0, 12))

        self.clear_button = RoundedButton(
            actions,
            "Clear log",
            self._clear_log,
            font=self.button_font,
            variant="secondary",
            min_width=108,
            height=42,
        )
        self.clear_button.pack(side="left", padx=(0, 10))

        self.stop_button = RoundedButton(
            actions,
            "Stop run",
            self._request_stop,
            font=self.button_font,
            variant="secondary",
            min_width=106,
            height=42,
        )
        self.stop_button.pack(side="left", padx=(0, 10))

        self.run_button = RoundedButton(
            actions,
            "Run ingest",
            self._start_run,
            font=self.button_font,
            variant="accent",
            min_width=118,
            height=42,
        )
        self.run_button.pack(side="left")

        header.bind("<Configure>", self._sync_header_wrap)
        return header

    def _build_pages(self, parent: tk.Misc) -> None:
        workflow = self._build_workflow_page(parent)
        workflow.grid(row=0, column=0, sticky="nsew")
        self.page_frames["workflow"] = workflow

        pdf = tk.Frame(parent, bg=COLORS["content"])
        pdf.grid(row=0, column=0, sticky="nsew")
        pdf.grid_columnconfigure(0, weight=1)
        pdf.grid_rowconfigure(0, weight=1)
        self._pdf_card(pdf).grid(row=0, column=0, sticky="nsew")
        self.page_frames["pdf"] = pdf

        diagnostics = tk.Frame(parent, bg=COLORS["content"])
        diagnostics.grid(row=0, column=0, sticky="nsew")
        diagnostics.grid_columnconfigure(0, weight=1)
        diagnostics.grid_rowconfigure(0, weight=1)
        self._diagnostics_page(diagnostics).grid(row=0, column=0, sticky="nsew")
        self.page_frames["diagnostics"] = diagnostics

        graph = tk.Frame(parent, bg=COLORS["content"])
        graph.grid(row=0, column=0, sticky="nsew")
        graph.grid_columnconfigure(0, weight=1)
        graph.grid_rowconfigure(0, weight=1)
        self._knowledge_graph_page(graph).grid(row=0, column=0, sticky="nsew")
        self.page_frames["graph"] = graph

        benchmark = tk.Frame(parent, bg=COLORS["content"])
        benchmark.grid(row=0, column=0, sticky="nsew")
        benchmark.grid_columnconfigure(0, weight=1)
        benchmark.grid_rowconfigure(0, weight=1)
        self._benchmark_page(benchmark).grid(row=0, column=0, sticky="nsew")
        self.page_frames["benchmark"] = benchmark

        activity = tk.Frame(parent, bg=COLORS["content"])
        activity.grid(row=0, column=0, sticky="nsew")
        activity.grid_columnconfigure(0, weight=1)
        activity.grid_rowconfigure(0, weight=1)
        self._activity_card(activity).grid(row=0, column=0, sticky="nsew")
        self.page_frames["activity"] = activity

    def _build_workflow_page(self, parent: tk.Misc) -> tk.Frame:
        outer = tk.Frame(parent, bg=COLORS["content"])
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            outer,
            bg=COLORS["content"],
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = tk.Frame(canvas, bg=COLORS["content"])
        inner.grid_columnconfigure(0, weight=1, uniform="workflow-columns")
        inner.grid_columnconfigure(1, weight=1, uniform="workflow-columns")

        self.workflow_inner = inner
        self.workflow_canvas = canvas
        self.workflow_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", self._sync_workflow_scrollregion)
        canvas.bind("<Configure>", self._sync_workflow_width)
        canvas.bind("<Enter>", self._bind_workflow_mousewheel)
        canvas.bind("<Leave>", self._unbind_workflow_mousewheel)

        self.workflow_cards[(0, 0)] = self._job_card(inner)
        self.workflow_cards[(1, 0)] = self._processing_card(inner)
        self.workflow_cards[(0, 1)] = self._summary_card(inner)
        self.workflow_cards[(1, 1)] = self._guidance_card(inner)

        self.workflow_cards[(0, 0)].grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 12))
        self.workflow_cards[(1, 0)].grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.workflow_cards[(0, 1)].grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 12))
        self.workflow_cards[(1, 1)].grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        return outer

    def _sync_workflow_scrollregion(self, _event=None) -> None:
        self._sync_workflow_card_sizes()
        if self.workflow_canvas is None:
            return
        self.workflow_canvas.configure(scrollregion=self.workflow_canvas.bbox("all"))

    def _sync_workflow_width(self, event) -> None:
        if self.workflow_canvas is None or self.workflow_window is None:
            return
        self.workflow_canvas.itemconfigure(self.workflow_window, width=event.width)

    def _bind_workflow_mousewheel(self, _event=None) -> None:
        self.root.bind_all("<MouseWheel>", self._on_workflow_mousewheel)

    def _unbind_workflow_mousewheel(self, _event=None) -> None:
        self.root.unbind_all("<MouseWheel>")

    def _on_workflow_mousewheel(self, event) -> None:
        if self.workflow_canvas is None:
            return
        self.workflow_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _sync_workflow_card_sizes(self) -> None:
        if self.workflow_inner is None or not self.workflow_cards:
            return

        for row in (0, 1):
            row_cards = [
                card
                for (card_row, _card_col), card in self.workflow_cards.items()
                if card_row == row
            ]
            if not row_cards:
                continue
            max_height = max(card.winfo_reqheight() for card in row_cards)
            self.workflow_inner.grid_rowconfigure(row, minsize=max_height)

    def _bind_wrap_to_width(self, widget: tk.Label, min_width: int = 120, inset: int = 0) -> None:
        def _update(event) -> None:
            widget.configure(wraplength=max(event.width - inset, min_width))

        widget.bind("<Configure>", _update)

    def _card(self, parent: tk.Misc, title: str) -> tuple[tk.Frame, tk.Frame]:
        frame = tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightbackground=COLORS["card_border"],
            highlightthickness=1,
            padx=18,
            pady=18,
        )
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        title_label = tk.Label(
            frame,
            text=title,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=self.section_font,
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="w", pady=(0, 14))

        body = tk.Frame(frame, bg=COLORS["card"])
        body.grid(row=1, column=0, sticky="nsew")
        return frame, body

    def _job_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Input and output")
        body.grid_columnconfigure(0, weight=1)

        self._field_label(body, "Mode").grid(row=0, column=0, sticky="w")
        mode_row = tk.Frame(body, bg=COLORS["card"])
        mode_row.grid(row=1, column=0, sticky="w", pady=(10, 18))

        self.mode_file_button = RoundedButton(
            mode_row,
            "Single file",
            lambda: self._set_mode("file"),
            font=self.button_font,
            variant="toggle",
            selected=True,
            min_width=132,
            height=40,
        )
        self.mode_file_button.pack(side="left", padx=(0, 10))

        self.mode_folder_button = RoundedButton(
            mode_row,
            "Folder batch",
            lambda: self._set_mode("folder"),
            font=self.button_font,
            variant="toggle",
            min_width=140,
            height=40,
        )
        self.mode_folder_button.pack(side="left")
        self.control_widgets.extend([self.mode_file_button, self.mode_folder_button])

        self._path_field(body, 2, "Input", self.input_path, self._browse_input)
        self._path_field(body, 4, "Output", self.output_path, self._browse_output)
        return card

    def _summary_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Current setup")
        body.grid_columnconfigure(1, weight=1)

        for row, (label, value_var) in enumerate(self.summary_vars.items()):
            pill = tk.Label(
                body,
                text=label,
                bg=COLORS["surface_alt"],
                fg=COLORS["muted"],
                font=self.caption_font,
                padx=12,
                pady=6,
            )
            pill.grid(row=row, column=0, sticky="nw", pady=5)

            value = tk.Label(
                body,
                textvariable=value_var,
                bg=COLORS["card"],
                fg=COLORS["text"],
                font=self.body_font,
                justify="left",
                anchor="w",
            )
            value.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
            self._bind_wrap_to_width(value, min_width=180)

        note = tk.Label(
            body,
            text="Paths wrap to the available panel width so the workflow stays readable.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        note.grid(row=len(self.summary_vars), column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self._bind_wrap_to_width(note, min_width=220)
        return card

    def _processing_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Processing")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._field_label(body, "Chunk size").grid(row=0, column=0, sticky="w")
        chunk_entry = self._entry(body, self.chunk_size)
        chunk_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 18))

        self._field_label(body, "PDF backend").grid(row=0, column=1, sticky="w")
        backend = self._dropdown(body, self.pdf_backend, llm_ingest.SUPPORTED_PDF_BACKENDS)
        backend.grid(row=1, column=1, sticky="ew", pady=(10, 18))

        self._field_label(body, "Table strategy").grid(row=2, column=0, sticky="w")
        strategy = self._dropdown(body, self.table_strategy, ("lines_strict", "lines", "text", "none"))
        strategy.grid(row=3, column=0, sticky="ew", padx=(0, 10))

        info = tk.Label(
            body,
            text="Use `lines_strict` as the default. Switch to `text` when ruled tables are sparse or missing. Choose `marker` for the hardest formula-heavy PDFs when that stack is installed.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        info.grid(row=3, column=1, sticky="nw", pady=(2, 0))
        self._bind_wrap_to_width(info, min_width=180)

        self.control_widgets.extend([chunk_entry, backend, strategy])
        return card

    def _pdf_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "PDF options")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._field_label(body, "OCR mode").grid(row=0, column=0, sticky="w")
        ocr_mode_menu = self._dropdown(body, self.ocr_mode, ("auto", "full", "off"))
        ocr_mode_menu.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(10, 18))

        self._field_label(body, "OCR language").grid(row=0, column=1, sticky="w")
        language_entry = self._entry(body, self.ocr_language)
        language_entry.grid(row=1, column=1, sticky="ew", pady=(10, 18))

        self._field_label(body, "OCR DPI").grid(row=2, column=0, sticky="w")
        dpi_entry = self._entry(body, self.ocr_dpi)
        dpi_entry.grid(row=3, column=0, sticky="ew", padx=(0, 12), pady=(10, 18))

        self._field_label(body, "Tessdata").grid(row=2, column=1, sticky="w")
        tess_row = tk.Frame(body, bg=COLORS["card"])
        tess_row.grid(row=3, column=1, sticky="ew", pady=(10, 18))
        tess_row.grid_columnconfigure(0, weight=1)

        tess_entry = self._entry(tess_row, self.tessdata)
        tess_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        browse_button = RoundedButton(
            tess_row,
            "Browse",
            self._browse_tessdata,
            font=self.button_font,
            variant="secondary",
            min_width=102,
            height=40,
        )
        browse_button.grid(row=0, column=1, sticky="e")

        note = tk.Label(
            body,
            text="Set a tessdata folder only when OCR language packs live outside the normal Tesseract install path.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        note.grid(row=4, column=0, columnspan=2, sticky="ew")
        self._bind_wrap_to_width(note, min_width=260)

        safety = tk.Frame(body, bg=COLORS["card"])
        safety.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        safety.grid_columnconfigure(0, weight=1)
        safety.grid_columnconfigure(1, weight=1)
        safety.grid_columnconfigure(2, weight=1)
        safety.grid_columnconfigure(3, weight=1)

        self._field_label(safety, "Backend timeout").grid(row=0, column=0, sticky="w")
        timeout_entry = self._entry(safety, self.backend_timeout_seconds)
        timeout_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 16))

        self._field_label(safety, "Max file MB").grid(row=0, column=1, sticky="w")
        max_file_entry = self._entry(safety, self.max_input_mb)
        max_file_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(10, 16))

        self._field_label(safety, "Max PDF pages").grid(row=0, column=2, sticky="w")
        max_pages_entry = self._entry(safety, self.max_pdf_pages)
        max_pages_entry.grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(10, 16))

        self._field_label(safety, "Max assets").grid(row=0, column=3, sticky="w")
        max_assets_entry = self._entry(safety, self.max_extracted_assets)
        max_assets_entry.grid(row=1, column=3, sticky="ew", pady=(10, 16))

        toggles = tk.Frame(body, bg=COLORS["card"])
        toggles.grid(row=6, column=0, columnspan=2, sticky="ew")
        hardened_toggle = self._checkbutton(toggles, "Hardened mode", self.hardened_mode)
        hardened_toggle.pack(side="left", padx=(0, 18))
        privacy_toggle = self._checkbutton(toggles, "Privacy mode", self.privacy_mode)
        privacy_toggle.pack(side="left", padx=(0, 18))
        sidecar_toggle = self._checkbutton(toggles, "Write JSON sidecars", self.write_sidecars)
        sidecar_toggle.pack(side="left", padx=(0, 18))
        external_marker_toggle = self._checkbutton(toggles, "Allow external Marker Python", self.allow_external_marker_python)
        external_marker_toggle.pack(side="left")

        self.control_widgets.extend(
            [
                ocr_mode_menu,
                language_entry,
                dpi_entry,
                tess_entry,
                browse_button,
                timeout_entry,
                max_file_entry,
                max_pages_entry,
                max_assets_entry,
                hardened_toggle,
                privacy_toggle,
                sidecar_toggle,
                external_marker_toggle,
            ]
        )
        return card

    def _diagnostics_page(self, parent: tk.Misc) -> tk.Frame:
        page = tk.Frame(parent, bg=COLORS["content"])
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        top = tk.Frame(page, bg=COLORS["content"])
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)

        self._diagnostics_health_card(top).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._diagnostics_corpus_card(top).grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._diagnostics_results_card(page).grid(row=1, column=0, sticky="nsew")
        return page

    def _diagnostics_health_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Backend health")
        body.grid_columnconfigure(0, weight=1)

        intro = tk.Label(
            body,
            text="This panel reflects what the app can actually run right now, not just what is importable.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._bind_wrap_to_width(intro, min_width=260)

        for row in range(8):
            label = tk.Label(
                body,
                text="",
                bg=COLORS["surface"],
                fg=COLORS["text"],
                font=self.caption_font,
                justify="left",
                anchor="w",
                padx=12,
                pady=8,
            )
            label.grid(row=row + 1, column=0, sticky="ew", pady=3)
            self._bind_wrap_to_width(label, min_width=260)
            self.audit_status_lines.append(label)
        return card

    def _diagnostics_corpus_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Sample corpus")
        body.grid_columnconfigure(0, weight=1)

        self._path_field(body, 0, "Manifest", self.audit_manifest_path, self._browse_audit_manifest)
        self._path_field(body, 2, "Cache dir", self.audit_cache_dir, self._browse_audit_cache)
        self._path_field(body, 4, "Report dir", self.audit_report_dir, self._browse_audit_report_dir)
        self._path_field(body, 6, "Baseline dir", self.audit_baseline_dir, self._browse_audit_baseline)

        self._field_label(body, "Backends").grid(row=8, column=0, sticky="w")
        backend_entry = self._entry(body, self.audit_backends)
        backend_entry.grid(row=9, column=0, sticky="ew", pady=(10, 18))

        download_toggle = tk.Checkbutton(
            body,
            text="Download missing public audit PDFs before running",
            variable=self.audit_download_missing,
            bg=COLORS["card"],
            fg=COLORS["text"],
            activebackground=COLORS["card"],
            activeforeground=COLORS["text"],
            selectcolor=COLORS["field"],
            font=self.caption_font,
            anchor="w",
        )
        download_toggle.grid(row=10, column=0, sticky="w")

        summary = tk.Label(
            body,
            textvariable=self.audit_summary_text,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        summary.grid(row=11, column=0, sticky="ew", pady=(12, 12))
        self._bind_wrap_to_width(summary, min_width=260)

        actions = tk.Frame(body, bg=COLORS["card"])
        actions.grid(row=12, column=0, sticky="w")

        self.audit_run_button = RoundedButton(
            actions,
            "Run audit",
            self._start_audit,
            font=self.button_font,
            variant="accent",
            min_width=108,
            height=40,
        )
        self.audit_run_button.pack(side="left", padx=(0, 10))

        self.audit_refresh_button = RoundedButton(
            actions,
            "Refresh health",
            self._refresh_diagnostics_health,
            font=self.button_font,
            variant="secondary",
            min_width=132,
            height=40,
        )
        self.audit_refresh_button.pack(side="left")

        self.audit_open_summary_button = RoundedButton(
            actions,
            "Open summary",
            self._open_latest_audit_summary,
            font=self.button_font,
            variant="secondary",
            min_width=132,
            height=40,
        )
        self.audit_open_summary_button.pack(side="left", padx=(10, 0))

        self.control_widgets.extend([backend_entry, download_toggle, self.audit_run_button, self.audit_refresh_button, self.audit_open_summary_button])
        return card

    def _diagnostics_results_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Audit results")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        with contextlib.suppress(tk.TclError):
            style.theme_use("clam")
        style.configure(
            "Audit.Treeview",
            background=COLORS["card"],
            fieldbackground=COLORS["card"],
            foreground=COLORS["text"],
            rowheight=24,
            font=self.caption_font,
        )
        style.configure(
            "Audit.Treeview.Heading",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            font=self.body_bold_font,
            relief="flat",
        )

        columns = ("sample", "source", "backend", "used", "status", "tokens", "assets", "issues")
        tree = ttk.Treeview(body, columns=columns, show="headings", style="Audit.Treeview")
        tree.grid(row=0, column=0, sticky="nsew")
        self.audit_tree = tree

        headings = {
            "sample": ("Sample", 260),
            "source": ("Source", 80),
            "backend": ("Requested", 92),
            "used": ("Used", 92),
            "status": ("Status", 84),
            "tokens": ("Tokens", 80),
            "assets": ("Assets", 70),
            "issues": ("Issues", 70),
        }
        for key, (label, width) in headings.items():
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=width // 2, stretch=key == "sample")

        scrollbar = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        return card

    def _knowledge_graph_page(self, parent: tk.Misc) -> tk.Frame:
        page = tk.Frame(parent, bg=COLORS["content"])
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        paned = tk.PanedWindow(
            page,
            orient="vertical",
            bg=COLORS["content"],
            bd=0,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        paned.grid(row=0, column=0, sticky="nsew")

        top_shell = tk.Frame(paned, bg=COLORS["content"])
        top_shell.grid_columnconfigure(0, weight=1)
        top_shell.grid_rowconfigure(0, weight=1)

        top_canvas = tk.Canvas(
            top_shell,
            bg=COLORS["content"],
            bd=0,
            highlightthickness=0,
            yscrollincrement=18,
        )
        top_scroll = tk.Scrollbar(top_shell, orient="vertical", command=top_canvas.yview)
        top_canvas.grid(row=0, column=0, sticky="nsew")
        top_scroll.grid(row=0, column=1, sticky="ns")
        top_canvas.configure(yscrollcommand=top_scroll.set)

        top = tk.Frame(top_canvas, bg=COLORS["content"])
        top_window = top_canvas.create_window((0, 0), window=top, anchor="nw")
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)
        top.bind(
            "<Configure>",
            lambda event: top_canvas.configure(scrollregion=top_canvas.bbox("all")),
        )
        top_canvas.bind(
            "<Configure>",
            lambda event: top_canvas.itemconfigure(top_window, width=max(1, event.width)),
        )

        self._kg_build_card(top).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._kg_query_card(top).grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        results = self._kg_results_card(paned)
        paned.add(top_shell, minsize=260, height=360)
        paned.add(results, minsize=220)
        return page

    def _kg_build_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Graph builder")
        body.grid_columnconfigure(0, weight=1)

        self._path_field(body, 0, "Markdown source", self.kg_source_dir, self._browse_kg_source)
        self._path_field(body, 2, "Graph index", self.kg_index_dir, self._browse_kg_index)

        action_row = tk.Frame(body, bg=COLORS["card"])
        action_row.grid(row=4, column=0, sticky="ew", pady=(0, 14))
        action_row.grid_columnconfigure(0, weight=1)

        summary = tk.Label(
            action_row,
            textvariable=self.kg_summary_text,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        summary.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._bind_wrap_to_width(summary, min_width=220)

        self.kg_build_button = RoundedButton(
            action_row,
            "Build graph",
            self._start_kg_build,
            font=self.button_font,
            variant="accent",
            min_width=120,
            height=40,
        )
        self.kg_build_button.grid(row=0, column=1, sticky="e")

        self.kg_open_context_button = RoundedButton(
            action_row,
            "Open context",
            self._open_graph_context,
            font=self.button_font,
            variant="secondary",
            min_width=124,
            height=40,
        )
        self.kg_open_context_button.grid(row=0, column=2, sticky="e", padx=(10, 0))

        settings = tk.Frame(body, bg=COLORS["card"])
        settings.grid(row=5, column=0, sticky="ew")
        settings.grid_columnconfigure(0, weight=1)
        settings.grid_columnconfigure(1, weight=1)

        self._field_label(settings, "Max chunk tokens").grid(row=0, column=0, sticky="w")
        max_tokens_entry = self._entry(settings, self.kg_max_chunk_tokens)
        max_tokens_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 18))

        self._field_label(settings, "Terms per chunk").grid(row=0, column=1, sticky="w")
        terms_entry = self._entry(settings, self.kg_top_terms)
        terms_entry.grid(row=1, column=1, sticky="ew", pady=(10, 18))

        vector_settings = tk.Frame(body, bg=COLORS["card"])
        vector_settings.grid(row=6, column=0, sticky="ew")
        vector_settings.grid_columnconfigure(0, weight=1)
        vector_settings.grid_columnconfigure(1, weight=1)

        self._field_label(vector_settings, "Embedding model").grid(row=0, column=0, sticky="w")
        embedding_menu = self._dropdown(vector_settings, self.kg_embedding_model, llm_knowledge_graph.SUPPORTED_EMBEDDING_MODELS)
        embedding_menu.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 18))

        self._field_label(vector_settings, "Vector dimensions").grid(row=0, column=1, sticky="w")
        dimensions_entry = self._entry(vector_settings, self.kg_embedding_dimensions)
        dimensions_entry.grid(row=1, column=1, sticky="ew", pady=(10, 18))

        limits = tk.Frame(body, bg=COLORS["card"])
        limits.grid(row=7, column=0, sticky="ew")
        limits.grid_columnconfigure(0, weight=1)
        limits.grid_columnconfigure(1, weight=1)

        self._field_label(limits, "Max source files").grid(row=0, column=0, sticky="w")
        max_files_entry = self._entry(limits, self.kg_max_source_files)
        max_files_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 18))

        self._field_label(limits, "Max text bytes").grid(row=0, column=1, sticky="w")
        max_text_entry = self._entry(limits, self.kg_max_chunk_text_bytes)
        max_text_entry.grid(row=1, column=1, sticky="ew", pady=(10, 18))

        self.control_widgets.extend([max_tokens_entry, terms_entry, embedding_menu, dimensions_entry, max_files_entry, max_text_entry, self.kg_build_button, self.kg_open_context_button])
        return card

    def _kg_query_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Graph query")
        body.grid_columnconfigure(0, weight=1)

        self._field_label(body, "Question").grid(row=0, column=0, sticky="w")
        query_entry = self._entry(body, self.kg_query)
        query_entry.grid(row=1, column=0, sticky="ew", pady=(10, 18))
        query_entry.bind("<Return>", lambda _event: self._start_kg_query())

        row = tk.Frame(body, bg=COLORS["card"])
        row.grid(row=2, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)

        row.grid_columnconfigure(1, weight=1)

        self._field_label(row, "Evidence chunks").grid(row=0, column=0, sticky="w")
        limit_entry = self._entry(row, self.kg_limit)
        limit_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 18))

        self._field_label(row, "Retrieval mode").grid(row=0, column=1, sticky="w")
        mode_menu = self._dropdown(row, self.kg_retrieval_mode, ("hybrid", "lexical", "vector"))
        mode_menu.grid(row=1, column=1, sticky="ew", pady=(10, 18))

        query_actions = tk.Frame(body, bg=COLORS["card"])
        query_actions.grid(row=3, column=0, sticky="w")

        self.kg_query_button = RoundedButton(
            query_actions,
            "Query graph",
            self._start_kg_query,
            font=self.button_font,
            variant="secondary",
            min_width=120,
            height=40,
        )
        self.kg_query_button.pack(side="left")

        self.kg_open_query_button = RoundedButton(
            query_actions,
            "Open last query",
            self._open_last_query,
            font=self.button_font,
            variant="secondary",
            min_width=142,
            height=40,
        )
        self.kg_open_query_button.pack(side="left", padx=(10, 0))

        note = tk.Label(
            body,
            text="Queries return a compact evidence pack from chunks plus graph metadata. The latest pack is written to last_query.md in the graph index.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        note.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self._bind_wrap_to_width(note, min_width=260)

        self.control_widgets.extend([query_entry, limit_entry, mode_menu, self.kg_query_button, self.kg_open_query_button])
        return card

    def _kg_results_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Graph results")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        columns = ("path", "heading", "score", "flags", "terms")
        tree = ttk.Treeview(body, columns=columns, show="headings", style="Audit.Treeview")
        tree.configure(height=10)
        tree.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.kg_tree = tree

        headings = {
            "path": ("Source", 260),
            "heading": ("Heading", 180),
            "score": ("Score", 70),
            "flags": ("Flags", 90),
            "terms": ("Terms", 260),
        }
        for key, (label, width) in headings.items():
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=width // 2, stretch=key in {"path", "terms", "flags"})

        tree_scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree_scroll.grid(row=0, column=0, sticky="nse", padx=(0, 10))
        tree.configure(yscrollcommand=tree_scroll.set)

        text_frame = tk.Frame(body, bg=COLORS["log_bg"], highlightbackground=COLORS["log_border"], highlightthickness=1)
        text_frame.grid(row=0, column=1, sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_rowconfigure(0, weight=1)

        self.kg_results_text = tk.Text(
            text_frame,
            bg=COLORS["log_bg"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            bd=0,
            relief="flat",
            padx=14,
            pady=14,
            wrap="word",
            font=self.caption_font,
            state="disabled",
        )
        self.kg_results_text.grid(row=0, column=0, sticky="nsew")

        text_scroll = tk.Scrollbar(text_frame, command=self.kg_results_text.yview)
        text_scroll.grid(row=0, column=1, sticky="ns")
        self.kg_results_text.configure(yscrollcommand=text_scroll.set)
        return card

    def _benchmark_page(self, parent: tk.Misc) -> tk.Frame:
        page = tk.Frame(parent, bg=COLORS["content"])
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        card, body = self._card(page, "Benchmark")
        card.grid(row=0, column=0, sticky="ew")
        body.grid_columnconfigure(0, weight=1)

        self._path_field(body, 0, "Benchmark output", self.benchmark_output_dir, self._browse_benchmark_output)
        self._path_field(body, 2, "Questions JSON", self.benchmark_questions_path, self._browse_benchmark_questions)

        summary = tk.Label(
            body,
            textvariable=self.benchmark_summary_text,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        summary.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        self._bind_wrap_to_width(summary, min_width=260)

        actions = tk.Frame(body, bg=COLORS["card"])
        actions.grid(row=5, column=0, sticky="w")
        quality_button = RoundedButton(actions, "Run quality", self._start_quality_benchmark, font=self.button_font, variant="accent", min_width=124, height=40)
        quality_button.pack(side="left", padx=(0, 10))
        retrieval_button = RoundedButton(actions, "Run retrieval", self._start_retrieval_benchmark, font=self.button_font, variant="secondary", min_width=132, height=40)
        retrieval_button.pack(side="left", padx=(0, 10))
        open_button = RoundedButton(actions, "Open report", self._open_latest_benchmark_report, font=self.button_font, variant="secondary", min_width=124, height=40)
        open_button.pack(side="left")
        self.control_widgets.extend([quality_button, retrieval_button, open_button])

        note = tk.Label(
            page,
            text="Quality benchmarks scan generated Markdown for known regressions. Retrieval benchmarks query the current graph index using a questions JSON file.",
            bg=COLORS["content"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        note.grid(row=1, column=0, sticky="new", pady=(12, 0))
        self._bind_wrap_to_width(note, min_width=300)
        return page

    def _guidance_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Guidance")

        items = (
            ("1", "Single file", "Best when you want a specific save location or are iterating on one paper."),
            ("2", "Folder batch", "Scans a directory recursively and writes Markdown into the output folder."),
            ("3", "Chunk size", "Leave at 0 for full documents. Set a token target when you want RAG-sized chunks."),
        )

        for row, (step, title, description) in enumerate(items):
            section = tk.Frame(body, bg=COLORS["surface"])
            section.grid(row=row, column=0, sticky="ew", pady=4)
            section.grid_columnconfigure(1, weight=1)

            badge = tk.Label(
                section,
                text=step,
                bg=COLORS["accent_soft"],
                fg=COLORS["accent"],
                font=self.badge_font,
                width=3,
                pady=8,
            )
            badge.grid(row=0, column=0, sticky="n")

            copy = tk.Frame(section, bg=COLORS["surface"], padx=12, pady=8)
            copy.grid(row=0, column=1, sticky="ew")

            tk.Label(
                copy,
                text=title,
                bg=COLORS["surface"],
                fg=COLORS["text"],
                font=self.body_bold_font,
                anchor="w",
            ).pack(fill="x")
            description_label = tk.Label(
                copy,
                text=description,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=self.caption_font,
                justify="left",
                anchor="w",
            )
            description_label.pack(fill="x", pady=(5, 0))
            self._bind_wrap_to_width(description_label, min_width=220)
        return card

    def _activity_card(self, parent: tk.Misc) -> tk.Frame:
        card, body = self._card(parent, "Activity log")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        progress_label = tk.Label(
            body,
            textvariable=self.progress_text,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=self.caption_font,
            justify="left",
            anchor="w",
        )
        progress_label.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        log_frame = tk.Frame(
            body,
            bg=COLORS["log_bg"],
            highlightbackground=COLORS["log_border"],
            highlightthickness=1,
        )
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_widget = tk.Text(
            log_frame,
            bg=COLORS["log_bg"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent_soft"],
            bd=0,
            relief="flat",
            padx=16,
            pady=16,
            wrap="word",
            font=self.body_font,
            state="disabled",
        )
        self.log_widget.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(log_frame, command=self.log_widget.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_widget.configure(yscrollcommand=scrollbar.set)
        return card

    def _field_label(self, parent: tk.Misc, label: str) -> tk.Label:
        return tk.Label(
            parent,
            text=label,
            bg=parent.cget("bg"),
            fg=COLORS["muted"],
            font=self.label_font,
            anchor="w",
        )

    def _entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=COLORS["field"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["field_border"],
            highlightcolor=COLORS["field_focus"],
            font=self.body_font,
        )
        entry.configure(disabledbackground=COLORS["button_disabled"], disabledforeground=COLORS["muted"])
        return entry

    def _dropdown(self, parent: tk.Misc, variable: tk.StringVar, values: tuple[str, ...]) -> tk.OptionMenu:
        menu = tk.OptionMenu(parent, variable, *values)
        menu.configure(
            bg=COLORS["field"],
            fg=COLORS["text"],
            activebackground=COLORS["surface_alt"],
            activeforeground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["field_border"],
            highlightcolor=COLORS["field_focus"],
            bd=0,
            relief="flat",
            font=self.body_font,
            anchor="w",
            padx=12,
            cursor="hand2",
        )
        menu["menu"].configure(
            bg=COLORS["card"],
            fg=COLORS["text"],
            activebackground=COLORS["surface_alt"],
            activeforeground=COLORS["text"],
            font=self.body_font,
            tearoff=0,
        )
        return menu

    def _checkbutton(self, parent: tk.Misc, text: str, variable: tk.BooleanVar) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=COLORS["card"],
            fg=COLORS["text"],
            activebackground=COLORS["card"],
            activeforeground=COLORS["text"],
            selectcolor=COLORS["field"],
            font=self.caption_font,
            anchor="w",
            padx=0,
        )

    def _path_field(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        var: tk.StringVar,
        command,
    ) -> None:
        self._field_label(parent, label).grid(row=row, column=0, sticky="w")

        row_wrap = tk.Frame(parent, bg=COLORS["card"])
        row_wrap.grid(row=row + 1, column=0, sticky="ew", pady=(10, 18))
        row_wrap.grid_columnconfigure(0, weight=1)

        entry = self._entry(row_wrap, var)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        button = RoundedButton(
            row_wrap,
            "Browse",
            command,
            font=self.button_font,
            variant="secondary",
            min_width=102,
            height=40,
        )
        button.grid(row=0, column=1, sticky="e")
        self.control_widgets.extend([entry, button])

    def _wire_variable_updates(self) -> None:
        for variable in (
            self.input_mode,
            self.input_path,
            self.output_path,
            self.chunk_size,
            self.pdf_backend,
        ):
            variable.trace_add("write", lambda *_args: self._refresh_summary())
        for variable in (
            self.pdf_backend,
            self.ocr_mode,
            self.tessdata,
            self.audit_manifest_path,
            self.audit_cache_dir,
            self.audit_report_dir,
            self.audit_baseline_dir,
            self.audit_backends,
            self.backend_timeout_seconds,
            self.max_input_mb,
            self.max_pdf_pages,
            self.max_extracted_assets,
            self.hardened_mode,
            self.privacy_mode,
            self.allow_external_marker_python,
        ):
            variable.trace_add("write", lambda *_args: self._refresh_diagnostics_health())

    def _sync_header_wrap(self, event) -> None:
        available = max(event.width - 320, 320)
        self.header_title.configure(wraplength=available)
        self.header_subtitle.configure(wraplength=available)

    def _set_default_paths(self) -> None:
        cwd = Path.cwd()
        default_input = cwd / "downloaded"
        self.input_path.set(str(default_input if default_input.exists() else cwd))
        self.output_path.set(str(cwd / "llm_ready"))
        self.audit_manifest_path.set(str(cwd / llm_ingest.DEFAULT_AUDIT_MANIFEST))
        self.audit_cache_dir.set(str(cwd / llm_ingest.DEFAULT_AUDIT_CACHE_DIR))
        self.audit_report_dir.set(str(cwd / llm_ingest.DEFAULT_AUDIT_REPORT_DIR))
        self.audit_baseline_dir.set(str(default_input if default_input.exists() else cwd))
        self.kg_source_dir.set(str(cwd / llm_knowledge_graph.DEFAULT_GRAPH_SOURCE_DIR))
        self.kg_index_dir.set(str(cwd / llm_knowledge_graph.DEFAULT_GRAPH_INDEX_DIR))
        self.benchmark_output_dir.set(str(cwd / "_benchmark_runs"))
        self._set_mode("folder" if default_input.exists() else "file")

    def _refresh_summary(self) -> None:
        mode = "Single file" if self.input_mode.get() == "file" else "Folder batch"
        backend = self.pdf_backend.get() or "auto"
        self.summary_vars["Mode"].set(mode)
        self.summary_vars["Input"].set(self.input_path.get().strip() or "Not selected")
        self.summary_vars["Output"].set(self.output_path.get().strip() or "Not selected")
        self.summary_vars["Chunk size"].set(self.chunk_size.get().strip() or "0")
        self.summary_vars["PDF backend"].set(backend)

    def _set_mode(self, mode: str) -> None:
        self.input_mode.set(mode)
        current_input = Path(self.input_path.get()) if self.input_path.get().strip() else None

        if mode == "file":
            self._set_status("Ready for a single file", "idle")
            if current_input and current_input.exists() and current_input.is_dir():
                self.output_path.set(str(current_input / "output.md"))
        else:
            self._set_status("Ready for a folder batch", "idle")
            if current_input and current_input.exists() and current_input.is_file():
                self.input_path.set(str(current_input.parent))
            output_dir = Path(self.output_path.get()) if self.output_path.get().strip() else None
            if output_dir and output_dir.suffix:
                self.output_path.set(str(output_dir.parent / "llm_ready"))

        self._sync_mode_buttons()
        self._refresh_summary()

    def _sync_mode_buttons(self) -> None:
        is_file = self.input_mode.get() == "file"
        self.mode_file_button.set_selected(is_file)
        self.mode_folder_button.set_selected(not is_file)

    def _show_page(self, key: str) -> None:
        self.active_page.set(key)
        for page_key, frame in self.page_frames.items():
            if page_key == key:
                frame.tkraise()
        for nav_key, button in self.nav_buttons.items():
            button.set_selected(nav_key == key)

    def _browse_input(self) -> None:
        if self.input_mode.get() == "file":
            selected = filedialog.askopenfilename(
                title="Select an input file",
                filetypes=self._file_dialog_patterns(),
            )
            if not selected:
                return
            self.input_path.set(selected)
            self.output_path.set(str(Path(selected).with_suffix(".md")))
            return

        selected = filedialog.askdirectory(title="Select an input folder")
        if selected:
            self.input_path.set(selected)

    def _browse_output(self) -> None:
        if self.input_mode.get() == "file":
            selected = filedialog.asksaveasfilename(
                title="Select output Markdown file",
                defaultextension=".md",
                filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
            )
        else:
            selected = filedialog.askdirectory(title="Select output folder")

        if selected:
            self.output_path.set(selected)

    def _browse_tessdata(self) -> None:
        selected = filedialog.askdirectory(title="Select tessdata folder")
        if selected:
            self.tessdata.set(selected)

    def _browse_audit_manifest(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select audit manifest JSON",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if selected:
            self.audit_manifest_path.set(selected)

    def _browse_audit_cache(self) -> None:
        selected = filedialog.askdirectory(title="Select audit cache directory")
        if selected:
            self.audit_cache_dir.set(selected)

    def _browse_audit_report_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select audit report directory")
        if selected:
            self.audit_report_dir.set(selected)

    def _browse_audit_baseline(self) -> None:
        selected = filedialog.askdirectory(title="Select local baseline directory")
        if selected:
            self.audit_baseline_dir.set(selected)

    def _browse_kg_source(self) -> None:
        selected = filedialog.askdirectory(title="Select generated Markdown folder")
        if selected:
            self.kg_source_dir.set(selected)

    def _browse_kg_index(self) -> None:
        selected = filedialog.askdirectory(title="Select graph index folder")
        if selected:
            self.kg_index_dir.set(selected)

    def _browse_benchmark_output(self) -> None:
        selected = filedialog.askdirectory(title="Select benchmark output folder")
        if selected:
            self.benchmark_output_dir.set(selected)

    def _browse_benchmark_questions(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select benchmark questions JSON",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if selected:
            self.benchmark_questions_path.set(selected)

    def _open_latest_audit_summary(self) -> None:
        if self.last_audit_report is not None:
            path = Path(self.last_audit_report.report_dir) / "audit_summary.md"
        else:
            path = Path(self.audit_report_dir.get().strip() or llm_ingest.DEFAULT_AUDIT_REPORT_DIR) / "audit_summary.md"
        self._open_existing_file(path, "Run an audit first; no audit_summary.md was found.")

    def _open_graph_context(self) -> None:
        path = Path(self.kg_index_dir.get().strip() or llm_knowledge_graph.DEFAULT_GRAPH_INDEX_DIR) / "graph_context.md"
        self._open_existing_file(path, "Build the graph first; no graph_context.md was found.")

    def _open_last_query(self) -> None:
        path = Path(self.kg_index_dir.get().strip() or llm_knowledge_graph.DEFAULT_GRAPH_INDEX_DIR) / "last_query.md"
        self._open_existing_file(path, "Query the graph first; no last_query.md was found.")

    def _open_latest_benchmark_report(self) -> None:
        root = Path(self.benchmark_output_dir.get().strip() or "_benchmark_runs")
        candidates = [root / "retrieval" / "benchmark_summary.md", root / "quality" / "benchmark_summary.md"]
        existing = [path for path in candidates if path.exists()]
        if not existing:
            self._open_existing_file(root / "benchmark_summary.md", "Run a benchmark first; no benchmark_summary.md was found.")
            return
        latest = max(existing, key=lambda path: path.stat().st_mtime)
        self._open_existing_file(latest, "Run a benchmark first; no benchmark_summary.md was found.")

    def _open_existing_file(self, path: Path, missing_message: str) -> None:
        path = Path(path)
        if not path.exists() or not path.is_file():
            messagebox.showinfo(APP_TITLE, missing_message)
            return
        try:
            os.startfile(str(path.resolve()))
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Unable to open {path.name}: {exc}")

    def _file_dialog_patterns(self) -> list[tuple[str, str]]:
        patterns = sorted(llm_ingest.SUPPORTED_EXTENSIONS)
        joined = " ".join(f"*{ext}" for ext in patterns)
        return [("Supported files", joined), ("All files", "*.*")]

    def _refresh_diagnostics_health(self) -> None:
        try:
            ocr_dpi = int(self.ocr_dpi.get().strip() or "200")
        except ValueError:
            ocr_dpi = 200
        security = self._collect_security_limits(fallback=True)
        sample_path: Path | None = None
        baseline_text = self.audit_baseline_dir.get().strip()
        if baseline_text:
            baseline_dir = Path(baseline_text)
            if baseline_dir.exists() and baseline_dir.is_dir():
                files = [file for file in llm_ingest.list_supported_files(baseline_dir) if file.suffix.lower() == ".pdf"]
                if files:
                    sample_path = files[0]

        backend_names = llm_ingest.SUPPORTED_PDF_BACKENDS
        status_lines: list[str] = []
        for backend_name in backend_names:
            config = PDFConfig(
                ocr_language=self.ocr_language.get().strip() or "eng",
                ocr_dpi=ocr_dpi,
                tessdata=self.tessdata.get().strip() or None,
                ocr_mode=self.ocr_mode.get(),
                pdf_backend=backend_name,
                table_strategy=self.table_strategy.get(),
                security=security,
            )
            plan = llm_ingest.inspect_pdf_backend_plan(
                config,
                require_marker_models=backend_name == "marker",
                sample_path=sample_path,
            )
            selected = plan.selected or "unavailable"
            candidate = next((entry for entry in plan.candidates if entry.name == selected), None)
            detail = candidate.detail if candidate is not None else llm_ingest.format_pdf_backend_failure(plan)
            status_lines.append(f"{backend_name}: {selected} - {detail}")
        provenance = llm_ingest.dependency_provenance(privacy_mode=self.privacy_mode.get())
        present = ", ".join(f"{name}={Path(origin).name if origin not in {'missing', 'built-in'} else origin}" for name, origin in provenance.items())
        status_lines.append(f"Dependencies: {present}")
        optional_health = llm_backends.backend_health(("docling", "mineru", "unstructured"))
        optional_summary = ", ".join(
            f"{health.name}={'ready' if health.runnable else ('importable' if health.importable else 'missing')}"
            for health in optional_health.values()
        )
        status_lines.append(f"Optional adapters: {optional_summary}")

        for label, text in zip(self.audit_status_lines, status_lines, strict=False):
            label.configure(text=text)

        manifest_path = Path(self.audit_manifest_path.get().strip()) if self.audit_manifest_path.get().strip() else None
        cache_dir = Path(self.audit_cache_dir.get().strip()) if self.audit_cache_dir.get().strip() else None
        sample_note = "Audit corpus manifest not found yet."
        if manifest_path and manifest_path.exists() and cache_dir:
            with contextlib.suppress(Exception):
                samples = llm_ingest.load_audit_manifest(manifest_path)
                cached = sum(1 for sample in samples if (cache_dir / sample.filename).exists())
                sample_note = f"{len(samples)} public samples configured, {cached} cached locally."
        self.audit_summary_text.set(sample_note if self.last_audit_report is None else self.audit_summary_text.get())

    def _populate_audit_results(self, report: llm_ingest.AuditReport) -> None:
        if self.audit_tree is None:
            return

        self.audit_tree.delete(*self.audit_tree.get_children())
        for result in report.results:
            self.audit_tree.insert(
                "",
                "end",
                values=(
                    result.sample_label,
                    result.source_kind,
                    result.backend_label,
                    result.backend_used or "-",
                    result.status,
                    result.tokens,
                    result.asset_count,
                    result.issue_total,
                ),
            )

        success_count = sum(1 for result in report.results if result.status == "ok")
        failure_count = sum(1 for result in report.results if result.status == "failed")
        issue_total = sum(result.issue_total for result in report.results)
        missing = len(report.missing_samples)
        self.audit_summary_text.set(
            f"{success_count} runs succeeded, {failure_count} failed, {issue_total} soft issues flagged, {missing} seed samples missing."
        )

    def _populate_kg_report(self, report: llm_knowledge_graph.KGReport) -> None:
        self.kg_summary_text.set(
            f"{report.document_count} docs, {report.chunk_count} chunks, {report.node_count} nodes, {report.edge_count} edges, {report.embedding_count} vectors."
        )
        if self.kg_tree is not None:
            self.kg_tree.delete(*self.kg_tree.get_children())
        self._set_kg_results_text(
            "\n".join(
                [
                    "Knowledge graph built.",
                    "",
                    f"Index: {report.index_dir}",
                    f"Documents: {report.document_count}",
                    f"Chunks: {report.chunk_count}",
                    f"Terms: {report.term_count}",
                    f"Citations: {report.citation_count}",
                    f"Embeddings: {report.embedding_model} ({report.embedding_count} vectors, {report.embedding_dimensions} dimensions)",
                    "",
                    "Artifacts:",
                    "- graph.json",
                    "- chunks.jsonl",
                    "- embeddings.jsonl",
                    "- rag_pack.json after a query",
                    "- graph_context.md",
                ]
            )
        )

    def _populate_kg_query(self, result: llm_knowledge_graph.KGQueryResult) -> None:
        if self.kg_tree is not None:
            self.kg_tree.delete(*self.kg_tree.get_children())
            for hit in result.hits:
                self.kg_tree.insert(
                    "",
                    "end",
                    values=(
                        hit.path,
                        hit.heading,
                        hit.score,
                        ", ".join(hit.prompt_flags) if hit.prompt_flags else "none",
                        ", ".join(hit.terms[:6]),
                    ),
                )
        self._set_kg_results_text(result.context_markdown)
        self.kg_summary_text.set(f"{len(result.hits)} evidence chunks returned with {result.retrieval_mode} retrieval. Query pack saved to last_query.md.")

    def _set_kg_results_text(self, text: str) -> None:
        if self.kg_results_text is None:
            return
        self.kg_results_text.configure(state="normal")
        self.kg_results_text.delete("1.0", "end")
        self.kg_results_text.insert("1.0", text)
        self.kg_results_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    self.progress_text.set(payload)
                elif kind == "status":
                    text, tone = payload.split("::", 1)
                    self._set_status(text, tone)
                elif kind == "audit_report":
                    self.last_audit_report = payload
                    self._populate_audit_results(payload)
                    self.progress_text.set("Audit complete")
                    self._show_page("diagnostics")
                elif kind == "kg_report":
                    self.last_kg_report = payload
                    self._populate_kg_report(payload)
                    self.progress_text.set("Knowledge graph built")
                    self._show_page("graph")
                elif kind == "kg_query":
                    self._populate_kg_query(payload)
                    self.progress_text.set("Knowledge graph query complete")
                    self._show_page("graph")
                elif kind == "benchmark_done":
                    self.benchmark_summary_text.set(f"Benchmark complete. Report: {payload}")
                    self.progress_text.set("Benchmark complete")
                    self._show_page("benchmark")
                elif kind == "benchmark_finished":
                    self._set_running(False)
                    self._set_status("Done", "success")
                    self.worker_thread = None
                    self.stop_requested.clear()
                    self._show_page("benchmark")
                elif kind == "kg_done":
                    self._set_running(False)
                    self._set_status("Done", "success")
                    self.worker_thread = None
                    self.stop_requested.clear()
                    self._show_page("graph")
                elif kind == "done":
                    self._set_running(False)
                    self._set_status("Done", "success")
                    self.progress_text.set("Run complete")
                    self.worker_thread = None
                    self.stop_requested.clear()
                    self._show_page("activity")
                elif kind == "cancelled":
                    self._set_running(False)
                    self._set_status("Stopped", "idle")
                    self.progress_text.set(payload)
                    self.worker_thread = None
                    self.stop_requested.clear()
                    self._show_page("activity")
                elif kind == "error":
                    self._set_running(False)
                    self._set_status("Failed", "error")
                    self.progress_text.set("Run failed")
                    self.worker_thread = None
                    self.stop_requested.clear()
                    self._show_page("activity")
                    messagebox.showerror(APP_TITLE, payload)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log_queue)

    def _set_running(self, running: bool) -> None:
        for control in self.control_widgets:
            with contextlib.suppress(tk.TclError, AttributeError):
                if hasattr(control, "set_enabled"):
                    control.set_enabled(not running)
                else:
                    control.configure(state="disabled" if running else "normal")

        self.run_button.set_enabled(not running)
        self.stop_button.set_enabled(running and not self.stop_requested.is_set())
        self.clear_button.set_enabled(True)
        self._sync_mode_buttons()

    def _set_status(self, text: str, tone: str) -> None:
        self.status_text.set(text)
        palette = {
            "idle": (COLORS["idle_bg"], COLORS["idle_fg"]),
            "running": (COLORS["accent_soft"], COLORS["accent"]),
            "success": (COLORS["success_bg"], COLORS["success_fg"]),
            "error": (COLORS["error_bg"], COLORS["error_fg"]),
        }
        bg, fg = palette.get(tone, palette["idle"])
        self.status_badge.configure(bg=bg, fg=fg)

    def _start_run(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return

        try:
            config = self._collect_inputs()
            runtime_notes = self._validate_runtime(config)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        input_mode, pdf_config, input_path, output_path, chunk_size = config
        self.stop_requested.clear()
        self._set_running(True)
        self._set_status("Running...", "running")
        self.progress_text.set("Preparing run...")
        self._append_log("Started: " + input_path.name + "\n")
        self._append_log("=" * 78 + "\n")
        for note in runtime_notes:
            self._append_log(note + "\n")
        if runtime_notes:
            self._append_log("-" * 78 + "\n")
        self._show_page("activity")

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(input_mode, pdf_config, input_path, output_path, chunk_size, self.write_sidecars.get()),
            daemon=True,
        )
        self.worker_thread.start()

    def _start_audit(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return

        try:
            manifest_path, cache_dir, report_dir, backend_specs, baseline_dirs = self._collect_audit_inputs()
            security = self._collect_security_limits()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self.stop_requested.clear()
        self._set_running(True)
        self._set_status("Auditing...", "running")
        self.progress_text.set("Preparing audit...")
        self._append_log("Started audit\n")
        self._append_log("=" * 78 + "\n")
        self._show_page("activity")

        self.worker_thread = threading.Thread(
            target=self._run_audit_worker,
            args=(manifest_path, cache_dir, report_dir, backend_specs, baseline_dirs, security),
            daemon=True,
        )
        self.worker_thread.start()

    def _start_kg_build(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        try:
            source_dir, index_dir, max_tokens, top_terms, embedding_model, embedding_dimensions, max_source_files, max_text_bytes = self._collect_kg_build_inputs()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self.stop_requested.clear()
        self._set_running(True)
        self._set_status("Indexing...", "running")
        self.progress_text.set("Preparing knowledge graph...")
        self._append_log("Started knowledge graph build\n")
        self._append_log("=" * 78 + "\n")
        self._show_page("activity")

        self.worker_thread = threading.Thread(
            target=self._run_kg_build_worker,
            args=(source_dir, index_dir, max_tokens, top_terms, embedding_model, embedding_dimensions, max_source_files, max_text_bytes),
            daemon=True,
        )
        self.worker_thread.start()

    def _start_kg_query(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        try:
            index_dir, query, limit, retrieval_mode = self._collect_kg_query_inputs()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self.stop_requested.clear()
        self._set_running(True)
        self._set_status("Querying...", "running")
        self.progress_text.set("Querying knowledge graph...")
        self._append_log(f"Knowledge graph query: {query}\n")

        self.worker_thread = threading.Thread(
            target=self._run_kg_query_worker,
            args=(index_dir, query, limit, retrieval_mode),
            daemon=True,
        )
        self.worker_thread.start()

    def _start_quality_benchmark(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        source_dir = Path(self.kg_source_dir.get().strip() or llm_knowledge_graph.DEFAULT_GRAPH_SOURCE_DIR)
        output_dir = Path(self.benchmark_output_dir.get().strip() or "_benchmark_runs") / "quality"
        if not source_dir.exists() or not source_dir.is_dir():
            messagebox.showerror(APP_TITLE, "Choose a Markdown source folder on the Knowledge Graph page first.")
            return
        self._set_running(True)
        self._set_status("Benchmarking...", "running")
        self.progress_text.set("Running quality benchmark...")
        self.worker_thread = threading.Thread(target=self._run_quality_benchmark_worker, args=(source_dir, output_dir), daemon=True)
        self.worker_thread.start()

    def _start_retrieval_benchmark(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        questions_path = Path(self.benchmark_questions_path.get().strip())
        index_dir = Path(self.kg_index_dir.get().strip() or llm_knowledge_graph.DEFAULT_GRAPH_INDEX_DIR)
        output_dir = Path(self.benchmark_output_dir.get().strip() or "_benchmark_runs") / "retrieval"
        if not questions_path.exists() or questions_path.suffix.lower() != ".json":
            messagebox.showerror(APP_TITLE, "Choose a benchmark questions JSON file.")
            return
        if not (index_dir / "graph.json").exists() or not (index_dir / "chunks.jsonl").exists():
            messagebox.showerror(APP_TITLE, "Build the knowledge graph before running retrieval benchmarks.")
            return
        self._set_running(True)
        self._set_status("Benchmarking...", "running")
        self.progress_text.set("Running retrieval benchmark...")
        self.worker_thread = threading.Thread(target=self._run_retrieval_benchmark_worker, args=(questions_path, index_dir, output_dir), daemon=True)
        self.worker_thread.start()

    def _request_stop(self) -> None:
        if not self.worker_thread or not self.worker_thread.is_alive():
            return
        if self.stop_requested.is_set():
            return
        self.stop_requested.set()
        self.stop_button.set_enabled(False)
        self._set_status("Stopping...", "running")
        self.progress_text.set("Stopping after the current step...")
        self._append_log("Stop requested. Finishing the current step before exiting.\n")

    def _collect_audit_inputs(
        self,
    ) -> tuple[Path, Path, Path, list[llm_ingest.AuditBackendSpec], list[Path]]:
        manifest_text = self.audit_manifest_path.get().strip()
        cache_text = self.audit_cache_dir.get().strip()
        report_text = self.audit_report_dir.get().strip()
        baseline_text = self.audit_baseline_dir.get().strip()
        backend_text = self.audit_backends.get().strip()

        if not manifest_text:
            raise ValueError("Choose an audit manifest JSON file.")
        if not cache_text:
            raise ValueError("Choose an audit cache directory.")
        if not report_text:
            raise ValueError("Choose an audit report directory.")
        if not backend_text:
            raise ValueError("Choose at least one audit backend.")

        manifest_path = Path(manifest_text)
        cache_dir = Path(cache_text)
        report_dir = Path(report_text)
        baseline_dirs = [Path(baseline_text)] if baseline_text else []

        if not manifest_path.exists():
            raise ValueError("The selected audit manifest does not exist.")
        if manifest_path.suffix.lower() != ".json":
            raise ValueError("The audit manifest must be a JSON file.")
        for baseline_dir in baseline_dirs:
            if not baseline_dir.exists() or not baseline_dir.is_dir():
                raise ValueError("The selected baseline directory does not exist.")

        try:
            llm_ingest.load_audit_manifest(manifest_path)
            backend_specs = llm_ingest.parse_audit_backend_specs(backend_text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(str(exc)) from exc

        return manifest_path, cache_dir, report_dir, backend_specs, baseline_dirs

    def _collect_kg_build_inputs(self) -> tuple[Path, Path, int, int, str, int, int, int]:
        source_text = self.kg_source_dir.get().strip()
        index_text = self.kg_index_dir.get().strip()
        if not source_text:
            raise ValueError("Choose the folder containing generated Markdown files.")
        if not index_text:
            raise ValueError("Choose a graph index folder.")
        source_dir = Path(source_text)
        index_dir = Path(index_text)
        if not source_dir.exists() or not source_dir.is_dir():
            raise ValueError("The selected Markdown source folder does not exist.")
        try:
            max_tokens = int(self.kg_max_chunk_tokens.get().strip() or "850")
            top_terms = int(self.kg_top_terms.get().strip() or "14")
            embedding_dimensions = int(self.kg_embedding_dimensions.get().strip() or str(llm_knowledge_graph.DEFAULT_EMBEDDING_DIMENSIONS))
            max_source_files = int(self.kg_max_source_files.get().strip() or "2000")
            max_text_bytes = int(self.kg_max_chunk_text_bytes.get().strip() or str(llm_knowledge_graph.DEFAULT_MAX_GRAPH_CHUNK_TEXT_BYTES))
        except ValueError as exc:
            raise ValueError("Graph settings must be whole numbers.") from exc
        embedding_model = self.kg_embedding_model.get().strip().lower() or llm_knowledge_graph.DEFAULT_EMBEDDING_MODEL
        if embedding_model not in llm_knowledge_graph.SUPPORTED_EMBEDDING_MODELS:
            raise ValueError("Embedding model must be hash, tfidf-hash, or none.")
        if max_tokens < 100:
            raise ValueError("Max chunk tokens must be at least 100.")
        if top_terms < 3:
            raise ValueError("Terms per chunk must be at least 3.")
        if embedding_dimensions < 32:
            raise ValueError("Vector dimensions must be at least 32.")
        if max_source_files < 1:
            raise ValueError("Max source files must be at least 1.")
        if max_text_bytes < 1000:
            raise ValueError("Max text bytes must be at least 1000.")
        return source_dir, index_dir, max_tokens, top_terms, embedding_model, embedding_dimensions, max_source_files, max_text_bytes

    def _collect_kg_query_inputs(self) -> tuple[Path, str, int, str]:
        index_text = self.kg_index_dir.get().strip()
        query = self.kg_query.get().strip()
        if not index_text:
            raise ValueError("Choose a graph index folder.")
        if not query:
            raise ValueError("Enter a question for the graph.")
        index_dir = Path(index_text)
        if not (index_dir / "chunks.jsonl").exists() or not (index_dir / "graph.json").exists():
            raise ValueError("Build the graph first, or choose an index folder containing graph.json and chunks.jsonl.")
        try:
            limit = int(self.kg_limit.get().strip() or "8")
        except ValueError as exc:
            raise ValueError("Evidence chunks must be a whole number.") from exc
        if limit < 1:
            raise ValueError("Evidence chunks must be at least 1.")
        retrieval_mode = self.kg_retrieval_mode.get().strip().lower() or "hybrid"
        if retrieval_mode not in {"hybrid", "lexical", "vector"}:
            raise ValueError("Retrieval mode must be hybrid, lexical, or vector.")
        return index_dir, query, limit, retrieval_mode

    def _collect_security_limits(self, *, fallback: bool = False) -> llm_ingest.SecurityLimits:
        try:
            timeout = int(self.backend_timeout_seconds.get().strip() or str(llm_ingest.DEFAULT_BACKEND_TIMEOUT_SECONDS))
            max_input = int(self.max_input_mb.get().strip() or str(llm_ingest.DEFAULT_MAX_INPUT_MB))
            max_pages = int(self.max_pdf_pages.get().strip() or str(llm_ingest.DEFAULT_MAX_PDF_PAGES))
            max_assets = int(self.max_extracted_assets.get().strip() or str(llm_ingest.DEFAULT_MAX_EXTRACTED_ASSETS))
        except ValueError as exc:
            if fallback:
                timeout = llm_ingest.DEFAULT_BACKEND_TIMEOUT_SECONDS
                max_input = llm_ingest.DEFAULT_MAX_INPUT_MB
                max_pages = llm_ingest.DEFAULT_MAX_PDF_PAGES
                max_assets = llm_ingest.DEFAULT_MAX_EXTRACTED_ASSETS
            else:
                raise ValueError("Security limits must be whole numbers.") from exc
        security = llm_ingest.SecurityLimits(
            max_input_mb=max_input,
            max_pdf_pages=max_pages,
            max_extracted_assets=max_assets,
            backend_timeout_seconds=timeout,
            hardened_mode=self.hardened_mode.get(),
            allow_external_marker_python=self.allow_external_marker_python.get(),
            privacy_mode=self.privacy_mode.get(),
        )
        try:
            llm_ingest._validate_security_limits(security)
        except ValueError:
            if not fallback:
                raise
            security = llm_ingest.SecurityLimits()
        return security

    def _collect_inputs(self) -> tuple[str, PDFConfig, Path, Path, int]:
        input_text = self.input_path.get().strip()
        output_text = self.output_path.get().strip()

        if not input_text:
            raise ValueError("Choose an input file or folder.")
        if not output_text:
            raise ValueError("Choose an output file or folder.")

        input_path = Path(input_text)
        output_path = Path(output_text)

        if not input_path.exists():
            raise ValueError("The selected input path does not exist.")

        mode = self.input_mode.get()
        if mode == "file" and not input_path.is_file():
            raise ValueError("Single file mode requires a file input.")
        if mode == "folder" and not input_path.is_dir():
            raise ValueError("Folder batch mode requires a folder input.")
        if mode == "file" and output_path.exists() and output_path.is_dir():
            raise ValueError("Single file mode requires an output file, not a folder.")
        if mode == "folder" and output_path.exists() and output_path.is_file():
            raise ValueError("Folder batch mode requires an output folder.")
        if mode == "folder" and self._paths_equal(input_path, output_path):
            raise ValueError("Output folder must be different from the input folder.")

        try:
            chunk_size = int(self.chunk_size.get().strip() or "0")
        except ValueError as exc:
            raise ValueError("Chunk size must be a whole number.") from exc
        if chunk_size < 0:
            raise ValueError("Chunk size cannot be negative.")

        try:
            ocr_dpi = int(self.ocr_dpi.get().strip() or "200")
        except ValueError as exc:
            raise ValueError("OCR DPI must be a whole number.") from exc
        if ocr_dpi <= 0:
            raise ValueError("OCR DPI must be greater than zero.")

        config = PDFConfig(
            ocr_language=self.ocr_language.get().strip() or "eng",
            ocr_dpi=ocr_dpi,
            tessdata=self.tessdata.get().strip() or None,
            ocr_mode=self.ocr_mode.get(),
            pdf_backend=self.pdf_backend.get(),
            table_strategy=self.table_strategy.get(),
            security=self._collect_security_limits(),
        )
        return mode, config, input_path, output_path, chunk_size

    def _validate_runtime(self, collected: tuple[str, PDFConfig, Path, Path, int]) -> list[str]:
        input_mode, config, input_path, output_path, _chunk_size = collected

        files_to_check: list[Path]
        if input_mode == "file":
            files_to_check = [input_path]
        else:
            files_to_check = self._folder_supported_files(input_path, output_path)

        has_pdf = any(file.suffix.lower() == ".pdf" for file in files_to_check)
        has_docx = any(file.suffix.lower() == ".docx" for file in files_to_check)
        has_pptx = any(file.suffix.lower() == ".pptx" for file in files_to_check)
        has_html = any(file.suffix.lower() in {".html", ".htm"} for file in files_to_check)
        has_csv = any(file.suffix.lower() == ".csv" for file in files_to_check)

        missing = []
        if has_pdf and importlib.util.find_spec("pymupdf") is None and importlib.util.find_spec("fitz") is None:
            missing.append("pymupdf")
        if has_docx and importlib.util.find_spec("docx") is None:
            missing.append("python-docx")
        if has_pptx and importlib.util.find_spec("pptx") is None:
            missing.append("python-pptx")
        if has_html and importlib.util.find_spec("bs4") is None:
            missing.append("beautifulsoup4")
        if has_csv and importlib.util.find_spec("pandas") is None:
            missing.append("pandas")

        if missing:
            deps = ", ".join(sorted(set(missing)))
            raise ValueError(f"Missing dependency: pip install {deps}")
        if has_pdf and config.tessdata:
            tessdata_path = Path(config.tessdata)
            if llm_ingest._normalize_tessdata_candidate(tessdata_path) is None:
                raise ValueError("The selected tessdata path does not contain OCR language data.")
        notes: list[str] = []
        if has_pdf:
            pdf_files = [file for file in files_to_check if file.suffix.lower() == ".pdf"]
            files_for_validation = pdf_files
            if config.pdf_backend == "auto":
                files_for_validation = pdf_files[:4]
            for index, pdf_file in enumerate(files_for_validation):
                plan = llm_ingest.inspect_pdf_backend_plan(
                    config,
                    require_marker_models=(config.pdf_backend or "auto").lower() == "marker",
                    sample_path=pdf_file,
                )
                if plan.selected is None:
                    raise ValueError(llm_ingest.format_pdf_backend_failure(plan))
                route_notes = llm_ingest.describe_pdf_backend_plan(plan)
                if input_mode == "file":
                    notes.extend(route_notes)
                elif index == 0:
                    notes.extend(route_notes)
        return notes

    def _run_worker(
        self,
        input_mode: str,
        config: PDFConfig,
        input_path: Path,
        output_path: Path,
        chunk_size: int,
        write_sidecars: bool,
    ) -> None:
        writer = QueueWriter(self.log_queue)

        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                self._run_conversion(input_mode, config, input_path, output_path, chunk_size, write_sidecars)
            self.log_queue.put(("done", "done"))
        except llm_ingest.ConversionCancelled as exc:
            message = str(exc).strip() or "Run cancelled by user."
            self.log_queue.put(("log", message + "\n"))
            self.log_queue.put(("cancelled", message))
        except BaseException as exc:
            error_text = self._format_worker_error(exc)
            self.log_queue.put(("log", error_text + "\n"))
            self.log_queue.put(("error", error_text))

    def _run_audit_worker(
        self,
        manifest_path: Path,
        cache_dir: Path,
        report_dir: Path,
        backend_specs: list[llm_ingest.AuditBackendSpec],
        baseline_dirs: list[Path],
        security: llm_ingest.SecurityLimits,
    ) -> None:
        writer = QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                report = llm_ingest.run_audit(
                    manifest_path,
                    cache_dir,
                    report_dir,
                    backend_specs,
                    baseline_dirs=baseline_dirs,
                    download_missing=self.audit_download_missing.get(),
                    security=security,
                    cancel_event=self.stop_requested,
                    progress_callback=lambda text: self.log_queue.put(("progress", text)),
                )
            self.log_queue.put(("audit_report", report))
            self.log_queue.put(("done", "done"))
        except llm_ingest.ConversionCancelled as exc:
            message = str(exc).strip() or "Run cancelled by user."
            self.log_queue.put(("log", message + "\n"))
            self.log_queue.put(("cancelled", message))
        except BaseException as exc:
            error_text = self._format_worker_error(exc)
            self.log_queue.put(("log", error_text + "\n"))
            self.log_queue.put(("error", error_text))

    def _run_kg_build_worker(
        self,
        source_dir: Path,
        index_dir: Path,
        max_tokens: int,
        top_terms: int,
        embedding_model: str,
        embedding_dimensions: int,
        max_source_files: int,
        max_text_bytes: int,
    ) -> None:
        writer = QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                report = llm_knowledge_graph.build_knowledge_graph(
                    source_dir,
                    index_dir,
                    max_chunk_tokens=max_tokens,
                    top_terms_per_chunk=top_terms,
                    embedding_model=embedding_model,
                    embedding_dimensions=embedding_dimensions,
                    max_source_files=max_source_files,
                    max_chunk_text_bytes=max_text_bytes,
                    cancel_event=self.stop_requested,
                    progress_callback=lambda text: self.log_queue.put(("progress", text)),
                )
                print(
                    f"Knowledge graph complete: {report.document_count} docs, "
                    f"{report.chunk_count} chunks, {report.node_count} nodes, {report.edge_count} edges, "
                    f"{report.embedding_count} vectors."
                )
            self.log_queue.put(("kg_report", report))
            self.log_queue.put(("kg_done", "done"))
        except RuntimeError as exc:
            message = str(exc).strip() or "Knowledge graph build cancelled."
            if "cancel" in message.lower():
                self.log_queue.put(("log", message + "\n"))
                self.log_queue.put(("cancelled", message))
            else:
                error_text = self._format_worker_error(exc)
                self.log_queue.put(("log", error_text + "\n"))
                self.log_queue.put(("error", error_text))
        except BaseException as exc:
            error_text = self._format_worker_error(exc)
            self.log_queue.put(("log", error_text + "\n"))
            self.log_queue.put(("error", error_text))

    def _run_kg_query_worker(self, index_dir: Path, query: str, limit: int, retrieval_mode: str) -> None:
        writer = QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                result = llm_knowledge_graph.query_knowledge_graph(index_dir, query, limit=limit, retrieval_mode=retrieval_mode)
                print(f"Knowledge graph query returned {len(result.hits)} chunks.")
            self.log_queue.put(("kg_query", result))
            self.log_queue.put(("kg_done", "done"))
        except BaseException as exc:
            error_text = self._format_worker_error(exc)
            self.log_queue.put(("log", error_text + "\n"))
            self.log_queue.put(("error", error_text))

    def _run_quality_benchmark_worker(self, source_dir: Path, output_dir: Path) -> None:
        writer = QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                report = llm_benchmark.run_quality_benchmark([source_dir], output_dir)
                print(f"Quality benchmark complete: {report['totals']['finding_count']} findings.")
            self.log_queue.put(("benchmark_done", str(output_dir / "benchmark_summary.md")))
            self.log_queue.put(("benchmark_finished", "done"))
        except BaseException as exc:
            error_text = self._format_worker_error(exc)
            self.log_queue.put(("log", error_text + "\n"))
            self.log_queue.put(("error", error_text))

    def _run_retrieval_benchmark_worker(self, questions_path: Path, index_dir: Path, output_dir: Path) -> None:
        writer = QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                report = llm_benchmark.run_retrieval_benchmark(questions_path, index_dir, output_dir)
                print(f"Retrieval benchmark complete: {report['summary']['question_count']} questions.")
            self.log_queue.put(("benchmark_done", str(output_dir / "benchmark_summary.md")))
            self.log_queue.put(("benchmark_finished", "done"))
        except BaseException as exc:
            error_text = self._format_worker_error(exc)
            self.log_queue.put(("log", error_text + "\n"))
            self.log_queue.put(("error", error_text))

    def _run_conversion(
        self,
        input_mode: str,
        config: PDFConfig,
        input_path: Path,
        output_path: Path,
        chunk_size: int,
        write_sidecars: bool,
    ) -> None:
        if input_mode == "file":
            self.log_queue.put(("progress", f"Processing 1/1: {input_path.name}"))
            llm_ingest.convert_file(
                input_path,
                output_path,
                chunk_size=chunk_size,
                pdf_config=config,
                cancel_event=self.stop_requested,
                write_sidecars=write_sidecars,
            )
            return

        output_path.mkdir(parents=True, exist_ok=True)
        files = self._folder_supported_files(input_path, output_path)
        batch_plan = llm_ingest.build_batch_targets(files, input_path, output_path)
        print(f"\nFound {len(files)} supported files in {input_path}\n")
        total = len(batch_plan)
        for index, (file, target) in enumerate(batch_plan, 1):
            relative = file.relative_to(input_path).as_posix()
            self.log_queue.put(("progress", f"Processing {index}/{total}: {relative}"))
            try:
                llm_ingest.convert_file(
                    file,
                    target,
                    chunk_size=chunk_size,
                    pdf_config=config,
                    cancel_event=self.stop_requested,
                    write_sidecars=write_sidecars,
                )
            except llm_ingest.ConversionCancelled:
                raise
            except (ValueError, OSError, RuntimeError, SystemExit) as exc:
                message = self._format_worker_error(exc)
                print(f"skipped: {relative}")
                print(f"  Reason: {message}")
        print(f"\nDone. Output in {output_path}")

    def _format_worker_error(self, exc: BaseException) -> str:
        if isinstance(exc, SystemExit):
            code = exc.code
            if isinstance(code, str) and code.strip():
                return code.strip()
            if code not in (None, 0):
                return f"Run stopped with exit code {code}."
            return "Run stopped."
        if isinstance(exc, (ValueError, OSError, RuntimeError)):
            message = str(exc).strip()
            if message:
                return message
        return traceback.format_exc().strip()

    def _folder_supported_files(self, input_path: Path, output_path: Path) -> list[Path]:
        return llm_ingest.list_supported_files(input_path, output_path)

    def _paths_equal(self, left: Path, right: Path) -> bool:
        return self._normalized_path(left) == self._normalized_path(right)

    def _path_is_within(self, child: Path, parent: Path) -> bool:
        child_path = self._normalized_path(child)
        parent_path = self._normalized_path(parent)
        try:
            child_path.relative_to(parent_path)
            return True
        except ValueError:
            return False

    def _normalized_path(self, path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return path.absolute()


def main() -> None:
    if "--pdf-worker" in sys.argv:
        import pdf_worker_runner

        raise SystemExit(pdf_worker_runner.main())

    loaded_fonts = _load_private_fonts()
    if loaded_fonts:
        atexit.register(_unload_private_fonts, loaded_fonts)

    root = tk.Tk()
    root.option_add("*tearOff", False)
    IngestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
