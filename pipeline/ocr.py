"""
pipeline/ocr.py — Extração de timestamp e camera_id de vídeos de câmera-armadilha.

Estágio 1 — Metadados do arquivo (ffprobe):
    Tenta ler creation_time, date ou DateTimeOriginal dos tags do container.
    Retorna location_source="metadata" se bem-sucedido.

Estágio 2 — OCR no overlay visual:
    Extrai o primeiro frame, recorta a barra inferior (12% da altura) e aplica
    OCR com pytesseract (primário) ou easyocr (fallback).
    Formato Bushnell: 0004 [ícones] 19°C 66°F 11/01/2025 08:14:30 0007
    Retorna location_source="ocr" se bem-sucedido.

Fallback:
    location_source="manual", todos os campos None.

Uso:
    meta = extract_video_metadata("/path/to/video.avi")
    print(meta.camera_id, meta.captured_at, meta.temperature_c)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Fração da altura do frame que constitui a barra de overlay (medida pelo baixo)
_OVERLAY_FRACTION = 0.12
# Fração mínima da barra que deve ser preta para confirmar que é overlay
_BLACK_THRESHOLD = 0.5


@dataclass
class VideoMetadata:
    """Metadados extraídos de um vídeo de câmera-armadilha.

    Attributes:
        camera_id:       ID da câmera (ex: "0004"), ou None se não encontrado.
        captured_at:     Timestamp ISO 8601 (ex: "2025-01-11T08:14:30"), ou None.
        temperature_c:   Temperatura em Celsius, ou None.
        location_source: Origem dos dados: "metadata", "ocr" ou "manual".
    """

    camera_id: str | None
    captured_at: str | None
    temperature_c: float | None
    location_source: str


# ── Estágio 1: metadados de arquivo ──────────────────────────────────────────


def _probe_metadata(video_path: str) -> VideoMetadata | None:
    """Tenta extrair timestamp de metadados do container via ffprobe.

    Campos tentados: creation_time, date, DateTimeOriginal.
    Formatos suportados: ISO 8601 e variantes comuns.

    Returns:
        VideoMetadata com location_source="metadata" se encontrado, None caso contrário.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        tags = data.get("format", {}).get("tags", {})
        # Normaliza chaves para lowercase
        tags = {k.lower(): v for k, v in tags.items()}

        raw = (
            tags.get("creation_time")
            or tags.get("date")
            or tags.get("datetimeoriginal")
        )
        if not raw:
            return None

        ts = _parse_iso_loose(raw)
        if not ts:
            return None

        logger.info("Metadados encontrados: creation_time=%s → %s", raw, ts)
        return VideoMetadata(
            camera_id=None,
            captured_at=ts,
            temperature_c=None,
            location_source="metadata",
        )

    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return None


def _parse_iso_loose(raw: str) -> str | None:
    """Converte string de data/hora para ISO 8601 com tolerância a formatos variados."""
    raw = raw.strip().replace("T", " ").replace("Z", "").strip()
    # "2025-01-11 08:14:30" ou "2025-01-11 08:14:30.000000"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[\s_](\d{2}):(\d{2}):(\d{2})", raw)
    if m:
        yr, mo, dy, hh, mm, ss = m.groups()
        return f"{yr}-{mo}-{dy}T{hh}:{mm}:{ss}"
    # "11/01/2025 08:14:30" (DD/MM/YYYY)
    m2 = re.match(r"(\d{1,2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", raw)
    if m2:
        dy, mo, yr, hh, mm, ss = m2.groups()
        return f"{yr}-{mo.zfill(2)}-{dy.zfill(2)}T{hh}:{mm}:{ss}"
    return None


# ── Estágio 2: OCR no overlay visual ─────────────────────────────────────────


def _extract_overlay_bar(video_path: str) -> np.ndarray | None:
    """Extrai a barra de overlay do primeiro frame do vídeo.

    Returns:
        Array BGR recortado (barra preta inferior), ou None se não encontrada.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Não foi possível abrir o vídeo: %s", video_path)
        return None
    try:
        ok, frame = cap.read()
        if not ok:
            return None
        h = frame.shape[0]
        cut = int(h * (1.0 - _OVERLAY_FRACTION))
        bar = frame[cut:, :]
        # Verifica que a barra é predominantemente escura (overlay real)
        gray = cv2.cvtColor(bar, cv2.COLOR_BGR2GRAY)
        dark_ratio = np.mean(gray < 80)
        if dark_ratio < _BLACK_THRESHOLD:
            logger.debug("Barra inferior não é overlay escuro (dark_ratio=%.2f)", dark_ratio)
            return None
        return bar
    finally:
        cap.release()


def _ocr_pytesseract(bar: np.ndarray) -> str | None:
    """OCR com pytesseract. Pré-processa: upscale 3× + threshold binário."""
    try:
        import pytesseract  # noqa: PLC0415
    except ImportError:
        return None

    big = cv2.resize(bar, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
    try:
        text = pytesseract.image_to_string(thresh, config="--psm 6 --oem 3")
        return text.strip() if text.strip() else None
    except Exception as exc:
        logger.debug("pytesseract falhou: %s", exc)
        return None


def _ocr_easyocr(bar: np.ndarray) -> str | None:
    """OCR com easyocr (fallback). Retorna texto concatenado."""
    try:
        import easyocr  # noqa: PLC0415
    except ImportError:
        return None

    try:
        reader = easyocr.Reader(["en"], verbose=False)
        results = reader.readtext(bar, detail=0)
        return " ".join(results).strip() if results else None
    except Exception as exc:
        logger.debug("easyocr falhou: %s", exc)
        return None


# ── Parsing do texto OCR ──────────────────────────────────────────────────────


def _parse_overlay_text(text: str) -> VideoMetadata | None:
    """Extrai campos estruturados do texto OCR do overlay Bushnell.

    Formato esperado (variações toleradas):
        0004  [ícones]  19°C  66°F  11/01/2025  08:14:30  0007

    Returns:
        VideoMetadata com location_source="ocr", ou None se parsing falhar.
    """
    # Normaliza: remove caracteres não-alfanuméricos problemáticos mas mantém /:°%
    text = text.replace("\n", " ")

    # camera_id: primeiro grupo de 4 dígitos isolado (antes dos ícones)
    cam_match = re.search(r"\b(\d{4})\b", text)
    camera_id = cam_match.group(1) if cam_match else None

    # temperatura Celsius: número seguido de °C (ou %C, GC, etc.)
    temp_match = re.search(r"\b(\d{1,3})\s*[°%oO]\s*[Cc°]", text, re.IGNORECASE)
    temperature_c: float | None = float(temp_match.group(1)) if temp_match else None
    if temperature_c is None:
        # Fallback easyocr: "19 %" sem letra C — pega o primeiro valor no intervalo de Celsius
        for m in re.finditer(r"\b(\d{1,3})\s*%", text):
            val = float(m.group(1))
            if -30 <= val <= 60:
                temperature_c = val
                break

    # data DD/MM/YYYY (tolerante a espaço em branco extra)
    # Fix "11/ 01" (espaço após barra) e "0 1/" (easyocr divide dígitos antes da barra)
    text_clean = re.sub(r"(\d)/\s+(\d)", r"\1/\2", text)
    text_clean = re.sub(r"(\d)\s+(\d)/", r"\1\2/", text_clean)
    date_match = re.search(r"(\d{1,2})/(\d{2})/(\d{4})", text_clean)

    # hora HH:MM:SS (tolerante a espaços: "08 : 14:30")
    text_time = re.sub(r"(\d+)\s*:\s*(\d+)", r"\1:\2", text_clean)
    time_match = re.search(r"(\d{2}):(\d{2}):(\d{2})", text_time)

    if not date_match or not time_match:
        logger.debug("Parsing incompleto — texto: %r", text)
        if camera_id is None and temperature_c is None:
            return None

    captured_at: str | None = None
    if date_match and time_match:
        day, month, year = date_match.groups()
        hour, minute, second = time_match.groups()
        captured_at = (
            f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            f"T{hour}:{minute}:{second}"
        )

    return VideoMetadata(
        camera_id=camera_id,
        captured_at=captured_at,
        temperature_c=temperature_c,
        location_source="ocr",
    )


def _ocr_video(video_path: str) -> VideoMetadata | None:
    """Estágio 2: extrai overlay e tenta OCR com pytesseract e easyocr."""
    bar = _extract_overlay_bar(video_path)
    if bar is None:
        return None

    text = _ocr_pytesseract(bar) or _ocr_easyocr(bar)
    if not text:
        logger.warning("Nenhum engine OCR disponível ou texto vazio.")
        return None

    logger.debug("Texto OCR bruto: %r", text)
    return _parse_overlay_text(text)


# ── API pública ───────────────────────────────────────────────────────────────


def extract_video_metadata(video_path: str) -> VideoMetadata:
    """Extrai timestamp e camera_id de um vídeo de câmera-armadilha.

    Tenta em sequência:
      1. Metadados do arquivo (ffprobe)
      2. OCR no overlay visual do primeiro frame
      3. Retorna campos None com location_source="manual"

    Args:
        video_path: Caminho local para o arquivo de vídeo.

    Returns:
        VideoMetadata com os campos extraídos.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    # Estágio 1
    meta = _probe_metadata(video_path)
    if meta is not None:
        return meta

    # Estágio 2
    meta = _ocr_video(video_path)
    if meta is not None:
        return meta

    # Fallback
    logger.warning("Sem metadados para %s — retornando manual.", video_path)
    return VideoMetadata(
        camera_id=None,
        captured_at=None,
        temperature_c=None,
        location_source="manual",
    )
