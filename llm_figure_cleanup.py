#!/usr/bin/env python3
"""Figure and caption cleanup helpers for generated Markdown."""

from __future__ import annotations

import re


def align_figure_images_with_captions(text: str) -> str:
    """Move generated figure image links next to matching rich captions."""
    text = drop_redundant_bare_figure_labels(text)
    source_lines = text.splitlines()
    future_caption_counts: dict[str, int] = {}
    for source_line in source_lines:
        label = figure_label_from_caption_line(source_line)
        if label:
            future_caption_counts[label] = future_caption_counts.get(label, 0) + 1

    output: list[str] = []
    pending_images: list[str] = []
    pending_blanks = 0

    for line in source_lines:
        image_label = figure_label_from_image_line(line)
        if image_label:
            pending_images.append(line)
            pending_blanks = 0
            continue

        caption_label = figure_label_from_caption_line(line)
        if caption_label:
            future_caption_counts[caption_label] = max(0, future_caption_counts.get(caption_label, 0) - 1)
        if caption_label and pending_images:
            matched = [image for image in pending_images if figure_label_from_image_line(image) == caption_label]
            remaining = [image for image in pending_images if figure_label_from_image_line(image) != caption_label]
            if matched:
                if output and output[-1].strip():
                    output.append("")
                output.extend(matched)
                output.append("")
                pending_images = remaining
                pending_blanks = 0
            flushable = [
                image
                for image in pending_images
                if future_caption_counts.get(figure_label_from_image_line(image), 0) <= 0
            ]
            pending_images = [
                image
                for image in pending_images
                if future_caption_counts.get(figure_label_from_image_line(image), 0) > 0
            ]
            output.extend(flushable)
            output.append(line)
            continue

        if not line.strip():
            if pending_images:
                pending_blanks += 1
                if pending_blanks <= 2:
                    continue
            output.append(line)
            continue

        if pending_images:
            flushable = [
                image
                for image in pending_images
                if future_caption_counts.get(figure_label_from_image_line(image), 0) <= 0
            ]
            pending_images = [
                image
                for image in pending_images
                if future_caption_counts.get(figure_label_from_image_line(image), 0) > 0
            ]
            output.extend(flushable)
            pending_blanks = 0
        output.append(line)

    if pending_images:
        if output and output[-1].strip():
            output.append("")
        output.extend(pending_images)
    return "\n".join(output)


def drop_redundant_bare_figure_labels(text: str) -> str:
    lines = text.splitlines()
    rich_labels: set[str] = set()
    for line in lines:
        if is_bare_figure_caption_line(line):
            continue
        label = figure_label_from_caption_line(line)
        if label:
            rich_labels.add(label)

    output: list[str] = []
    for line in lines:
        if is_bare_figure_caption_line(line):
            label = figure_label_from_caption_line(line)
            if label in rich_labels:
                continue
        output.append(line)
    return "\n".join(output)


def is_bare_figure_caption_line(line: str) -> bool:
    stripped = line.strip().lstrip("> ").strip()
    stripped = stripped.strip("*").strip()
    return bool(
        re.fullmatch(
            r"(?:Extended Data\s+|Supplementary\s+)?(?:Figure|Fig\.|Table)\s+\d+[A-Za-z]?",
            stripped,
            flags=re.IGNORECASE,
        )
    )


def figure_label_from_image_line(line: str) -> str:
    match = re.match(r"!\[([^\]]+)\]\([^)]+\)", line.strip())
    if not match:
        return ""
    return normalize_figure_label(match.group(1))


def figure_label_from_caption_line(line: str) -> str:
    stripped = line.strip().lstrip("> ").strip()
    stripped = re.sub(r"^\*\*", "", stripped)
    stripped = re.sub(r"\*\*.*$", "", stripped)
    return normalize_figure_label(stripped)


def normalize_figure_label(text: str) -> str:
    match = re.search(
        r"\b((?:Extended Data\s+|Supplementary\s+)?(?:Figure|Fig\.|Table)\s+\d+[A-Za-z]?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    label = match.group(1).lower().replace("fig.", "figure")
    return re.sub(r"\s+", " ", label).strip()
