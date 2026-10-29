"""Heading-aware chunker that keeps a command and its lead-in together.

The corpus optimizer preferred sentence splits (~1036 characters) but those
splits glued the next heading onto the previous sentence. The pipeline design
for mixed technical and code text calls for code-aware chunks around 1000
characters. Fenced commands stay intact even when they are longer than that,
and the paragraph that says where to run the command stays on the same chunk.
"""

from __future__ import annotations

import re

FENCE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)
HEADING_RE = re.compile(r"(?m)^(#{1,3} .+)$")
MAX_CHARS = 1000


def chunk_text(text: str, *, suffix: str) -> list[tuple[str, str]]:
    """Return (heading, chunk_text) pairs.

    Markdown is split on headings. Shell, YAML, and config files are split on
    blank lines because they have no headings.
    """
    if _looks_like_markdown(text, suffix):
        return _chunk_markdown(text)
    return _chunk_plain(text, suffix)


def _looks_like_markdown(text: str, suffix: str) -> bool:
    return suffix == ".md" or text.lstrip().startswith("#")


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    sections = _sections(text)
    chunks: list[tuple[str, str]] = []
    for heading, body in sections:
        chunks.extend(_pack_section(heading, body))
    return chunks or [("document", text.strip())]


def _sections(text: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("document", text.strip())]
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(("document", preamble))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        sections.append((match.group(1).lstrip("#").strip(), body))
    return sections


def _pack_section(heading: str, body: str) -> list[tuple[str, str]]:
    if not body:
        return [(heading, heading)]
    blocks = _blocks(body)
    packed: list[tuple[str, str]] = []
    index = 0
    while index < len(blocks):
        kind, content = blocks[index]
        if kind == "fence":
            lead = ""
            if index > 0 and blocks[index - 1][0] == "prose":
                lead = _last_paragraph(blocks[index - 1][1])
            piece = _join(heading, lead, content)
            packed.append((heading, piece))
            index += 1
            continue
        if index + 1 < len(blocks) and blocks[index + 1][0] == "fence":
            index += 1
            continue
        for part in _split_prose(content):
            packed.append((heading, _join(heading, part)))
        index += 1
    return packed


def _blocks(body: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    position = 0
    for match in FENCE_RE.finditer(body):
        prose = body[position : match.start()].strip()
        if prose:
            blocks.append(("prose", prose))
        blocks.append(("fence", match.group(0).strip()))
        position = match.end()
    tail = body[position:].strip()
    if tail:
        blocks.append(("prose", tail))
    return blocks


def _last_paragraph(prose: str) -> str:
    parts = [part.strip() for part in re.split(r"\n\s*\n", prose) if part.strip()]
    return parts[-1] if parts else ""


def _split_prose(prose: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", prose) if part.strip()]
    if not paragraphs:
        return []
    groups: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if current and len(candidate) > MAX_CHARS:
            groups.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _join(heading: str, *parts: str) -> str:
    body = "\n\n".join(part for part in parts if part)
    if heading and heading != "document":
        return f"{heading}\n\n{body}".strip()
    return body.strip()


def _chunk_plain(text: str, suffix: str) -> list[tuple[str, str]]:
    label = suffix.lstrip(".") or "file"
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
    groups: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if current and len(candidate) > MAX_CHARS:
            groups.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        groups.append(current)
    return [(label, group) for group in groups]
