#!/usr/bin/env python3
"""Document-level Markdown cleanup for PDF extraction artifacts.

This module intentionally stays independent from the PDF extraction code.  It
repairs structural Markdown problems after a backend has already produced text:
bad H1/title selection, frontmatter drift, publisher boilerplate, repeated
section headings, empty headings, packed references, and common PDF word breaks.
"""

from __future__ import annotations

import re
from pathlib import Path


TITLE_COMPARE_STOPWORDS = {
    "a",
    "an",
    "and",
    "of",
    "the",
    "to",
    "for",
    "in",
    "on",
    "with",
    "from",
    "by",
}

BOILERPLATE_PHRASES = (
    "queen's university belfast",
    "research portal",
    "publisher rights",
    "general rights",
    "take down policy",
    "download date",
    "link to publication record",
    "reprints and permissions",
    "supplementary information is linked",
    "document version publisher",
    "publisher's pdf",
    "downloaded from the university",
    "strictly personal use",
    "copyright holder",
    "taverne",
    "this article is available from",
    "licensee biomed central",
    "page number not for citation purposes",
)

DEHYPHENATED_WORD_REPLACEMENTS = {
    "addition": "addition",
    "biomedical": "biomedical",
    "carboxyl": "carboxyl",
    "chemical": "chemical",
    "hierarchical": "hierarchical",
    "mechanical": "mechanical",
    "mechanism": "mechanism",
    "miniature": "miniature",
    "molecular": "molecular",
    "polymers": "polymers",
    "production": "production",
    "produced": "produced",
    "proteinaceous": "proteinaceous",
    "sealants": "sealants",
    "spider": "spider",
    "structures": "structures",
    "supramolecular": "supramolecular",
    "technique": "technique",
    "viscoelasticity": "viscoelasticity",
}


def normalize_document_structure(text: str, source_path: Path | None = None) -> str:
    """Repair document-level PDF extraction artifacts in Markdown."""
    text = normalize_line_endings(text)
    text = normalize_h1_title(text, source_path=source_path)
    text = ensure_frontmatter(text)
    text = sanitize_existing_frontmatter(text)
    text = strip_leading_plain_metadata_and_boilerplate(text)
    text = remove_duplicate_title_and_author_lines(text)
    text = normalize_bold_section_labels(text)
    text = remove_empty_markdown_headings(text)
    text = remove_duplicate_frontmatter_dates(text)
    text = remove_running_headers_inline(text)
    text = remove_placeholder_affiliations(text)
    text = repair_hyphenated_pdf_breaks(text)
    text = normalize_reference_blocks(text)
    text = qualify_repeated_section_headings(text)
    text = reorder_intro_before_results(text)
    return normalize_line_endings(text)


def normalize_line_endings(text: str) -> str:
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[str, str]:
    match = re.match(r"(?s)\A---\n.*?\n---\n\n?", text)
    if not match:
        return "", text
    return text[: match.end()], text[match.end() :]


def find_first_h1(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if re.match(r"^# (?!#)", line.strip()):
            return index
    return None


def clean_title_text(title: str) -> str:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    title = re.sub(r"^#+\s*", "", title)
    title = title.replace("**", "").replace("__", "").strip("*_ ")
    title = re.sub(r"^\d+\s+", "", title)
    title = re.sub(r"^Article\s+https?://doi\.org/\S+\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^(?:Manuscript\s+title|Title)\s*:\s*", "", title, flags=re.IGNORECASE)
    title = title.replace("_", " ")
    title = re.sub(r"\bFull-\s+Length\b", "Full-Length", title, flags=re.IGNORECASE)
    title = re.sub(r"\bmechan-\s*ical\b", "mechanical", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+\d+\s+(?=of\b)", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(synthetic proteins)\s+Thomas\s+Scheibel\b", r"\1", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip(" .")


def normalize_for_compare(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def looks_like_journal_line(text: str) -> bool:
    normalized = normalize_for_compare(text)
    if normalized in {"article", "review", "full paper", "research article"}:
        return False
    journal_keywords = (
        "journal",
        "communications",
        "factories",
        "letters",
        "materials",
        "science",
        "nature",
        "review",
        "reports",
        "proceedings",
    )
    if not any(keyword in normalized for keyword in journal_keywords):
        return False
    if re.search(r"\d", text) or "," in text or "&" in text:
        return False
    tokens = re.findall(r"[A-Za-z][A-Za-z.\-']*", text)
    return 1 <= len(tokens) <= 6 and all(token[0].isupper() for token in tokens)


def looks_like_filename_slug(title: str) -> bool:
    stripped = title.strip()
    if "_" in stripped:
        return True
    return bool(re.search(r"\b(?:boo|bioa|che|syntheti|mechani)\b$", stripped, flags=re.IGNORECASE))


def looks_like_journal_title(title: str) -> bool:
    normalized = normalize_for_compare(title)
    if normalized in {"microbial cell factories", "nature communications", "small", "biomaterials", "science"}:
        return True
    return looks_like_journal_line(title)


def looks_like_bad_extracted_title(title: str) -> bool:
    lower = title.lower()
    return bool(
        "figure" in lower
        or "scanning electron" in lower
        or " collected fro " in lower
        or lower.startswith(("authors:", "herein,", "finally,", "feasibility of", "fourier-transform"))
        or re.search(r"\bwe\s+(?:introduce|also|develop|investigated|demonstrate)\b", lower)
        or len(title) > 240
    )


def is_title_candidate(line: str) -> bool:
    stripped = clean_title_text(line)
    if not 12 <= len(stripped) <= 220:
        return False
    lower = stripped.lower()
    if line.strip().startswith(("![", "|")):
        return False
    if re.match(r"^\d{1,3}[.)]\s+", stripped):
        return False
    if any(marker in lower for marker in ("http://", "https://", "doi:", "@", "number of words", "copyright")):
        return False
    if re.match(r"^(?:authors?|affiliations?|keywords?|abbreviations?|received|accepted|published|abstract)\b", lower):
        return False
    if lower.startswith(("composition and structural architecture", "natural spider silk assembly", "types of spider silk")):
        return False
    if looks_like_journal_title(stripped) or looks_like_bad_extracted_title(stripped):
        return False
    return len(re.findall(r"[A-Za-z][A-Za-z-]+", stripped)) >= 3


def title_source_overlap_score(title: str, source_path: Path | None) -> int:
    if source_path is None:
        return 0
    source_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", source_path.stem.lower())
        if len(token) > 2 and token not in TITLE_COMPARE_STOPWORDS
    }
    title_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", title.lower())
        if len(token) > 2 and token not in TITLE_COMPARE_STOPWORDS
    }
    return len(source_tokens & title_tokens)


def combine_split_title_heading(lines: list[str], index: int) -> tuple[str, set[int]]:
    title = clean_title_text(lines[index])
    consumed = {index}
    for next_index in range(index + 1, min(len(lines), index + 3)):
        next_line = lines[next_index].strip()
        if not next_line:
            continue
        if not next_line.startswith("## "):
            break
        next_title = clean_title_text(next_line)
        if not next_title:
            continue
        if next_title.lower().startswith(("abstract", "introduction", "methods", "results", "discussion", "references")):
            break
        if len(next_title.split()) <= 8 and not re.search(r"[.:]$", title):
            title = f"{title} {next_title}".strip()
            consumed.add(next_index)
            continue
        break
    return clean_title_text(title), consumed


def best_title_candidate(lines: list[str], start: int, source_path: Path | None) -> tuple[int | None, str]:
    best_index: int | None = None
    best_title = ""
    best_score = -1
    scan_limit = min(len(lines), start + 80)
    for index in range(start, scan_limit):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            cleaned_heading, _ = combine_split_title_heading(lines, index)
            if cleaned_heading.lower().startswith("abstract"):
                break
            if is_title_candidate(stripped):
                score = len(cleaned_heading.split()) + 12
                score += title_source_overlap_score(cleaned_heading, source_path) * 4
                if re.search(r"\b(?:spider|silk|protein|fiber|fibre|polymer|biomaterial|mechanical)\b", cleaned_heading, re.IGNORECASE):
                    score += 6
                if score > best_score:
                    best_index = index
                    best_title = cleaned_heading
                    best_score = score
                continue
        if not is_title_candidate(stripped):
            continue
        score = len(stripped.split()) + title_source_overlap_score(stripped, source_path) * 4
        if ":" in stripped:
            score += 8
        if re.search(r"\b(?:spider|silk|protein|fiber|fibre|polymer|biomaterial|mechanical)\b", stripped, re.IGNORECASE):
            score += 6
        if index == start:
            score += 5
        if score > best_score:
            best_index = index
            best_title = clean_title_text(stripped)
            best_score = score
    if best_title:
        return best_index, best_title
    if source_path is not None:
        return None, clean_title_text(source_path.stem)
    return None, ""


def is_stronger_title(candidate: str, current: str, source_path: Path | None) -> bool:
    if not candidate:
        return False
    if looks_like_bad_extracted_title(current):
        return True
    if looks_like_filename_slug(current) or looks_like_journal_title(current):
        return True
    candidate_overlap = title_source_overlap_score(candidate, source_path)
    current_overlap = title_source_overlap_score(current, source_path)
    if candidate_overlap >= current_overlap + 2:
        return True
    if current.endswith(":") and len(candidate) > len(current) + 8 and candidate.startswith(current):
        return True
    if len(current.split()) <= 6 and len(candidate.split()) > len(current.split()) + 2:
        return True
    return False


def normalize_h1_title(text: str, source_path: Path | None = None) -> str:
    prefix, body = split_frontmatter(text)
    lines = body.splitlines()
    h1_index = find_first_h1(lines)
    if h1_index is None:
        _, fallback = best_title_candidate(lines, 0, source_path)
        if fallback:
            return prefix + f"# {fallback}\n\n" + body.lstrip()
        return text

    raw_heading = lines[h1_index].strip()[2:].strip()
    title = clean_title_text(raw_heading)
    remove_indices: set[int] = set()

    next_index = h1_index + 1
    while next_index < len(lines) and not lines[next_index].strip():
        next_index += 1
    if next_index < len(lines) and is_title_candidate(lines[next_index]):
        continuation = clean_title_text(lines[next_index])
        if raw_heading.lower().startswith(("# title:", "title:", "# manuscript title:", "manuscript title:")):
            title = f"{title} {continuation}".strip()
            remove_indices.add(next_index)
        elif looks_like_filename_slug(raw_heading) or looks_like_journal_title(raw_heading):
            title = continuation
            remove_indices.add(next_index)

    candidate_index, candidate = best_title_candidate(lines, h1_index + 1, source_path)
    if is_stronger_title(candidate, title, source_path):
        title = candidate
        if candidate_index is not None:
            combined_title, combined_indices = combine_split_title_heading(lines, candidate_index)
            if clean_title_text(combined_title) == clean_title_text(candidate):
                remove_indices.update(combined_indices)
            else:
                remove_indices.add(candidate_index)
    elif (looks_like_filename_slug(raw_heading) or looks_like_journal_title(raw_heading) or not title) and candidate:
        title = candidate
        if candidate_index is not None:
            remove_indices.add(candidate_index)

    lines[h1_index] = f"# {title or clean_title_text(source_path.stem if source_path else raw_heading)}"
    return prefix + "\n".join(line for index, line in enumerate(lines) if index not in remove_indices)


def yaml_quote(value: str) -> str:
    return str(value).replace('"', "'").strip()


def clean_metadata_authors(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.split(
        r"\b(?:Document Version|Publisher's PDF|Version of record|Published in|Publication date|Download date|License|Copyright|Research Portal|"
        r"Link to publication|General rights|Take down policy)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ;,.")
    if len(text) > 320:
        text = text[:320].rsplit(",", 1)[0].strip(" ;,.")
    return re.sub(r"\s+\bSmall\b$", "", text).strip(" ;,.")


def clean_metadata_journal(text: str) -> str:
    journal = re.sub(r"\s+", " ", str(text or "")).strip()
    if normalize_for_compare(journal) in {"article", "review", "full paper", "feature article", "research article"}:
        return ""
    return journal


def extract_plain_authors(lines: list[str]) -> str:
    for index, line in enumerate(lines[:50]):
        if re.match(r"^\s*Authors?\s*:", line, flags=re.IGNORECASE):
            parts = [re.sub(r"^\s*Authors?\s*:\s*", "", line, flags=re.IGNORECASE).strip()]
            for continuation in lines[index + 1 : index + 8]:
                stripped = continuation.strip()
                if not stripped:
                    continue
                if re.match(r"^(?:Affiliations?|Correspondence|Keywords?|Abbreviations?|##)\b", stripped, flags=re.IGNORECASE):
                    break
                parts.append(stripped)
            return clean_metadata_authors(" ".join(parts))
    return ""


def ensure_frontmatter(text: str) -> str:
    prefix, body = split_frontmatter(text)
    lines = body.splitlines()
    h1_index = find_first_h1(lines)
    title = clean_title_text(lines[h1_index][2:]) if h1_index is not None else ""
    authors = extract_plain_authors(lines)

    if prefix:
        frontmatter = prefix.strip().splitlines()
        keys = {line.split(":", 1)[0].strip().lower() for line in frontmatter[1:-1] if ":" in line}
        insert_at = 1
        if title and "title" not in keys:
            frontmatter.insert(insert_at, f'title: "{yaml_quote(title)}"')
            insert_at += 1
        if authors and "authors" not in keys:
            frontmatter.insert(insert_at, f'authors: "{yaml_quote(authors)}"')
        return "\n".join(frontmatter) + "\n\n" + body.lstrip()

    fields: list[tuple[str, str]] = []
    if title:
        fields.append(("title", title))
    if authors:
        fields.append(("authors", authors))
    if not fields:
        return text
    frontmatter_lines = ["---", *(f'{key}: "{yaml_quote(value)}"' for key, value in fields), "---"]
    return "\n".join(frontmatter_lines) + "\n\n" + body.lstrip()


def sanitize_existing_frontmatter(text: str) -> str:
    prefix, body = split_frontmatter(text)
    if not prefix:
        return text
    body_lines = body.splitlines()
    h1_index = find_first_h1(body_lines)
    body_title = clean_title_text(body_lines[h1_index][2:]) if h1_index is not None else ""
    lines = prefix.strip().splitlines()
    output = [lines[0]]
    for line in lines[1:-1]:
        if ":" not in line:
            output.append(line)
            continue
        key, value = line.split(":", 1)
        key_name = key.strip().lower()
        cleaned_value = value.strip().strip('"')
        if key_name == "authors":
            cleaned_value = clean_metadata_authors(cleaned_value)
            if cleaned_value:
                output.append(f'authors: "{yaml_quote(cleaned_value)}"')
            continue
        if key_name == "journal":
            cleaned_value = clean_metadata_journal(cleaned_value)
            if cleaned_value:
                output.append(f'journal: "{yaml_quote(cleaned_value)}"')
            continue
        if key_name == "title":
            cleaned_value = clean_title_text(cleaned_value)
            if body_title and (
                looks_like_filename_slug(cleaned_value)
                or looks_like_journal_title(cleaned_value)
                or looks_like_bad_extracted_title(cleaned_value)
                or "http://" in cleaned_value.lower()
                or "https://" in cleaned_value.lower()
                or "university of" in cleaned_value.lower()
                or (body_title.lower().startswith(cleaned_value.lower()) and len(body_title) > len(cleaned_value) + 8)
                or len(body_title.split()) > len(cleaned_value.split()) + 2
                or len(cleaned_value) < 12
            ):
                cleaned_value = body_title
            if cleaned_value:
                output.append(f'title: "{yaml_quote(cleaned_value)}"')
            continue
        output.append(line)
    output.append("---")
    return "\n".join(output) + "\n\n" + body.lstrip()


def strip_leading_plain_metadata_and_boilerplate(text: str) -> str:
    prefix, body = split_frontmatter(text)
    lines = body.splitlines()
    h1_index = find_first_h1(lines)
    output: list[str] = []
    in_plain_metadata = False
    pre_section = True

    for index, line in enumerate(lines):
        stripped = line.strip()
        plain = stripped.strip("*_ ").strip()
        if stripped.startswith("## "):
            heading_text = clean_title_text(stripped)
            if pre_section and (looks_like_journal_title(heading_text) or heading_text.lower() in {"review", "open access"}):
                continue
            pre_section = False
            in_plain_metadata = False
        if pre_section and re.match(r"^\*\*Abstract:\*\*", stripped, flags=re.IGNORECASE):
            pre_section = False
            in_plain_metadata = False
        if pre_section and index != h1_index:
            starts_metadata = bool(
                re.match(
                    r"^(?:Authors?|Affiliations?|Affiliation|Correspondence|Keywords?|Abbreviations?|Number of words|"
                    r"\d+\s*email|[*\u2020]?\s*These authors contributed|[*]?\s*Correspondence to)\b",
                    plain,
                    flags=re.IGNORECASE,
                )
                or re.match(r"^-?\s*\d+\b", stripped)
            )
            if starts_metadata:
                in_plain_metadata = True
                continue
            if in_plain_metadata:
                if not stripped:
                    continue
                if stripped.startswith("## ") or re.match(r"^\*\*Abstract:\*\*", stripped, flags=re.IGNORECASE):
                    in_plain_metadata = False
                else:
                    continue
            if is_boilerplate_body_line(plain):
                continue
        output.append(line)
    return prefix + "\n".join(output)


def is_boilerplate_body_line(line: str) -> bool:
    if not line:
        return False
    lower = line.lower()
    if any(phrase in lower for phrase in BOILERPLATE_PHRASES):
        return True
    return bool(
        re.match(r"^(?:Page \d+ of \d+|\(page number not for citation purposes\)|www\.[\w.-]+\.com\b)", line, flags=re.IGNORECASE)
    )


def remove_duplicate_title_and_author_lines(text: str) -> str:
    prefix, body = split_frontmatter(text)
    lines = body.splitlines()
    h1_index = find_first_h1(lines)
    if h1_index is None:
        return text
    title = clean_title_text(lines[h1_index][2:])
    output: list[str] = []
    before_section = True
    skip_indices: set[int] = set()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        plain = stripped.strip("*_ ").strip()
        if index in skip_indices:
            index += 1
            continue
        if index == h1_index:
            output.append(line)
            index += 1
            continue
        if stripped.startswith("## "):
            heading_title, consumed = combine_split_title_heading(lines, index)
            if before_section and clean_title_text(heading_title).lower() == title.lower():
                skip_indices.update(consumed)
                index += 1
                continue
            before_section = False
        if before_section:
            cleaned = clean_title_text(plain)
            if title and cleaned.lower().startswith(title.lower()):
                index += 1
                continue
            if re.match(r"^\*?\s*Corresponding author\b", plain, flags=re.IGNORECASE):
                index += 1
                continue
        output.append(line)
        index += 1
    return prefix + "\n".join(output)


def normalize_bold_section_labels(text: str) -> str:
    output: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        heading_match = re.match(r"^##\s+[_* ]*(?:\d+[\.\s]+)?(Abstract|Introduction|Results|Methods|Discussion|References|Supplementary|Review)[_* ]*$", stripped, flags=re.IGNORECASE)
        if heading_match:
            output.append(f"## {heading_match.group(1).title()}")
            continue
        bold_match = re.match(r"^\*\*(Abstract|Introduction|Results|Methods|Discussion|References|Supplementary|Review):\*\*\s*(.*)$", stripped, flags=re.IGNORECASE)
        if bold_match:
            output.append(f"## {bold_match.group(1).title()}")
            if bold_match.group(2).strip():
                output.append("")
                output.append(bold_match.group(2).strip())
            continue
        output.append(line)
    return "\n".join(output)


def remove_empty_markdown_headings(text: str) -> str:
    return re.sub(r"(?m)^\s*#{1,6}\s*$\n?", "", text)


def remove_running_headers_inline(text: str) -> str:
    patterns = [
        r"Nature Communications\|\s*\(\d{4}\)\s*\d+:\d+",
        r"Article\s+https?://doi\.org/\S+",
        r"Microbial Cell Factories\s+\d{4},\s*\d+:\d+\s+https?://\S+",
        r"Page\s+\d+\s+of\s+\d+",
        r"\(page number not for citation purposes\)",
    ]
    for pattern in patterns:
        text = re.sub(rf"(?im)^\s*{pattern}\s*$\n?", "", text)
        text = re.sub(rf"\s+{pattern}\s+", " ", text, flags=re.IGNORECASE)
    lines = [line for line in text.splitlines() if not is_boilerplate_body_line(line.strip().strip("*_ "))]
    return re.sub(r"[ \t]{2,}", " ", "\n".join(lines))


def remove_placeholder_affiliations(text: str) -> str:
    text = re.sub(r"(?im)^\s*\d+\s+TBA\s*$\n?", "", text)
    return re.sub(r"\b\d+\s+TBA\b", "", text)


def apply_replacement_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def repair_hyphenated_pdf_breaks(text: str) -> str:
    def replace_break(match: re.Match[str]) -> str:
        left, right = match.groups()
        combined = f"{left}{right}"
        replacement = DEHYPHENATED_WORD_REPLACEMENTS.get(combined.lower())
        if replacement:
            return apply_replacement_case(combined, replacement)
        return f"{left}-{right}"

    text = re.sub(r"\b([A-Za-z]{3,})-\s*\n\s*([a-z]{2,})\b", replace_break, text)
    for source, target in DEHYPHENATED_WORD_REPLACEMENTS.items():
        split = re.sub(r"([a-z])([a-z]+)", r"\1-\2", source, count=1)
        text = re.sub(rf"\b{re.escape(split)}\b", target, text, flags=re.IGNORECASE)
    text = re.sub(r"\bmechan-ical\b", "mechanical", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpro-duction\b", "production", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsea-lants\b", "sealants", text, flags=re.IGNORECASE)
    text = re.sub(r"\bboo-\s+", "bio-", text, flags=re.IGNORECASE)
    return text


def normalize_reference_blocks(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    in_references = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^## References\b", stripped, flags=re.IGNORECASE):
            in_references = True
            output.append("## References")
            continue
        if stripped.startswith("## ") and not re.match(r"^## References\b", stripped, flags=re.IGNORECASE):
            in_references = False
            output.append(line)
            continue
        if in_references:
            cleaned = remove_running_headers_inline(line).strip()
            if not cleaned:
                output.append("")
                continue
            parts = re.split(r"(?<!^)\s+(?=\d{1,3}\.\s+[A-Z])", cleaned)
            output.extend(part.strip() for part in parts if part.strip())
            continue
        output.append(line)
    return "\n".join(output)


def qualify_repeated_section_headings(text: str) -> str:
    seen: dict[str, int] = {}
    seen_titles: set[str] = set()
    supplementary_context = False
    output: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^(##) (Results|Methods|References|Discussion|Supplementary)\s*$", line.strip(), flags=re.IGNORECASE)
        if not match:
            output.append(line)
            continue
        base = match.group(2).title()
        count = seen.get(base, 0)
        if count == 0:
            title = base
        elif supplementary_context and base != "Supplementary":
            title = f"Supplementary {base}"
        else:
            title = f"{base} (continued {count + 1})"
        while title.lower() in seen_titles:
            count += 1
            title = f"{base} (continued {count + 1})"
        seen[base] = seen.get(base, 0) + 1
        seen_titles.add(title.lower())
        if base == "Supplementary":
            supplementary_context = True
        output.append(f"## {title}")
    return "\n".join(output)


def reorder_intro_before_results(text: str) -> str:
    lines = text.splitlines()
    headings = [(index, line.strip()) for index, line in enumerate(lines) if line.startswith("## ")]
    result_entry = next(((index, title) for index, title in headings if title == "## Results"), None)
    intro_entry = next(((index, title) for index, title in headings if title == "## Introduction"), None)
    if not result_entry or not intro_entry or intro_entry[0] < result_entry[0]:
        return text
    intro_start = intro_entry[0]
    next_heading = next((index for index, _ in headings if index > intro_start), len(lines))
    intro_block = lines[intro_start:next_heading]
    remaining = lines[:intro_start] + lines[next_heading:]
    insert_at = next((index for index, line in enumerate(remaining) if line == "## Results"), None)
    if insert_at is None:
        return text
    return "\n".join(remaining[:insert_at] + intro_block + [""] + remaining[insert_at:])


def remove_duplicate_frontmatter_dates(text: str) -> str:
    frontmatter_match = re.match(r"(?s)\A---\n(.*?)\n---\n\n", text)
    if not frontmatter_match:
        return text
    frontmatter = frontmatter_match.group(1).lower()
    if "received:" not in frontmatter and "accepted:" not in frontmatter and "journal:" not in frontmatter:
        return text

    prefix = text[: frontmatter_match.end()]
    rest = text[frontmatter_match.end() :]
    title_match = re.match(r"(?s)(# .+?\n\n)(.*)", rest)
    if not title_match:
        return text
    title = title_match.group(1)
    body = title_match.group(2)
    metadata_block = r"(?:(?:Received|Accepted|Published online|Revised)\s*\n\s*(?:\d{1,2}\s+\w+\s+\d{4})\s*\n\s*)+"
    body = re.sub(rf"\A{metadata_block}", "", body, flags=re.IGNORECASE)
    body = strip_leading_duplicate_metadata_lines(body, frontmatter)
    return prefix + title + body


def strip_leading_duplicate_metadata_lines(body: str, frontmatter: str) -> str:
    lines = body.splitlines()
    output_start = 0
    saw_metadata = False
    for index, line in enumerate(lines[:12]):
        stripped = line.strip()
        if not stripped:
            output_start = index + 1
            continue
        normalized = normalize_for_compare(stripped)
        is_date = bool(re.fullmatch(r"\d{1,2}\s+\w+\s+\d{4}", stripped))
        is_label = normalized in {"received", "accepted", "revised", "published online"}
        is_journal = f'journal: "{stripped.lower()}"' in frontmatter or f"journal: {stripped.lower()}" in frontmatter
        if is_date or is_label or is_journal:
            saw_metadata = True
            output_start = index + 1
            continue
        break
    if saw_metadata:
        return "\n".join(lines[output_start:]).lstrip()
    return body
