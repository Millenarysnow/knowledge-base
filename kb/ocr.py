"""扫描件 OCR 兜底。

依赖按需安装，本模块不在 requirements.txt 强制声明：
- PaddleOCR：中文效果好，安装命令见下文
- pytesseract：通用，但需要系统装好 tesseract-ocr 与 chi_sim 语言包

PaddleOCR 安装（推荐）：
    pip install "paddleocr>=2.7" "paddlepaddle>=2.5"
pytesseract 安装：
    pip install pytesseract pdf2image
    apt-get install -y tesseract-ocr tesseract-ocr-chi-sim poppler-utils

调用：
    from kb.ocr import pdf_ocr
    text = pdf_ocr(Path("/some/scanned.pdf"))
未安装任何 OCR 依赖时返回空字符串而不是抛异常，让导入流程继续。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

_PADDLE_OCR = None
_PADDLE_AVAILABLE: Optional[bool] = None
_TESSERACT_AVAILABLE: Optional[bool] = None


def _try_paddle() -> bool:
    global _PADDLE_OCR, _PADDLE_AVAILABLE
    if _PADDLE_AVAILABLE is not None:
        return _PADDLE_AVAILABLE
    try:
        from paddleocr import PaddleOCR  # type: ignore

        _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        _PADDLE_AVAILABLE = True
    except Exception:
        _PADDLE_AVAILABLE = False
    return _PADDLE_AVAILABLE


def _try_tesseract() -> bool:
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE
    try:
        import pytesseract  # type: ignore  # noqa: F401
        from pdf2image import convert_from_path  # type: ignore  # noqa: F401

        _TESSERACT_AVAILABLE = True
    except Exception:
        _TESSERACT_AVAILABLE = False
    return _TESSERACT_AVAILABLE


def available() -> List[str]:
    engines: List[str] = []
    if _try_paddle():
        engines.append("paddleocr")
    if _try_tesseract():
        engines.append("tesseract")
    return engines


def pdf_ocr_paddle(pdf_path: Path) -> str:
    if not _try_paddle() or _PADDLE_OCR is None:
        return ""
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception:
        try:
            import fitz  # type: ignore  # PyMuPDF

            return _paddle_via_pymupdf(pdf_path, fitz)
        except Exception:
            return ""
    images = convert_from_path(str(pdf_path), dpi=200)
    parts: List[str] = []
    for img in images:
        result = _PADDLE_OCR.ocr(img)
        for line in result or []:
            for box in line or []:
                if isinstance(box, (list, tuple)) and len(box) >= 2:
                    txt = box[1][0] if isinstance(box[1], (list, tuple)) else str(box[1])
                    if txt:
                        parts.append(str(txt))
    return "\n".join(parts).strip()


def _paddle_via_pymupdf(pdf_path: Path, fitz) -> str:
    if _PADDLE_OCR is None:
        return ""
    parts: List[str] = []
    doc = fitz.open(str(pdf_path))
    try:
        import io

        from PIL import Image  # type: ignore

        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            result = _PADDLE_OCR.ocr(img)
            for line in result or []:
                for box in line or []:
                    if isinstance(box, (list, tuple)) and len(box) >= 2:
                        txt = box[1][0] if isinstance(box[1], (list, tuple)) else str(box[1])
                        if txt:
                            parts.append(str(txt))
    finally:
        doc.close()
    return "\n".join(parts).strip()


def pdf_ocr_tesseract(pdf_path: Path) -> str:
    if not _try_tesseract():
        return ""
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except Exception:
        return ""
    images = convert_from_path(str(pdf_path), dpi=200)
    parts: List[str] = []
    for img in images:
        try:
            txt = pytesseract.image_to_string(img, lang="chi_sim+eng")
        except Exception:
            txt = pytesseract.image_to_string(img)
        if txt and txt.strip():
            parts.append(txt.strip())
    return "\n\n".join(parts).strip()


def pdf_ocr(pdf_path: Path) -> str:
    """优先使用 PaddleOCR，fallback 到 tesseract；都不可用则返回空字符串。"""
    if _try_paddle():
        text = pdf_ocr_paddle(pdf_path)
        if text:
            return text
    if _try_tesseract():
        return pdf_ocr_tesseract(pdf_path)
    return ""
