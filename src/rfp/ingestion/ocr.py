"""OCR for PDF pages with no extractable text (scans, or text drawn as vector shapes)."""

from functools import lru_cache

import numpy as np
import structlog

log = structlog.get_logger()


@lru_cache
def _engine():
    from rapidocr_onnxruntime import (
        RapidOCR,  # optional heavy dependency, loaded on first use
    )

    return RapidOCR()


def ocr_lines(results, tolerance_ratio: float = 0.5) -> str:
    """Turn OCR boxes [(box, text, score), ...] into reading-order text lines."""
    items = []
    for box, text, _score in results or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), text))
    items.sort()
    lines: list[dict] = []
    for y, x, height, text in items:
        if (
            lines
            and abs(y - lines[-1]["y"]) <= max(height, lines[-1]["h"]) * tolerance_ratio
        ):
            lines[-1]["parts"].append((x, text))
        else:
            lines.append({"y": y, "h": height, "parts": [(x, text)]})
    return "\n".join(" ".join(t for _, t in sorted(line["parts"])) for line in lines)


def ocr_page(page, dpi: int = 200) -> str:
    """Render a PyMuPDF page and OCR it. Returns '' if OCR is unavailable or finds nothing."""
    try:
        pix = page.get_pixmap(dpi=dpi)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if pix.n == 4:
            image = image[:, :, :3]
        results, _ = _engine()(
            image[:, :, ::-1].copy()
        )  # RGB -> BGR, as the OCR model expects
        return ocr_lines(results)
    except ImportError:
        log.warning("ocr_unavailable", hint="uv add rapidocr-onnxruntime")
        return ""
    except Exception as exc:
        log.warning("ocr_failed", page=page.number + 1, error=str(exc))
        return ""
