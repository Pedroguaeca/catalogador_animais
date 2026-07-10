"""
pipeline/ingester.py — Estágio 0 do pipeline SIAB.

Responsabilidade: extrair frames de um vídeo local (1 frame/segundo) e
persistir cada frame no S3 sob o prefixo {tenant_id}/frames/{video_id}/.

Retorna metadados do vídeo e a lista de s3_keys gerados, que serão
consumidos pelos estágios seguintes (MegaDetector → SpeciesNet).
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import boto3
import cv2
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

BUCKET_NAME    = os.environ.get("SIAB_BUCKET",     "siab-media-dev")
CAMERAS_TABLE  = os.environ.get("CAMERAS_TABLE",  "siab-cameras")
VIDEOS_TABLE   = os.environ.get("VIDEOS_TABLE",   "siab-videos")
LOG_INTERVAL   = 10  # logar progresso a cada N frames


# ── Tipos ────────────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    """Resultado retornado por ingest_video()."""

    tenant_id: str
    project_id: str
    video_id: str
    s3_keys: list[str] = field(default_factory=list)
    total_frames: int = 0
    fps: float = 0.0
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _s3_key(tenant_id: str, video_id: str, frame_n: int) -> str:
    return f"{tenant_id}/frames/{video_id}/frame_{frame_n:05d}.jpg"


def _upload_frame(
    s3_client,
    frame_bgr,
    bucket: str,
    key: str,
    jpeg_quality: int = 92,
) -> None:
    """Codifica o frame como JPEG em memória e faz upload para o S3."""
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        raise RuntimeError(f"cv2.imencode falhou para a chave {key}")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=io.BytesIO(buf.tobytes()),
        ContentType="image/jpeg",
    )


def _open_video(video_path: str) -> cv2.VideoCapture:
    """Abre o vídeo e valida que está acessível."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Vídeo corrompido ou formato não suportado: {video_path}")
    return cap


# ── Função principal ──────────────────────────────────────────────────────────


def ingest_video(
    video_path: str,
    tenant_id: str,
    project_id: str,
    video_id: str,
    bucket: Optional[str] = None,
    s3_client=None,
) -> IngestResult:
    """Extrai 1 frame por segundo de *video_path* e salva cada um no S3.

    Args:
        video_path:  Caminho local para o arquivo de vídeo.
        tenant_id:   Identificador do tenant (prefixo S3).
        project_id:  Identificador do projeto (incluído nos metadados).
        video_id:    Identificador único do vídeo (usado no caminho S3).
        bucket:      Nome do bucket S3. Padrão: variável SIAB_BUCKET ou
                     ``siab-media-dev``.
        s3_client:   Cliente boto3 S3. Se None, cria um novo (útil para testes).

    Returns:
        IngestResult com s3_keys e metadados do vídeo.

    Raises:
        FileNotFoundError: se o arquivo de vídeo não existir.
        ValueError:        se o vídeo estiver corrompido.
        RuntimeError:      se a codificação JPEG falhar.
        ClientError:       se o upload para o S3 falhar.
    """
    bucket = bucket or BUCKET_NAME
    s3 = s3_client or boto3.client("s3")

    cap = _open_video(video_path)

    fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
    total_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frame_count / fps if fps > 0 else 0.0

    logger.info(
        "Iniciando ingestão | video_id=%s fps=%.2f frames=%d duração=%.1fs %dx%d",
        video_id, fps, total_frame_count, duration, width, height,
    )

    result = IngestResult(
        tenant_id=tenant_id,
        project_id=project_id,
        video_id=video_id,
        fps=fps,
        duration_seconds=duration,
        width=width,
        height=height,
    )

    frame_n = 0          # índice global de frames lidos
    saved_n = 0          # índice de frames salvos (1/segundo)
    stride  = max(1, round(fps))  # pular N frames entre capturas

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_n % stride == 0:
                key = _s3_key(tenant_id, video_id, saved_n)
                try:
                    _upload_frame(s3, frame, bucket, key)
                except (BotoCoreError, ClientError) as exc:
                    logger.error("Falha ao enviar frame %d para S3: %s", saved_n, exc)
                    raise

                result.s3_keys.append(key)
                saved_n += 1

                if saved_n % LOG_INTERVAL == 0:
                    logger.info(
                        "Progresso | video_id=%s frames_salvos=%d / ~%d",
                        video_id, saved_n, int(duration),
                    )

            frame_n += 1

    finally:
        cap.release()

    result.total_frames = saved_n
    logger.info(
        "Ingestão concluída | video_id=%s frames_salvos=%d bucket=%s",
        video_id, saved_n, bucket,
    )
    return result


# ── Helpers para metadados pós-OCR ────────────────────────────────────────────


def _ensure_camera(ddb_resource, tenant_id: str, project_id: str, camera_id: str) -> None:
    """Cria entrada de câmera em siab-cameras se ainda não existir (idempotente)."""
    try:
        table = ddb_resource.Table(CAMERAS_TABLE)
        table.update_item(
            Key={
                "tenant_id":         tenant_id,
                "project_id#camera_id": f"{project_id}#{camera_id}",
            },
            UpdateExpression=(
                "SET project_id   = if_not_exists(project_id,   :p),"
                "    camera_id    = if_not_exists(camera_id,    :c),"
                "    created_at   = if_not_exists(created_at,   :ts)"
            ),
            ExpressionAttributeValues={
                ":p":  project_id,
                ":c":  camera_id,
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("_ensure_camera | tenant=%s project=%s camera=%s", tenant_id, project_id, camera_id)
    except Exception as exc:
        logger.warning("_ensure_camera falhou para %s/%s/%s: %s", tenant_id, project_id, camera_id, exc)



def _claim_video_for_processing(
    ddb_resource,
    tenant_id: str,
    project_id: str,
    video_id: str,
) -> bool:
    """Muda atomicamente status 'uploaded' → 'processing' via conditional update.

    Retorna True se reclamado com sucesso.
    Retorna False se ConditionalCheckFailedException (vídeo já foi reclamado por
    outra invocação — reentrega SQS segura de ignorar).
    """
    table = ddb_resource.Table(VIDEOS_TABLE)
    try:
        table.update_item(
            Key={
                "tenant_id":           tenant_id,
                "project_id#video_id": f"{project_id}#{video_id}",
            },
            UpdateExpression="SET #status = :processing",
            ConditionExpression="#status = :uploaded",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":processing": "processing",
                ":uploaded":   "uploaded",
            },
        )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def _update_video_status(
    ddb_resource,
    tenant_id: str,
    project_id: str,
    video_id: str,
    camera_id: Optional[str],
    captured_at: Optional[str],
    temperature_c: Optional[float],
) -> None:
    """Grava campos OCR em siab-videos e avança status para 'processing'.

    Executado mesmo com OCR parcial/falha: o pipeline downstream trata os
    campos como opcionais. 'status' é palavra reservada no DynamoDB —
    obrigatório ExpressionAttributeNames.
    """
    try:
        table = ddb_resource.Table(VIDEOS_TABLE)
        table.update_item(
            Key={
                "tenant_id":           tenant_id,
                "project_id#video_id": f"{project_id}#{video_id}",
            },
            UpdateExpression=(
                "SET #status = :status,"
                "    camera_id = :camera_id,"
                "    captured_at = :captured_at,"
                "    temperature_c = :temperature_c,"
                "    processing_started_at = :now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status":       "processing",
                ":camera_id":    camera_id,
                ":captured_at":  captured_at,
                ":temperature_c": (
                    Decimal(str(temperature_c)) if temperature_c is not None else None
                ),
                ":now": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(
            "_update_video_status | tenant=%s video=%s status=processing"
            " camera=%s ts=%s temp=%s",
            tenant_id, video_id, camera_id, captured_at, temperature_c,
        )
    except Exception as exc:
        logger.warning(
            "_update_video_status falhou para %s/%s: %s", tenant_id, video_id, exc
        )


# ── Lambda handler ────────────────────────────────────────────────────────────


def lambda_handler(event, context):
    """Entry point SQS → ingest_video() → frames_queue.

    Evento SQS esperado (corpo de cada record):
        {
            "video_s3_key": "tenant-abc/videos/vid-001.mp4",
            "tenant_id":    "tenant-abc",
            "project_id":   "proj-001",
            "video_id":     "vid-001"
        }

    camera_id, captured_at e temperature_c são extraídos por OCR aqui,
    não mais enviados na mensagem SQS (migração do upload síncrono).
    """
    import json

    logging.getLogger().setLevel(logging.INFO)

    s3   = boto3.client("s3")
    sqs  = boto3.client("sqs")
    ddb  = boto3.resource("dynamodb")
    frames_queue_url = os.environ.get("FRAMES_QUEUE_URL", "")

    for record in event.get("Records", []):
        body = json.loads(record["body"])
        video_s3_key = body["video_s3_key"]
        tenant_id    = body["tenant_id"]
        project_id   = body["project_id"]
        video_id     = body["video_id"]

        if not _claim_video_for_processing(ddb, tenant_id, project_id, video_id):
            logger.warning(
                "Idempotência | video_id=%s já reclamado para processamento "
                "— ignorando reentrega SQS",
                video_id,
            )
            continue

        # Extensão original preservada na s3_key
        ext        = os.path.splitext(video_s3_key)[1] or ".avi"
        local_path = f"/tmp/{video_id}{ext}"
        logger.info("Baixando s3://%s/%s → %s", BUCKET_NAME, video_s3_key, local_path)
        s3.download_file(BUCKET_NAME, video_s3_key, local_path)

        # ── OCR: extrai camera_id, captured_at, temperature_c do vídeo ──
        camera_id = captured_at = temperature_c = None
        try:
            from pipeline.ocr import extract_video_metadata
            meta = extract_video_metadata(local_path)
            camera_id     = meta.camera_id
            captured_at   = meta.captured_at
            temperature_c = meta.temperature_c
            logger.info(
                "OCR | video_id=%s camera=%s ts=%s temp=%s source=%s",
                video_id, camera_id, captured_at, temperature_c, meta.location_source,
            )
        except Exception as exc:
            logger.warning("OCR falhou para %s: %s", video_id, exc)

        # ── Cria câmera em siab-cameras se necessário ────────────────────
        if camera_id:
            _ensure_camera(ddb, tenant_id, project_id, camera_id)

        # ── Atualiza siab-videos: status=processing + campos OCR ─────────
        _update_video_status(
            ddb, tenant_id, project_id, video_id,
            camera_id, captured_at, temperature_c,
        )

        try:
            result = ingest_video(
                video_path=local_path,
                tenant_id=tenant_id,
                project_id=project_id,
                video_id=video_id,
                bucket=BUCKET_NAME,
                s3_client=s3,
            )
        finally:
            if os.path.exists(local_path):
                os.unlink(local_path)

        if result.s3_keys and frames_queue_url:
            sqs.send_message(
                QueueUrl=frames_queue_url,
                MessageBody=json.dumps({
                    "tenant_id":  tenant_id,
                    "project_id": project_id,
                    "video_id":   video_id,
                    "s3_keys":    result.s3_keys,
                    "metadata": {
                        "total_frames":     result.total_frames,
                        "fps":              result.fps,
                        "duration_seconds": result.duration_seconds,
                        "camera_id":        camera_id,
                        "captured_at":      captured_at,
                        "temperature_c":    temperature_c,
                    },
                }),
            )
            logger.info(
                "Publicados %d frames na fila | video_id=%s",
                len(result.s3_keys), video_id,
            )
        elif not frames_queue_url:
            logger.warning("FRAMES_QUEUE_URL não definida; pulando publicação.")

    return {"statusCode": 200}
