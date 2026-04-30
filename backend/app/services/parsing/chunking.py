"""Smart chunking strategy: natural paragraph priority + token range constraints."""

import re

from app.services.parsing.types import Chunk


# CJK-aware token estimation
def estimate_tokens(text: str) -> int:
    """Estimate token count with CJK awareness."""
    cjk_count = sum(1 for c in text if ord(c) > 0x2E80)
    ascii_text = "".join(c for c in text if ord(c) <= 0x2E80)
    ascii_words = len(ascii_text.split())
    return int(cjk_count * 1.5 + ascii_words * 1.3)


# Sentence boundary regex (handles Chinese and English)
SENTENCE_RE = re.compile(r'(?<=[。！？.!?])\s*')


def split_by_sentences(text: str, max_tokens: int = 1000) -> list[str]:
    """Split text at sentence boundaries, keeping each segment <= max_tokens."""
    sentences = SENTENCE_RE.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [text]

    segments = []
    current = ""
    for sentence in sentences:
        test = (current + " " + sentence).strip() if current else sentence
        if estimate_tokens(test) <= max_tokens:
            current = test
        else:
            if current:
                segments.append(current)
            # If single sentence exceeds limit, split by smaller units
            if estimate_tokens(sentence) > max_tokens:
                # Character-level split as fallback
                chars = list(sentence)
                chunk_chars = []
                for ch in chars:
                    chunk_chars.append(ch)
                    if estimate_tokens("".join(chunk_chars)) >= max_tokens:
                        segments.append("".join(chunk_chars))
                        chunk_chars = []
                if chunk_chars:
                    segments.append("".join(chunk_chars))
            else:
                current = sentence
    if current:
        segments.append(current)
    return segments


def chunk_text(
    content: str,
    doc_id: str,
    kb_id: str,
    file_hash: str = "",
    min_tokens: int = 500,
    max_tokens: int = 1000,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """
    Smart chunking with natural paragraph priority.

    Strategy:
    1. Split content into paragraphs
    2. Paragraphs in [min_tokens, max_tokens] range -> keep as-is
    3. Paragraphs > max_tokens -> split at sentence boundaries
    4. Paragraphs < min_tokens -> merge with adjacent paragraphs
    5. Add overlap between adjacent chunks
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    # Step 1: Classify paragraphs
    processed = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        tokens = estimate_tokens(para)

        if tokens < min_tokens:
            # Merge with adjacent paragraphs until >= min_tokens
            merged = para
            j = i + 1
            while j < len(paragraphs) and estimate_tokens(merged) < min_tokens:
                merged += "\n\n" + paragraphs[j]
                j += 1
            processed.append(merged)
            i = j
        elif tokens > max_tokens:
            # Split at sentence boundaries
            segments = split_by_sentences(para, max_tokens=max_tokens)
            processed.extend(segments)
            i += 1
        else:
            processed.append(para)
            i += 1

    # Step 2: Create chunks with overlap
    chunks = []
    for idx, text in enumerate(processed):
        # Add overlap from previous chunk
        if idx > 0 and chunks:
            prev_text = processed[idx - 1]
            prev_tokens = estimate_tokens(prev_text)
            if prev_tokens > overlap_tokens:
                # Take last ~overlap_tokens from previous
                overlap_text = _take_last_tokens(prev_text, overlap_tokens)
                text = overlap_text + "\n\n" + text

        chunk = Chunk(
            chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
            doc_id=doc_id,
            kb_id=kb_id,
            content=text,
            token_count=estimate_tokens(text),
            file_hash=file_hash,
        )
        chunks.append(chunk)

    return chunks


def _take_last_tokens(text: str, count: int) -> str:
    """Take approximately the last N tokens from text."""
    words = text.split()
    if not words:
        return ""

    # Estimate: each word/char is roughly tokens/len
    total_tokens = estimate_tokens(text)
    if total_tokens <= count:
        return text

    ratio = count / total_tokens
    take = max(1, int(len(words) * ratio))
    return " ".join(words[-take:])
