"""
pipeline/speciesnet.py — Estágio 2 do pipeline SIAB.

Classifica espécies nas detecções do MegaDetector usando o SpeciesNet (Google).
Retorna uma Classification por detecção processada com sucesso.

Fluxo:
    list[Detection]  →  classify_species()  →  list[Classification]
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from pipeline.megadetector import Detection

logger = logging.getLogger(__name__)

BUCKET_NAME       = os.environ.get("SIAB_BUCKET", "siab-media-dev")
MODEL_NAME        = os.environ.get("SN_MODEL", "/tmp/models/speciesnet/v4.0.3a")
MODEL_S3_PREFIX   = os.environ.get("SN_MODEL_S3_PREFIX", "models/speciesnet/v4.0.3a")
MODEL_LOCAL_DIR   = os.environ.get("SN_MODEL_LOCAL_DIR", "/tmp/models/speciesnet/v4.0.3a")

# Cache em memória: model_name → objeto SpeciesNet carregado
_model_cache: dict[str, Any] = {}

# Arquivos esperados no diretório do modelo (info.json é o sentinel de cache)
_MODEL_FILES = [
    "info.json",
    "always_crop_99710272_22x8_v12_epoch_00148.pt",
    "always_crop_99710272_22x8_v12_epoch_00148.labels.20260609.txt",
    "taxonomy_release.20260609.txt",
    "geofence_release.20260609.json",
]


# ── Download do modelo do S3 ──────────────────────────────────────────────────


def download_speciesnet_from_s3(
    bucket: str,
    s3_prefix: str,
    local_dir: str,
    s3_client=None,
) -> str:
    """Baixa o diretório do modelo SpeciesNet do S3 para local_dir.

    Usa info.json como sentinel: se já existir, assume cache válido e pula o download.
    Retorna o caminho local do diretório do modelo.
    """
    sentinel = os.path.join(local_dir, "info.json")
    if os.path.exists(sentinel):
        logger.info("Modelo SpeciesNet em cache: %s", local_dir)
        return local_dir

    os.makedirs(local_dir, exist_ok=True)
    s3 = s3_client or boto3.client("s3")

    for filename in _MODEL_FILES:
        s3_key = f"{s3_prefix.rstrip('/')}/{filename}"
        local_path = os.path.join(local_dir, filename)
        logger.info("Baixando s3://%s/%s → %s", bucket, s3_key, local_path)
        s3.download_file(bucket, s3_key, local_path)

    logger.info("Modelo SpeciesNet baixado para %s", local_dir)
    return local_dir


# ── Tipos ─────────────────────────────────────────────────────────────────────


@dataclass
class Classification:
    """Resultado da classificação SpeciesNet para uma detecção.

    Attributes:
        appearance_id:    UUID provisional (será o ID da Aparição no DynamoDB).
        frame_s3_key:     Chave S3 do frame de origem.
        species:          Nome científico da espécie (ou nível taxonômico resolvido).
        species_score:    Confiança da classificação (0–1).
        taxonomic_level:  Nível resolvido: species/genus/family/order/class/blank/animal/unknown.
        taxonomic_path:   Hierarquia taxonômica sem UUID nem nome comum (separada por ;).
        camera_id:        ID da câmera (None no MVP).
        bbox:             Bounding box normalizada (x, y, w, h) herdada da detecção.
        model_version:    Versão do SpeciesNet que gerou a classificação.
    """

    appearance_id: str
    frame_s3_key: str
    species: str
    species_score: float
    taxonomic_level: str
    taxonomic_path: str
    camera_id: str | None
    bbox: tuple[float, float, float, float]
    model_version: str = ""


# ── Parsing de label ──────────────────────────────────────────────────────────


def _parse_label(label: str) -> tuple[str, str, str]:
    """Converte um label SpeciesNet em (species_name, taxonomic_level, taxonomic_path).

    Formato do label: ``uuid;class;order;family;genus;species_epithet;common_name``

    Exemplos:
        - ``abc;mammalia;rodentia;dasyproctidae;dasyprocta;leporina;agouti``
          → ("dasyprocta leporina", "species", "mammalia;rodentia;dasyproctidae;dasyprocta")
        - ``abc;;;;;;blank``
          → ("blank", "blank", "")
        - ``abc;;;;;;animal``
          → ("animal", "animal", "")
    """
    parts = label.split(";")
    if len(parts) < 7:
        return "unknown", "unknown", ""

    _cls, _order, _family, _genus, _species, _common = (
        parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
    )
    EMPTY = {"", "no cv result"}

    if _common == "blank":
        return "blank", "blank", ""
    if _common == "animal":
        return "animal", "animal", ""
    if _common == "human":
        return "homo sapiens", "species", "mammalia;primates;hominidae;homo"
    if _common == "vehicle":
        return "vehicle", "vehicle", ""

    tax_parts = [p for p in [_cls, _order, _family, _genus] if p and p not in EMPTY]
    taxonomic_path = ";".join(tax_parts)

    if _species and _species not in EMPTY:
        name = f"{_genus} {_species}" if _genus and _genus not in EMPTY else _species
        return name, "species", taxonomic_path
    if _genus and _genus not in EMPTY:
        return _genus, "genus", taxonomic_path
    if _family and _family not in EMPTY:
        return _family, "family", taxonomic_path
    if _order and _order not in EMPTY:
        return _order, "order", taxonomic_path
    if _cls and _cls not in EMPTY:
        return _cls, "class", taxonomic_path

    return "unknown", "unknown", ""


# ── Carregamento do modelo ────────────────────────────────────────────────────


def _get_model(model_name: str):
    """Carrega o SpeciesNet (classifier-only), cacheando entre invocações quentes."""
    if model_name not in _model_cache:
        from speciesnet.multiprocessing import SpeciesNet  # import pesado adiado
        logger.info("Carregando SpeciesNet: %s", model_name)
        _model_cache[model_name] = SpeciesNet(model_name, components="classifier")
        logger.info("SpeciesNet carregado.")
    return _model_cache[model_name]


# ── Função principal ──────────────────────────────────────────────────────────


def classify_species(
    detections: list[Detection],
    tenant_id: str,
    bucket: str | None = None,
    s3_client=None,
    country: str | None = None,
    model_name: str | None = None,
) -> list[Classification]:
    """Classifica espécies para uma lista de detecções do MegaDetector.

    Baixa os frames do S3, passa ao SpeciesNet com as bboxes do MegaDetector
    como dicas de recorte e retorna uma Classification por detecção.
    Frames que falham no download ou na inferência são ignorados sem interromper
    o batch.

    Args:
        detections:  Detecções do MegaDetector (frame_s3_key + bbox).
        tenant_id:   Identificador do tenant (para logs).
        bucket:      Bucket S3. Padrão: env SIAB_BUCKET.
        s3_client:   Cliente boto3 S3. Se None, cria um novo.
        country:     Código ISO 3166-1 alpha-3 para geofencing (ex: "BRA"). Opcional.
        model_name:  Identificador do modelo. Padrão: env SN_MODEL.

    Returns:
        Lista de Classification; pode ter menos itens que detections se houver
        falhas de download ou inferência.
    """
    if not detections:
        return []

    bucket     = bucket or BUCKET_NAME
    model_name = model_name or MODEL_NAME
    s3         = s3_client or boto3.client("s3")
    model      = _get_model(model_name)

    # Imports adiados (pesados)
    import PIL.Image
    from speciesnet.utils import BBox

    tmpdir = tempfile.mkdtemp(prefix="sn_", dir="/tmp")
    try:
        # ── Download de frames únicos ─────────────────────────────────────────
        key_to_path: dict[str, str] = {}
        for det in detections:
            if det.frame_s3_key in key_to_path:
                continue
            local = os.path.join(tmpdir, os.path.basename(det.frame_s3_key))
            try:
                s3.download_file(bucket, det.frame_s3_key, local)
                key_to_path[det.frame_s3_key] = local
            except (BotoCoreError, ClientError) as exc:
                logger.warning("Falha ao baixar frame %s: %s", det.frame_s3_key, exc)

        if not key_to_path:
            logger.warning("Nenhum frame baixado com sucesso para tenant=%s", tenant_id)
            return []

        # ── Uma Classification por Detection (sem multiprocessing) ────────────
        # Chama model.classifier diretamente para evitar SemLock do Lambda.
        classifications: list[Classification] = []
        n_frames = len(set(key_to_path.values()))
        logger.info("Iniciando classificação SpeciesNet | tenant=%s frames=%d", tenant_id, n_frames)

        for det in detections:
            local = key_to_path.get(det.frame_s3_key)
            if not local:
                continue

            try:
                img_pil = PIL.Image.open(local).convert("RGB")
            except Exception as exc:
                logger.warning("Falha ao abrir frame %s: %s", det.frame_s3_key, exc)
                continue

            # Converte bbox MegaDetector (x,y,w,h norm) → BBox SpeciesNet
            x, y, w, h = det.bbox
            bboxes = [BBox(xmin=x, ymin=y, width=w, height=h)]

            preprocessed = model.classifier.preprocess(img_pil, bboxes=bboxes)
            pred = model.classifier.predict(local, preprocessed)

            if "failures" in pred or "classifications" not in pred:
                logger.warning(
                    "SpeciesNet sem resultado para %s: %s",
                    det.frame_s3_key, pred.get("failures"),
                )
                continue

            cls_info = pred["classifications"]
            label    = cls_info["classes"][0]
            score    = float(cls_info["scores"][0])
            species, level, tax_path = _parse_label(label)

            classifications.append(Classification(
                appearance_id=str(uuid.uuid4()),
                frame_s3_key=det.frame_s3_key,
                species=species,
                species_score=score,
                taxonomic_level=level,
                taxonomic_path=tax_path,
                camera_id=None,
                bbox=det.bbox,
                model_version=pred.get("model_version", ""),
            ))

        logger.info(
            "classify_species | tenant=%s frames=%d classificações=%d",
            tenant_id, n_frames, len(classifications),
        )
        return classifications

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
