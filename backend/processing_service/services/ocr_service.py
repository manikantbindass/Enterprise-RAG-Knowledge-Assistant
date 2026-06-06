"""
OCR Service — Tesseract and Azure Document Intelligence.

Provides async batch OCR for image files and image-heavy PDFs.
Falls back gracefully: Azure → Tesseract → empty string.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

import structlog

from processing_service.models.schemas import PageContent

logger = structlog.get_logger(__name__)


class OCRService:
    """
    Async OCR wrapper supporting multiple backends.

    Priority order (configurable):
      1. Azure Document Intelligence (if configured)
      2. Tesseract (local, always available if installed)
    """

    def __init__(
        self,
        engine: str = "tesseract",
        tesseract_lang: str = "eng",
        tesseract_path: str | None = None,
        azure_endpoint: str | None = None,
        azure_key: str | None = None,
    ) -> None:
        self._engine = engine
        self._tesseract_lang = tesseract_lang
        self._tesseract_path = tesseract_path
        self._azure_endpoint = azure_endpoint
        self._azure_key = azure_key
        self._log = logger.bind(service="OCRService", engine=engine)

        if tesseract_path:
            try:
                import pytesseract  # type: ignore[import-untyped]

                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            except ImportError:
                pass

    async def ocr_image_bytes(self, image_bytes: bytes, page_num: int = 0) -> PageContent:
        """
        Run OCR on raw image bytes.

        Dispatches to Azure if configured, else Tesseract.
        """
        if self._engine == "azure" and self._azure_endpoint and self._azure_key:
            try:
                return await self._azure_ocr(image_bytes, page_num)
            except Exception as exc:
                self._log.warning(
                    "azure_ocr_failed_fallback_tesseract",
                    error=str(exc),
                    page_num=page_num,
                )

        if self._engine in ("tesseract", "azure"):  # azure already tried above
            return await self._tesseract_ocr(image_bytes, page_num)

        # disabled
        return PageContent(
            page_num=page_num,
            text="",
            metadata={"ocr_skipped": True},
            extraction_method="disabled",
        )

    async def ocr_batch(
        self, image_chunks: list[tuple[bytes, int]]
    ) -> list[PageContent]:
        """
        Process multiple images concurrently (max 4 parallel).

        Args:
            image_chunks: List of (image_bytes, page_num) tuples.

        Returns:
            PageContent list in same order as input.
        """
        semaphore = asyncio.Semaphore(4)

        async def bounded_ocr(img_bytes: bytes, pn: int) -> PageContent:
            async with semaphore:
                return await self.ocr_image_bytes(img_bytes, pn)

        tasks = [bounded_ocr(img, pn) for img, pn in image_chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        pages: list[PageContent] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._log.error(
                    "ocr_batch_item_failed",
                    page_num=image_chunks[i][1],
                    error=str(result),
                )
                pages.append(
                    PageContent(
                        page_num=image_chunks[i][1],
                        text="",
                        metadata={"ocr_error": str(result)},
                        extraction_method="error",
                    )
                )
            else:
                pages.append(result)  # type: ignore[arg-type]

        return pages

    async def _tesseract_ocr(self, image_bytes: bytes, page_num: int) -> PageContent:
        """Run Tesseract OCR in thread pool executor."""
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None, self._run_tesseract_sync, image_bytes
        )
        return PageContent(
            page_num=page_num,
            text=text,
            metadata={"ocr_engine": "tesseract", "lang": self._tesseract_lang},
            extraction_method="ocr",
        )

    def _run_tesseract_sync(self, image_bytes: bytes) -> str:
        """Blocking Tesseract call — run in executor."""
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]

            image = Image.open(io.BytesIO(image_bytes))
            # Convert to RGB if needed (Tesseract doesn't handle all modes)
            if image.mode not in ("RGB", "L", "RGBA"):
                image = image.convert("RGB")

            text: str = pytesseract.image_to_string(
                image,
                lang=self._tesseract_lang,
                config="--oem 3 --psm 3",  # LSTM OCR + auto page segmentation
            )
            return text

        except ImportError:
            self._log.error("pytesseract_not_installed")
            return ""
        except Exception as exc:
            self._log.error("tesseract_failed", error=str(exc))
            return ""

    async def _azure_ocr(self, image_bytes: bytes, page_num: int) -> PageContent:
        """
        Azure Document Intelligence OCR.

        Uses azure-ai-formrecognizer SDK.
        Extracts text with layout information.
        """
        loop = asyncio.get_event_loop()
        text, confidence = await loop.run_in_executor(
            None, self._run_azure_sync, image_bytes
        )
        return PageContent(
            page_num=page_num,
            text=text,
            metadata={
                "ocr_engine": "azure_document_intelligence",
                "confidence": confidence,
            },
            extraction_method="ocr",
        )

    def _run_azure_sync(self, image_bytes: bytes) -> tuple[str, float]:
        """Blocking Azure Form Recognizer call."""
        try:
            from azure.ai.formrecognizer import DocumentAnalysisClient  # type: ignore[import-untyped]
            from azure.core.credentials import AzureKeyCredential  # type: ignore[import-untyped]

            client = DocumentAnalysisClient(
                endpoint=self._azure_endpoint,
                credential=AzureKeyCredential(self._azure_key),
            )
            poller = client.begin_analyze_document(
                "prebuilt-read",
                document=io.BytesIO(image_bytes),
            )
            result = poller.result()

            lines: list[str] = []
            total_confidence: float = 0.0
            word_count = 0
            for page in result.pages:
                for line in (page.lines or []):
                    lines.append(line.content)
                for word in (page.words or []):
                    total_confidence += word.confidence
                    word_count += 1

            avg_confidence = total_confidence / word_count if word_count else 0.0
            return "\n".join(lines), avg_confidence

        except ImportError:
            self._log.error("azure_ai_formrecognizer_not_installed")
            return "", 0.0
        except Exception as exc:
            self._log.error("azure_ocr_error", error=str(exc))
            raise
