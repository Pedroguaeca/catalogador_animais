"""
pipeline/megadetector_handler.py — Lambda handler para o estágio MegaDetector.

Lê mensagens da frames_queue (SQS), roda inferência com detect_animals()
e publica o resultado serializado na detections_queue.
"""

import json
import logging
import os

import boto3

from pipeline.megadetector import detect_animals

logger = logging.getLogger(__name__)

BUCKET              = os.environ.get("SIAB_BUCKET", "siab-media-dev")
DETECTIONS_QUEUE_URL = os.environ.get("DETECTIONS_QUEUE_URL", "")
MODEL_PATH          = os.environ.get("MD_MODEL_PATH", "/tmp/models/md_v5a.0.0.pt")
THRESHOLD           = float(os.environ.get("MD_THRESHOLD", "0.1"))

_sqs = boto3.client("sqs")


def lambda_handler(event, context):
    """Entry point SQS → MegaDetector → detections_queue."""
    for record in event.get("Records", []):
        body       = json.loads(record["body"])
        s3_keys    = body["s3_keys"]
        tenant_id  = body["tenant_id"]
        project_id = body["project_id"]
        video_id   = body["video_id"]

        logger.info(
            "MegaDetector | tenant=%s video=%s frames=%d",
            tenant_id, video_id, len(s3_keys),
        )

        detections = detect_animals(
            s3_keys=s3_keys,
            tenant_id=tenant_id,
            model_path=MODEL_PATH,
            threshold=THRESHOLD,
            bucket=BUCKET,
        )

        if not detections:
            logger.info("Nenhuma detecção acima de %.2f — video=%s", THRESHOLD, video_id)
            continue

        if not DETECTIONS_QUEUE_URL:
            logger.warning("DETECTIONS_QUEUE_URL não definida; pulando publicação.")
            continue

        _sqs.send_message(
            QueueUrl=DETECTIONS_QUEUE_URL,
            MessageBody=json.dumps({
                "tenant_id":  tenant_id,
                "project_id": project_id,
                "video_id":   video_id,
                "detections": [
                    {
                        "frame_s3_key": d.frame_s3_key,
                        "confidence":   d.confidence,
                        "bbox":         list(d.bbox),
                        "category":     d.category,
                    }
                    for d in detections
                ],
            }),
        )
        logger.info(
            "Publicado %d detecções na fila | video=%s", len(detections), video_id
        )

    return {"statusCode": 200}
