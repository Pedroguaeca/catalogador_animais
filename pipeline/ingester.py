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
from typing import Optional

import boto3
import cv2
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

BUCKET_NAME = os.environ.get("SIAB_BUCKET", "siab-media-dev")
LOG_INTERVAL = 10  # logar progresso a cada N frames


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
    """
    import json
    import tempfile

    s3  = boto3.client("s3")
    sqs = boto3.client("sqs")
    frames_queue_url = os.environ.get("FRAMES_QUEUE_URL", "")

    for record in event.get("Records", []):
        body = json.loads(record["body"])
        video_s3_key = body["video_s3_key"]
        tenant_id    = body["tenant_id"]
        project_id   = body["project_id"]
        video_id     = body["video_id"]

        local_path = f"/tmp/{video_id}.mp4"
        logger.info("Baixando s3://%s/%s → %s", BUCKET_NAME, video_s3_key, local_path)
        s3.download_file(BUCKET_NAME, video_s3_key, local_path)

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
