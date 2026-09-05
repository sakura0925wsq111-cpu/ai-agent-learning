"""PaddleOCR adapter for page-level Study text recognition."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock
from typing import Protocol

import pymupdf

from core.config import settings


@dataclass(frozen=True)
class OCRBlock:
    text: str
    confidence: float
    bbox: list[int]

    def as_dict(self) -> dict:
        return asdict(self)


class OCREngine(Protocol):
    def recognize(self, pixmap: pymupdf.Pixmap) -> list[OCRBlock]: ...


class OCRUnavailableError(RuntimeError):
    pass


class OCRProcessingError(RuntimeError):
    pass


class PaddleOCREngine:
    """Lazy, serialized CPU adapter using the PP-OCRv5 mobile models."""

    def __init__(self) -> None:
        try:
            import numpy as np
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OCRUnavailableError(
                "OCR 依赖未安装，请重新安装 backend/requirements.txt"
            ) from exc

        self._np = np
        try:
            self._pipeline = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="PP-OCRv5_mobile_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device=settings.study_ocr_device,
                # Paddle 3.3.1 on Windows currently fails for this model's
                # oneDNN graph, while the plain CPU executor works correctly.
                enable_mkldnn=False,
            )
        except Exception as exc:
            raise OCRUnavailableError("OCR 模型加载失败") from exc
        self._lock = Lock()

    @staticmethod
    def _bbox(value) -> list[int]:
        points = value.tolist() if hasattr(value, "tolist") else value
        if len(points) == 4 and not isinstance(points[0], (list, tuple)):
            return [int(round(float(item))) for item in points]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return [
            int(round(min(xs))),
            int(round(min(ys))),
            int(round(max(xs))),
            int(round(max(ys))),
        ]

    def recognize(self, pixmap: pymupdf.Pixmap) -> list[OCRBlock]:
        image = self._np.frombuffer(pixmap.samples, dtype=self._np.uint8).reshape(
            pixmap.height,
            pixmap.width,
            pixmap.n,
        )
        try:
            with self._lock:
                results = list(self._pipeline.predict(image, text_rec_score_thresh=0.0))
        except Exception as exc:
            raise OCRProcessingError("OCR 页面识别失败") from exc
        if not results:
            return []

        payload = results[0].json
        if callable(payload):
            payload = payload()
        data = payload.get("res", payload)
        texts = data.get("rec_texts") or []
        scores = data.get("rec_scores") or []
        boxes = data.get("rec_boxes") or data.get("rec_polys") or []
        blocks = []
        for text, score, box in zip(texts, scores, boxes):
            clean_text = str(text).replace("\x00", "").strip()
            if clean_text:
                blocks.append(OCRBlock(
                    text=clean_text,
                    confidence=round(float(score), 6),
                    bbox=self._bbox(box),
                ))
        return sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))


_ocr_engine: PaddleOCREngine | None = None
_ocr_engine_lock = Lock()


def get_ocr_engine() -> PaddleOCREngine:
    global _ocr_engine
    if not settings.study_ocr_enabled:
        raise OCRUnavailableError("OCR 功能未启用")
    if _ocr_engine is None:
        with _ocr_engine_lock:
            if _ocr_engine is None:
                _ocr_engine = PaddleOCREngine()
    return _ocr_engine


__all__ = [
    "OCRBlock",
    "OCREngine",
    "OCRProcessingError",
    "OCRUnavailableError",
    "PaddleOCREngine",
    "get_ocr_engine",
]
