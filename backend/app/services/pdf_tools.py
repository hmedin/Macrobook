"""Local PDF helpers: hashing, page text/rendering, and chunking for API size limits."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf as fitz

MAX_CHUNK_PAGES = 60
MAX_CHUNK_BYTES = 24 * 1024 * 1024  # stay well under the API's request size limit


def file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def page_count(path: str | Path) -> int:
    with fitz.open(path) as doc:
        return doc.page_count


def page_text(path: str | Path, page: int) -> str:
    with fitz.open(path) as doc:
        return doc[page].get_text()


def render_page(path: str | Path, page: int, out: str | Path, dpi: int = 90) -> Path:
    with fitz.open(path) as doc:
        pix = doc[page].get_pixmap(dpi=dpi)
        pix.save(str(out))
    return Path(out)


def text_coverage(path: str | Path) -> list[int]:
    """Characters of extractable text per page; near-zero means a scanned/image page."""
    with fitz.open(path) as doc:
        return [len(p.get_text().strip()) for p in doc]


def _subset(src: fitz.Document, start: int, end: int, downscale: bool) -> bytes:
    out = fitz.open()
    out.insert_pdf(src, from_page=start, to_page=end)
    if downscale:
        for page in out:
            for img in page.get_images(full=True):
                try:
                    out.rewrite_images(dpi_threshold=130, dpi_target=110, quality=70)
                except Exception:
                    pass
                break
    data = out.tobytes(garbage=4, deflate=True)
    out.close()
    return data


def split_chunks(path: str | Path, pages: list[int] | None = None) -> list[tuple[int, int, bytes]]:
    """Split into (first_page, last_page, pdf_bytes) chunks under the page and size limits.

    `pages` optionally restricts to recipe pages; consecutive runs are chunked together.
    Chunks over the byte limit are halved until they fit.
    """
    with fitz.open(path) as src:
        idx = pages if pages is not None else list(range(src.page_count))
        runs: list[tuple[int, int]] = []
        for p in idx:
            if runs and p == runs[-1][1] + 1 and p - runs[-1][0] < MAX_CHUNK_PAGES:
                runs[-1] = (runs[-1][0], p)
            else:
                runs.append((p, p))

        result: list[tuple[int, int, bytes]] = []
        stack = list(reversed(runs))
        while stack:
            start, end = stack.pop()
            data = _subset(src, start, end, downscale=True)
            if len(data) > MAX_CHUNK_BYTES and end > start:
                mid = (start + end) // 2
                stack.append((mid + 1, end))
                stack.append((start, mid))
            else:
                result.append((start, end, data))
        return result
