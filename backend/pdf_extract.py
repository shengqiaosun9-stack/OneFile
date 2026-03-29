from __future__ import annotations

from io import BytesIO
from typing import Dict

from pypdf import PdfReader

from text_cleaning import sanitize_text_strict


def extract_pdf_text(payload: bytes, max_chars: int = 12000) -> Dict[str, object]:
    reader = PdfReader(BytesIO(payload))
    page_count = len(reader.pages)
    parts = []
    total_chars = 0
    truncated = False

    for page in reader.pages:
        text = page.extract_text() or ""
        if not text.strip():
            continue
        remaining = max_chars - total_chars
        if remaining <= 0:
            truncated = True
            break
        if len(text) > remaining:
            parts.append(text[:remaining])
            total_chars += remaining
            truncated = True
            break
        parts.append(text)
        total_chars += len(text)

    merged = sanitize_text_strict("\n\n".join(parts), allow_empty=True, max_len=max_chars)
    return {
        "extracted_text": merged,
        "page_count": page_count,
        "text_chars": len(merged),
        "truncated": truncated,
    }
