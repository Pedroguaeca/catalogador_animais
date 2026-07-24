"""
pipeline/speciesnet_handler.py — Lambda handler para o estágio SpeciesNet.

Consome siab-detections, classifica com SpeciesNet, consolida em Aparições
via gap tracking e grava cada Aparição no DynamoDB (siab-appearances).

Fluxo:
    siab-detections (SQS) → classify_species() → gap_track() → DynamoDB
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

from pipeline.megadetector import Detection
from pipeline.speciesnet import (
    BUCKET_NAME,
    MODEL_LOCAL_DIR,
    MODEL_S3_PREFIX,
    classify_species,
    download_speciesnet_from_s3,
)

logger = logging.getLogger(__name__)

BUCKET                  = os.environ.get("SIAB_BUCKET",              "siab-media-dev")
APPEARANCES_TABLE       = os.environ.get("APPEARANCES_TABLE",        "siab-appearances")
FRAME_ANNOTATIONS_TABLE = os.environ.get("FRAME_ANNOTATIONS_TABLE",  "siab-frame-annotations")
COUNTRY                 = os.environ.get("SIAB_COUNTRY",             "BRA")
GAP_FRAMES              = int(os.environ.get("GAP_FRAMES",           "15"))
MODEL_VERSION           = os.environ.get("SN_MODEL_VERSION",         "speciesnet-v5.0.5")

_ddb              = boto3.resource("dynamodb")
_appearances      = _ddb.Table(APPEARANCES_TABLE)
_frame_anns       = _ddb.Table(FRAME_ANNOTATIONS_TABLE)

# Cold start: garante que o modelo está disponível localmente antes da primeira invocação
download_speciesnet_from_s3(
    bucket=BUCKET_NAME,
    s3_prefix=MODEL_S3_PREFIX,
    local_dir=MODEL_LOCAL_DIR,
)


# ── Gap tracking ──────────────────────────────────────────────────────────────


def _frame_index(s3_key: str) -> int:
    """Extrai o índice numérico do frame a partir da chave S3.

    Exemplo: ``tenant/frames/video/frame_00003.jpg`` → 3
    """
    stem = os.path.splitext(os.path.basename(s3_key))[0]   # "frame_00003"
    return int(stem.split("_")[-1])


def _ts_offset(captured_at: str | None, frame_index: int) -> str | None:
    """Calcula o timestamp absoluto de um frame dado captured_at + índice em segundos."""
    if not captured_at:
        return None
    try:
        dt = datetime.fromisoformat(captured_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt + timedelta(seconds=frame_index)).isoformat()
    except ValueError:
        return None


def gap_track(
    classifications: list,
    gap_frames: int = GAP_FRAMES,
    video_camera_id: str | None = None,
    video_captured_at: str | None = None,
    video_temperature_c: float | None = None,
) -> list[dict]:
    """Consolida Classifications em Aparições por gap temporal.

    Agrupa frames consecutivos da mesma espécie onde o índice entre frames
    consecutivos não supera *gap_frames*. Cada grupo vira uma Aparição,
    usando o frame de maior ``species_score`` como best_crop.

    Args:
        classifications:     Saída de classify_species().
        gap_frames:          Máximo de frames de gap dentro da mesma Aparição.
        video_camera_id:     ID da câmera extraído pelo OCR.
        video_captured_at:   Timestamp ISO 8601 do início do vídeo (OCR).
        video_temperature_c: Temperatura extraída do overlay (OCR).

    Returns:
        Lista de dicts de Aparição prontos para gravação no DynamoDB.
    """
    if not classifications:
        return []

    by_species: dict[str, list] = {}
    for c in classifications:
        by_species.setdefault(c.species, []).append(c)

    appearances: list[dict] = []
    for clss in by_species.values():
        clss.sort(key=lambda c: _frame_index(c.frame_s3_key))

        group = [clss[0]]
        for c in clss[1:]:
            gap = _frame_index(c.frame_s3_key) - _frame_index(group[-1].frame_s3_key)
            if gap <= gap_frames:
                group.append(c)
            else:
                appearances.append(_group_to_appearance(
                    group,
                    video_camera_id=video_camera_id,
                    video_captured_at=video_captured_at,
                    video_temperature_c=video_temperature_c,
                ))
                group = [c]
        appearances.append(_group_to_appearance(
            group,
            video_camera_id=video_camera_id,
            video_captured_at=video_captured_at,
            video_temperature_c=video_temperature_c,
        ))

    return appearances


def _group_to_appearance(
    group: list,
    video_camera_id: str | None = None,
    video_captured_at: str | None = None,
    video_temperature_c: float | None = None,
) -> dict:
    """Converte um grupo de Classification numa dict de Aparição."""
    best      = max(group, key=lambda c: c.species_score)
    first_idx = _frame_index(group[0].frame_s3_key)
    last_idx  = _frame_index(group[-1].frame_s3_key)
    app_id    = str(uuid.uuid4())

    return {
        "appearance_id":    app_id,
        "species":          best.species,
        "species_score":    best.species_score,
        "taxonomic_level":  best.taxonomic_level,
        "taxonomic_path":   best.taxonomic_path,
        "model_version":    best.model_version or MODEL_VERSION,
        "frame_start":      first_idx,
        "frame_end":        last_idx,
        "ts_start":         _ts_offset(video_captured_at, first_idx),
        "ts_end":           _ts_offset(video_captured_at, last_idx),
        "support_frames":   len(group),
        "best_crop_s3_key": best.frame_s3_key,
        "camera_id":        best.camera_id or video_camera_id,
        "temperature_c":    video_temperature_c,
        "bbox":             list(best.bbox),
        "individual_count": 1,
        "review_status":    "pending",
    }


# ── Persistência por frame ────────────────────────────────────────────────────


def _write_frame_annotations(
    classifications: list,
    tenant_id: str,
    video_id: str,
) -> None:
    """Persiste classificação AI de cada frame em siab-frame-annotations.

    Chamado ANTES de gap_track(), para que os dados por frame não sejam descartados.
    SK: video_id#frame_idx (zero-padded 5 dígitos) — uma linha por frame.
    """
    # O MegaDetector pode retornar mais de uma detecção (bbox) no mesmo frame,
    # o que gera mais de uma Classification com o mesmo frame_idx. Por
    # ADR-0002 (individual_count=1 no MVP; tracking de múltiplos indivíduos
    # por frame é V1), mantemos aqui só a de maior confiança por frame — sem
    # isso o batch_writer tenta gravar duas chaves iguais no mesmo lote e o
    # DynamoDB rejeita o BatchWriteItem inteiro (ValidationException:
    # "Provided list of item keys contains duplicates").
    best_by_frame: dict[int, object] = {}
    for c in classifications:
        frame_idx = _frame_index(c.frame_s3_key)
        current_best = best_by_frame.get(frame_idx)
        if current_best is None or c.species_score > current_best.species_score:
            best_by_frame[frame_idx] = c

    with _frame_anns.batch_writer() as batch:
        for frame_idx, c in best_by_frame.items():
            batch.put_item(Item={
                "tenant_id":          tenant_id,
                "video_id#frame_idx": f"{video_id}#{frame_idx:05d}",
                "video_id":           video_id,
                "frame_idx":          frame_idx,
                "frame_s3_key":       c.frame_s3_key,
                "ai_species":         c.species,
                "ai_score":           Decimal(str(round(c.species_score, 4))),
                "bbox":               [Decimal(str(round(v, 4))) for v in c.bbox],
                # species/genus/family/order/class já são os valores corretos do
                # enum de nivel_taxonomico; blank/animal/unknown/vehicle não são
                # níveis taxonômicos de verdade — normaliza pra "unidentified".
                "taxonomic_level":    (
                    c.taxonomic_level
                    if c.taxonomic_level in ("species", "genus", "family", "order", "class")
                    else "unidentified"
                ),
            })


# ── Gravação no DynamoDB ──────────────────────────────────────────────────────


def _write_appearance(
    app: dict,
    tenant_id: str,
    project_id: str,
    video_id: str,
) -> None:
    """Grava uma Aparição na tabela siab-appearances.

    Chaves conforme data-model.md:
      - PK:   tenant_id
      - SK:   video_id#appearance_id
      - GSI-1 (by-species):        PK=tenant_id#project_id, SK=species#appearance_id
      - GSI-2 (by-review-status):  PK=tenant_id#review_status, SK=project_id#appearance_id
    """
    app_id = app["appearance_id"]
    item: dict = {
        # Chaves de partição e sort
        "tenant_id":               tenant_id,
        "video_id#appearance_id":  f"{video_id}#{app_id}",
        # GSI-1
        "tenant_id#project_id":    f"{tenant_id}#{project_id}",
        "species#appearance_id":   f"{app['species']}#{app_id}",
        # GSI-2
        "tenant_id#review_status": f"{tenant_id}#{app['review_status']}",
        "project_id#appearance_id": f"{project_id}#{app_id}",
        # Dados da aparição
        "project_id":              project_id,
        "video_id":                video_id,
        "appearance_id":           app_id,
        "species":                 app["species"],
        "species_score":           Decimal(str(round(app["species_score"], 4))),
        "taxonomic_level":         app["taxonomic_level"],
        "taxonomic_path":          app["taxonomic_path"],
        "model_version":           app["model_version"],
        "frame_start":             app["frame_start"],
        "frame_end":               app["frame_end"],
        "support_frames":          app["support_frames"],
        "best_crop_s3_key":        app["best_crop_s3_key"],
        "individual_count":        app["individual_count"],
        "review_status":           app["review_status"],
    }
    # Campos opcionais (omitidos se None, evitando AttributeValue nulos no DynamoDB)
    for field_name in ("camera_id", "ts_start", "ts_end"):
        if app.get(field_name) is not None:
            item[field_name] = app[field_name]
    if app.get("temperature_c") is not None:
        item["temperature_c"] = Decimal(str(round(app["temperature_c"], 1)))
    if app.get("bbox"):
        item["bbox"] = [Decimal(str(round(v, 4))) for v in app["bbox"]]

    _appearances.put_item(Item=item)


# ── Lambda handler ────────────────────────────────────────────────────────────


def lambda_handler(event, context):
    """Entry point SQS → SpeciesNet → DynamoDB appearances."""
    logging.getLogger().setLevel(logging.INFO)

    s3 = boto3.client("s3")

    for record in event.get("Records", []):
        body          = json.loads(record["body"])
        tenant_id     = body["tenant_id"]
        project_id    = body["project_id"]
        video_id      = body["video_id"]
        camera_id     = body.get("camera_id")
        captured_at   = body.get("captured_at")
        temperature_c = body.get("temperature_c")
        raw_dets      = body.get("detections", [])

        if not raw_dets:
            logger.info("Nenhuma detecção para video=%s — sem Aparições.", video_id)
            continue

        logger.info(
            "SpeciesNet | tenant=%s video=%s detecções=%d",
            tenant_id, video_id, len(raw_dets),
        )

        # Reconstitui Detection objects (classifica só animais)
        detections = [
            Detection(
                frame_s3_key=d["frame_s3_key"],
                confidence=d["confidence"],
                bbox=tuple(d["bbox"]),
                category=d["category"],
            )
            for d in raw_dets
            if d.get("category") == "animal"
        ]

        if not detections:
            logger.info("Sem detecções de animais para video=%s.", video_id)
            continue

        classifications = classify_species(
            detections=detections,
            tenant_id=tenant_id,
            bucket=BUCKET,
            s3_client=s3,
            country=COUNTRY,
        )

        _write_frame_annotations(classifications, tenant_id=tenant_id, video_id=video_id)

        appearances = gap_track(
            classifications,
            video_camera_id=camera_id,
            video_captured_at=captured_at,
            video_temperature_c=temperature_c,
        )

        logger.info(
            "Gap tracking | video=%s classificações=%d aparições=%d",
            video_id, len(classifications), len(appearances),
        )

        for app in appearances:
            _write_appearance(app, tenant_id=tenant_id, project_id=project_id, video_id=video_id)

        logger.info(
            "Aparições gravadas no DynamoDB | video=%s total=%d",
            video_id, len(appearances),
        )

    return {"statusCode": 200}
