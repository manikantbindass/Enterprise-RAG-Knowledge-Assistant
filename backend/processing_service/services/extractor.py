"""
Text extraction service.

Supports:
  - PDF: PyMuPDF (fitz) with fallback to pdfplumber
  - DOCX: python-docx
  - Excel/CSV: pandas
  - HTML: BeautifulSoup4
  - TXT/MD: direct read
  - Images: Tesseract OCR via OCRService

Returns List[PageContent] — one item per page/sheet/section.
"""

from __future__ import annotations

import asyncio
import csv
import io
from pathlib import Path
from typing import Any

import structlog

from processing_service.models.schemas import PageContent
from processing_service.services.ocr_service import OCRService

logger = structlog.get_logger(__name__)

# MIME type → extractor method mapping
_MIME_EXTRACTORS: dict[str, str] = {
    "application/pdf": "extract_pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "extract_docx",
    "application/msword": "extract_docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "extract_excel",
    "application/vnd.ms-excel": "extract_excel",
    "text/csv": "extract_csv",
    "text/plain": "extract_text",
    "text/markdown": "extract_text",
    "text/html": "extract_html",
    "image/jpeg": "extract_image",
    "image/png": "extract_image",
    "image/tiff": "extract_image",
    "image/webp": "extract_image",
}


class ExtractionError(Exception):
    """Raised when text extraction fails irrecoverably."""
    pass


class TextExtractor:
    """
    Multi-format text extractor.

    All extraction methods are sync but wrapped with run_in_executor
    since underlying libs (PyMuPDF, python-docx) release the GIL
    intermittently but are not truly async.
    """

    def __init__(
        self,
        ocr_service: OCRService,
        max_pages: int = 5000,
        pdf_fallback: bool = True,
    ) -> None:
        self._ocr = ocr_service
        self._max_pages = max_pages
        self._pdf_fallback = pdf_fallback
        self._log = logger.bind(service="TextExtractor")

    async def extract(
        self, content: bytes, content_type: str, filename: str = ""
    ) -> list[PageContent]:
        """
        Dispatch extraction based on MIME type.

        Args:
            content: Raw file bytes.
            content_type: MIME type string.
            filename: Original filename (used for extension fallback).

        Returns:
            List of PageContent ordered by page number.

        Raises:
            ExtractionError: If all extraction methods fail.
        """
        method_name = _MIME_EXTRACTORS.get(content_type)

        if not method_name:
            # Try to infer from filename extension
            ext = Path(filename).suffix.lower()
            ext_map = {
                ".pdf": "extract_pdf",
                ".docx": "extract_docx",
                ".doc": "extract_docx",
                ".xlsx": "extract_excel",
                ".xls": "extract_excel",
                ".csv": "extract_csv",
                ".txt": "extract_text",
                ".md": "extract_text",
                ".html": "extract_html",
                ".htm": "extract_html",
                ".jpg": "extract_image",
                ".jpeg": "extract_image",
                ".png": "extract_image",
                ".tiff": "extract_image",
                ".tif": "extract_image",
            }
            method_name = ext_map.get(ext)

        if not method_name:
            self._log.warning(
                "unsupported_content_type",
                content_type=content_type,
                filename=filename,
            )
            raise ExtractionError(f"Unsupported content type: {content_type}")

        method = getattr(self, method_name)
        loop = asyncio.get_event_loop()

        # Image OCR is already async; others run in executor
        if method_name == "extract_image":
            return await method(content)

        pages: list[PageContent] = await loop.run_in_executor(
            None, method, content
        )

        self._log.info(
            "extraction_complete",
            method=method_name,
            pages=len(pages),
            total_chars=sum(len(p.text) for p in pages),
        )
        return pages

    # ── PDF ───────────────────────────────────────────────────────────────────

    def extract_pdf(self, content: bytes) -> list[PageContent]:
        """
        Extract text from PDF using PyMuPDF.

        Falls back to pdfplumber if PyMuPDF yields no text (scanned PDF).
        Scanned pages are flagged for OCR.
        """
        pages: list[PageContent] = []

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content, filetype="pdf")
            total_pages = min(len(doc), self._max_pages)

            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text("text")  # type: ignore[call-overload]

                metadata: dict[str, Any] = {
                    "page_width": page.rect.width,
                    "page_height": page.rect.height,
                }

                if text.strip():
                    pages.append(
                        PageContent(
                            page_num=page_num + 1,
                            text=text,
                            metadata=metadata,
                            extraction_method="pymupdf",
                        )
                    )
                else:
                    # Scanned page — flag for OCR (done in worker)
                    pages.append(
                        PageContent(
                            page_num=page_num + 1,
                            text="",
                            metadata={**metadata, "needs_ocr": True},
                            extraction_method="pymupdf_scanned",
                        )
                    )

            doc.close()
            self._log.info("pdf_extracted_pymupdf", pages=len(pages))
            return pages

        except ImportError:
            self._log.warning("pymupdf_not_installed_fallback_pdfplumber")
        except Exception as exc:
            self._log.warning("pymupdf_failed", error=str(exc))
            if not self._pdf_fallback:
                raise ExtractionError(f"PyMuPDF failed: {exc}")

        # Fallback: pdfplumber
        return self._extract_pdf_pdfplumber(content)

    def _extract_pdf_pdfplumber(self, content: bytes) -> list[PageContent]:
        """pdfplumber fallback for PDFs that PyMuPDF can't handle."""
        try:
            import pdfplumber  # type: ignore[import-untyped]

            pages: list[PageContent] = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for i, page in enumerate(pdf.pages[: self._max_pages]):
                    text = page.extract_text() or ""
                    pages.append(
                        PageContent(
                            page_num=i + 1,
                            text=text,
                            metadata={
                                "page_width": page.width,
                                "page_height": page.height,
                            },
                            extraction_method="pdfplumber",
                        )
                    )
            self._log.info("pdf_extracted_pdfplumber", pages=len(pages))
            return pages

        except Exception as exc:
            raise ExtractionError(f"pdfplumber failed: {exc}") from exc

    # ── DOCX ──────────────────────────────────────────────────────────────────

    def extract_docx(self, content: bytes) -> list[PageContent]:
        """Extract text from DOCX preserving paragraph structure."""
        try:
            from docx import Document  # type: ignore[import-untyped]

            doc = Document(io.BytesIO(content))
            paragraphs: list[str] = []

            for para in doc.paragraphs:
                if para.text.strip():
                    # Preserve heading levels in metadata via style
                    paragraphs.append(para.text)

            # Treat entire document as page 1 (DOCX has no true pages)
            full_text = "\n\n".join(paragraphs)
            return [
                PageContent(
                    page_num=1,
                    text=full_text,
                    metadata={
                        "paragraph_count": len(paragraphs),
                        "section_count": len(doc.sections),
                    },
                    extraction_method="python_docx",
                )
            ]
        except Exception as exc:
            raise ExtractionError(f"DOCX extraction failed: {exc}") from exc

    # ── Excel ─────────────────────────────────────────────────────────────────

    def extract_excel(self, content: bytes) -> list[PageContent]:
        """
        Extract text from Excel.

        Each sheet becomes a "page". Cells converted to string representation.
        """
        try:
            import pandas as pd  # type: ignore[import-untyped]

            pages: list[PageContent] = []
            xls = pd.ExcelFile(io.BytesIO(content))

            for sheet_num, sheet_name in enumerate(xls.sheet_names):
                df = xls.parse(sheet_name)
                # Convert to readable text: column names + rows
                text_parts = [f"Sheet: {sheet_name}"]
                text_parts.append("\t".join(str(c) for c in df.columns))
                for _, row in df.iterrows():
                    text_parts.append("\t".join(str(v) for v in row.values))

                pages.append(
                    PageContent(
                        page_num=sheet_num + 1,
                        text="\n".join(text_parts),
                        metadata={
                            "sheet_name": sheet_name,
                            "rows": len(df),
                            "columns": len(df.columns),
                        },
                        extraction_method="pandas_excel",
                    )
                )

            return pages

        except Exception as exc:
            raise ExtractionError(f"Excel extraction failed: {exc}") from exc

    # ── CSV ───────────────────────────────────────────────────────────────────

    def extract_csv(self, content: bytes) -> list[PageContent]:
        """Extract CSV as tab-separated text."""
        try:
            text_content = content.decode("utf-8-sig", errors="replace")
            reader = csv.reader(io.StringIO(text_content))
            rows = list(reader)

            text_parts: list[str] = []
            for row in rows:
                text_parts.append("\t".join(row))

            return [
                PageContent(
                    page_num=1,
                    text="\n".join(text_parts),
                    metadata={"row_count": len(rows)},
                    extraction_method="csv",
                )
            ]
        except Exception as exc:
            raise ExtractionError(f"CSV extraction failed: {exc}") from exc

    # ── HTML ──────────────────────────────────────────────────────────────────

    def extract_html(self, content: bytes) -> list[PageContent]:
        """Extract plain text from HTML using BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup  # type: ignore[import-untyped]

            # Try to detect encoding from meta tags
            soup = BeautifulSoup(content, "html.parser")

            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            title = soup.title.string if soup.title else None

            return [
                PageContent(
                    page_num=1,
                    text=text,
                    metadata={"html_title": title},
                    extraction_method="beautifulsoup",
                )
            ]
        except Exception as exc:
            raise ExtractionError(f"HTML extraction failed: {exc}") from exc

    # ── Plain text / Markdown ─────────────────────────────────────────────────

    def extract_text(self, content: bytes) -> list[PageContent]:
        """Decode and return plain text or Markdown as-is."""
        try:
            # Try UTF-8 first, then latin-1 fallback
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = content.decode("latin-1", errors="replace")

            return [
                PageContent(
                    page_num=1,
                    text=text,
                    metadata={},
                    extraction_method="direct",
                )
            ]
        except Exception as exc:
            raise ExtractionError(f"Text extraction failed: {exc}") from exc

    # ── Image (OCR) ───────────────────────────────────────────────────────────

    async def extract_image(self, content: bytes) -> list[PageContent]:
        """Run OCR on image bytes."""
        return [await self._ocr.ocr_image_bytes(content, page_num=1)]
