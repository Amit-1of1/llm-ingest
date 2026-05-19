#!/usr/bin/env python3
"""Figure and caption cleanup helpers for generated Markdown."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FigureImageLine:
    line_index: int
    line: str
    label: str
    group_label: str


@dataclass(frozen=True)
class CaptionGroup:
    caption_line_index: int
    caption_line: str
    label: str
    group_label: str
    images: tuple[FigureImageLine, ...]


def align_figure_images_with_captions(text: str) -> str:
    """Move generated figure image links next to matching rich captions."""
    return group_multipanel_figures(text)


def recover_caption_groups(text: str) -> list[CaptionGroup]:
    """Return pending figure image lines that can be recovered for each caption."""
    text = drop_redundant_bare_figure_labels(text)
    source_lines = text.splitlines()
    groups: list[CaptionGroup] = []
    pending_images: list[FigureImageLine] = []

    for line_index, line in enumerate(source_lines):
        image = figure_image_from_line(line_index, line)
        if image:
            pending_images.append(image)
            continue

        caption_label = figure_label_from_caption_line(line)
        if not caption_label:
            continue

        matched = [image for image in pending_images if caption_accepts_image(caption_label, image)]
        if matched:
            groups.append(
                CaptionGroup(
                    caption_line_index=line_index,
                    caption_line=line,
                    label=caption_label,
                    group_label=normalize_figure_group_label(caption_label),
                    images=tuple(matched),
                )
            )
            pending_images = [image for image in pending_images if image not in matched]

    return groups


def group_multipanel_figures(text: str) -> str:
    """Move related figure assets, including panels, near their best caption."""
    text = drop_redundant_bare_figure_labels(text)
    source_lines = text.splitlines()
    future_caption_counts: dict[str, int] = {}
    future_base_caption_counts: dict[str, int] = {}
    for source_line in source_lines:
        label = figure_label_from_caption_line(source_line)
        if label:
            future_caption_counts[label] = future_caption_counts.get(label, 0) + 1
            if is_base_figure_label(label):
                group_label = normalize_figure_group_label(label)
                future_base_caption_counts[group_label] = future_base_caption_counts.get(group_label, 0) + 1

    output: list[str] = []
    pending_images: list[FigureImageLine] = []
    pending_blanks = 0

    for line_index, line in enumerate(source_lines):
        image = figure_image_from_line(line_index, line)
        if image:
            pending_images.append(image)
            pending_blanks = 0
            continue

        caption_label = figure_label_from_caption_line(line)
        caption_group_label = normalize_figure_group_label(caption_label) if caption_label else ""
        if caption_label:
            future_caption_counts[caption_label] = max(0, future_caption_counts.get(caption_label, 0) - 1)
            if is_base_figure_label(caption_label):
                future_base_caption_counts[caption_group_label] = max(
                    0,
                    future_base_caption_counts.get(caption_group_label, 0) - 1,
                )
        if caption_label and pending_images:
            matched = [image for image in pending_images if caption_accepts_image(caption_label, image)]
            remaining = [image for image in pending_images if not caption_accepts_image(caption_label, image)]
            if matched:
                if output and output[-1].strip():
                    output.append("")
                output.extend(image.line for image in matched)
                output.append("")
                pending_images = remaining
                pending_blanks = 0
            flushable = [
                image
                for image in pending_images
                if not image_has_future_caption(image, future_caption_counts, future_base_caption_counts)
            ]
            pending_images = [
                image
                for image in pending_images
                if image_has_future_caption(image, future_caption_counts, future_base_caption_counts)
            ]
            output.extend(image.line for image in flushable)
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
                if not image_has_future_caption(image, future_caption_counts, future_base_caption_counts)
            ]
            pending_images = [
                image
                for image in pending_images
                if image_has_future_caption(image, future_caption_counts, future_base_caption_counts)
            ]
            output.extend(image.line for image in flushable)
            pending_blanks = 0
        output.append(line)

    if pending_images:
        if output and output[-1].strip():
            output.append("")
        output.extend(image.line for image in pending_images)
    return "\n".join(output)


def figure_image_from_line(line_index: int, line: str) -> FigureImageLine | None:
    label = figure_label_from_image_line(line)
    if not label:
        return None
    return FigureImageLine(
        line_index=line_index,
        line=line,
        label=label,
        group_label=normalize_figure_group_label(label),
    )


def caption_accepts_image(caption_label: str, image: FigureImageLine) -> bool:
    if image.label == caption_label:
        return True
    return is_base_figure_label(caption_label) and image.group_label == normalize_figure_group_label(caption_label)


def image_has_future_caption(
    image: FigureImageLine,
    future_caption_counts: dict[str, int],
    future_base_caption_counts: dict[str, int],
) -> bool:
    return (
        future_caption_counts.get(image.label, 0) > 0
        or future_base_caption_counts.get(image.group_label, 0) > 0
    )


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
    match = _figure_label_match(text)
    if not match:
        return ""
    label = f"{match.group('kind')} {match.group('number')}{match.group('panel') or ''}"
    label = label.lower().replace("fig.", "figure")
    return re.sub(r"\s+", " ", label).strip()


def normalize_figure_group_label(text: str) -> str:
    match = _figure_label_match(text)
    if not match:
        return ""
    label = f"{match.group('kind')} {match.group('number')}"
    label = label.lower().replace("fig.", "figure")
    return re.sub(r"\s+", " ", label).strip()


def is_base_figure_label(label: str) -> bool:
    return bool(label) and label == normalize_figure_group_label(label)


def _figure_label_match(text: str) -> re.Match[str] | None:
    return re.search(
        r"\b(?P<kind>(?:Extended Data\s+|Supplementary\s+)?(?:Figure|Fig\.|Table))\s+"
        r"(?P<number>[A-Za-z]?\d+)(?P<panel>[A-Za-z]?)\b",
        text,
        flags=re.IGNORECASE,
    )
