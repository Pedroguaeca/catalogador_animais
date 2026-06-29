"""
pipeline/megadetector.py — Estágio 1 do pipeline SIAB.

Responsabilidade: receber chaves S3 de frames, rodar inferência com o
MegaDetector v5 e devolver apenas os frames que contêm detecções acima
do threshold (animais, pessoas ou veículos).

Fluxo:
    S3 frames  →  download_model()  →  detect_animals()  →  [Detection]

O modelo é cacheado em /tmp/models/ no disco (persiste entre invocações
quentes em Lambda/container) e em memória dentro do processo.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from typing import Any

import boto3
import cv2
import numpy as np
from botocore.exceptions import BotoCoreError, ClientError
from megadetector.detection.run_detector import (
    DEFAULT_DETECTOR_LABEL_MAP,
    load_detector,
)

logger = logging.getLogger(__name__)

BUCKET_NAME    = os.environ.get("SIAB_BUCKET", "siab-media-dev")
MODEL_CACHE_DIR = os.environ.get("MD_CACHE_DIR", "/tmp/models")

# Mapa de categoria numérica → string legível
_LABEL_MAP: dict[str, str] = DEFAULT_DETECTOR_LABEL_MAP  # {'1':'animal', ...}

# Cache em memória: model_path → objeto detector carregado
_model_cache: dict[str, Any] = {}


# ── Tipos ─────────────────────────────────────────────────────────────────────


@dataclass
class Detection:
    """Uma única detecção em um frame S3.

    Attributes:
        frame_s3_key: Chave S3 do frame de origem.
        confidence:   Confiança da detecção (0–1).
        bbox:         Bounding box normalizada (x, y, w, h) em 0–1.
        category:     Categoria detectada: "animal", "person" ou "vehicle".
    """

    frame_s3_key: str
    confidence: float
    bbox: tuple[float, float, float, float]
    category: str


# ── Download do modelo ────────────────────────────────────────────────────────


def download_model(
    s3_bucket: str,
    model_s3_key: str,
    local_path: str,
    s3_client=None,
) -> str:
    """Garante que o modelo MegaDetector esteja disponível localmente.

    Se *local_path* já existir, retorna imediatamente (cache hit).
    Caso contrário, baixa de ``s3://s3_bucket/model_s3_key``.

    Args:
        s3_bucket:    Nome do bucket S3 que hospeda o modelo.
        model_s3_key: Chave S3 do arquivo do modelo (.pt).
        local_path:   Caminho local onde o modelo será salvo.
        s3_client:    Cliente boto3 S3. Se None, cria um novo.

    Returns:
        O *local_path* onde o modelo foi salvo.

    Raises:
        ClientError: Se o download do S3 falhar.
    """
    if os.path.exists(local_path):
        logger.info("Modelo em cache: %s", local_path)
        return local_path

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    s3 = s3_client or boto3.client("s3")

    logger.info("Baixando modelo de s3://%s/%s → %s", s3_bucket, model_s3_key, local_path)
    try:
        s3.download_file(s3_bucket, model_s3_key, local_path)
    except (BotoCoreError, ClientError) as exc:
        logger.error("Falha ao baixar modelo: %s", exc)
        raise

    logger.info("Modelo salvo em %s", local_path)
    return local_path


# ── Helpers internos ──────────────────────────────────────────────────────────


def _get_detector(model_path: str):
    """Carrega o detector, usando cache em memória para reutilização."""
    if model_path not in _model_cache:
        logger.info("Carregando MegaDetector de %s", model_path)
        _model_cache[model_path] = load_detector(model_path)
        logger.info("MegaDetector carregado.")
    return _model_cache[model_path]


def _download_frame(s3_client, bucket: str, key: str) -> np.ndarray | None:
    """Baixa um frame do S3 e decodifica como array BGR.

    Retorna None se o frame estiver corrompido ou inacessível,
    para que o batch continue sem interrupção.
    """
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Não foi possível baixar frame %s: %s", key, exc)
        return None

    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        logger.warning("Frame corrompido (imdecode falhou): %s", key)
        return None

    return img


def _parse_detections(raw: dict, frame_s3_key: str, threshold: float) -> list[Detection]:
    """Converte o resultado bruto do MegaDetector em lista de Detection."""
    detections: list[Detection] = []
    for d in raw.get("detections") or []:
        conf = float(d.get("conf", 0.0))
        if conf < threshold:
            continue
        category = _LABEL_MAP.get(str(d.get("category", "1")), "animal")
        x, y, w, h = d["bbox"]
        detections.append(Detection(
            frame_s3_key=frame_s3_key,
            confidence=conf,
            bbox=(float(x), float(y), float(w), float(h)),
            category=category,
        ))
    return detections


# ── Função principal ──────────────────────────────────────────────────────────


def detect_animals(
    s3_keys: list[str],
    tenant_id: str,
    model_path: str | None = None,
    threshold: float = 0.1,
    bucket: str | None = None,
    s3_client=None,
) -> list[Detection]:
    """Roda o MegaDetector v5 em uma lista de frames armazenados no S3.

    Apenas frames com pelo menos uma detecção acima de *threshold* geram
    entradas na lista retornada. Frames corrompidos são ignorados sem
    interromper o batch.

    Args:
        s3_keys:    Lista de chaves S3 dos frames a inspecionar.
        tenant_id:  Identificador do tenant (usado em logs).
        model_path: Caminho local do arquivo .pt do modelo. Padrão:
                    ``/tmp/models/md_v5a.0.0.pt``.
        threshold:  Confiança mínima para aceitar uma detecção (0–1).
        bucket:     Bucket S3. Padrão: variável SIAB_BUCKET.
        s3_client:  Cliente boto3 S3. Se None, cria um novo.

    Returns:
        Lista de Detection ordenada pela chave S3 de origem.
    """
    bucket     = bucket or BUCKET_NAME
    model_path = model_path or os.path.join(MODEL_CACHE_DIR, "md_v5a.0.0.pt")
    s3         = s3_client or boto3.client("s3")

    detector = _get_detector(model_path)

    results: list[Detection] = []
    discarded = 0

    for key in s3_keys:
        img = _download_frame(s3, bucket, key)
        if img is None:
            discarded += 1
            continue

        # MegaDetector espera RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        try:
            raw = detector.generate_detections_one_image(
                img_rgb,
                image_id=key,
                detection_threshold=threshold,
            )
        except Exception as exc:
            logger.warning("Inferência falhou para %s: %s", key, exc)
            discarded += 1
            continue

        frame_detections = _parse_detections(raw, key, threshold)

        if frame_detections:
            results.extend(frame_detections)
        else:
            discarded += 1
            logger.debug("Sem detecção acima de %.2f: %s", threshold, key)

    logger.info(
        "detect_animals | tenant=%s frames=%d detecções=%d descartados=%d",
        tenant_id, len(s3_keys), len(results), discarded,
    )
    return results
