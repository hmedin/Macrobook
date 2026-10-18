"""Dev tool: inspect a cookbook PDF locally. Usage: python scripts/inspect_pdf.py <pdf> [page ...]

With no pages, prints page count and text coverage. With pages (0-based), renders PNGs
to the scratch dir given by $INSPECT_OUT (default: ./_inspect) and prints extracted text.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import pdf_tools  # noqa: E402

pdf = sys.argv[1]
pages = [int(p) for p in sys.argv[2:]]
out = Path(os.environ.get("INSPECT_OUT", "_inspect"))

if not pages:
    cov = pdf_tools.text_coverage(pdf)
    print("pages:", len(cov))
    print("pages with <40 chars of text (likely image-only):", sum(1 for c in cov if c < 40))
    print("coverage sample:", cov[:40])
else:
    out.mkdir(parents=True, exist_ok=True)
    for p in pages:
        png = pdf_tools.render_page(pdf, p, out / f"page_{p}.png")
        print(f"--- page {p} -> {png}")
        print(pdf_tools.page_text(pdf, p)[:1500])
