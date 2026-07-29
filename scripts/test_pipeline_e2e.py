#!/usr/bin/env python3
"""
scripts/test_pipeline_e2e.py — Teste ponta a ponta na AWS.

Fluxo:
    vídeo sintético → S3 → siab-videos (SQS) → ingester Lambda
                       → siab-frames  (SQS) → megadetector Lambda
                       → siab-detections (SQS) → este script

Uso:
    python scripts/test_pipeline_e2e.py
"""

import json
import os
import sys
import tempfile
import time
import datetime

import boto3
import cv2
import numpy as np

# ── Configuração ──────────────────────────────────────────────────────────────
REGION            = "us-east-1"
BUCKET            = "siab-media-dev"
TENANT_ID         = "test-tenant"
PROJECT_ID        = "test-project"
VIDEOS_QUEUE_NAME = "siab-videos"
FRAMES_QUEUE_NAME = "siab-frames"
DETECTIONS_QUEUE  = "siab-detections"
POLL_TIMEOUT_S    = 420   # 7 minutos (cold start megadetector: download 268MB + load modelo ~3min)
LOG_LOOKBACK_S    = 600   # busca logs dos últimos 10 min no CloudWatch


# ── Vídeo sintético ───────────────────────────────────────────────────────────

def make_synthetic_video(path: str, fps: int = 5, seconds: int = 8) -> None:
    """Gera vídeo com silhueta de quadrúpede se movendo em fundo de mata."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (640, 480))
    rng    = np.random.default_rng(42)

    for n in range(fps * seconds):
        t = n / fps

        # Fundo: vegetação (verde escuro com ruído de textura)
        base  = np.array([35, 75, 35], dtype=np.int16)
        frame = np.clip(base + rng.integers(-25, 25, (480, 640, 3)), 0, 255).astype(np.uint8)

        # Silhueta animada: elipse + cabeça + pernas + cauda (estilo cervídeo)
        x = int(150 + 250 * (0.5 + 0.5 * np.sin(t * 0.7)))
        y = int(240 + 60  * np.sin(t * 1.1))

        body_color = (55, 80, 110)   # marrom-escuro (BGR)
        cv2.ellipse(frame, (x, y), (70, 38), 0, 0, 360, body_color, -1)
        cv2.circle(frame,  (x + 75, y - 12), 26, body_color, -1)

        leg_x = [x - 30, x - 10, x + 20, x + 45]
        for lx in leg_x:
            cv2.line(frame, (lx, y + 32), (lx - 4, y + 72), body_color, 5)

        cv2.line(frame, (x - 65, y - 8), (x - 95, y - 30), body_color, 6)  # cauda

        # Chifres (para silhueta de veado)
        tip_x, tip_y = x + 75, y - 12
        cv2.line(frame, (tip_x, tip_y - 24), (tip_x - 10, tip_y - 55), body_color, 3)
        cv2.line(frame, (tip_x, tip_y - 24), (tip_x + 12, tip_y - 52), body_color, 3)

        # Sombra sutil no chão
        cv2.ellipse(frame, (x + 10, y + 72), (55, 10), 0, 0, 360, (20, 50, 20), -1)

        writer.write(frame)

    writer.release()
    size_kb = os.path.getsize(path) // 1024
    print(f"  Vídeo gerado: {fps * seconds} frames, {seconds}s @ {fps} fps, {size_kb} KB → {path}")


# ── Helpers AWS ───────────────────────────────────────────────────────────────

def queue_url(sqs, name: str) -> str:
    return sqs.get_queue_url(QueueName=name)["QueueUrl"]


def drain_queue(sqs, url: str) -> int:
    """Remove mensagens antigas para evitar falsos positivos."""
    removed = 0
    while True:
        resp = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=0)
        msgs = resp.get("Messages", [])
        if not msgs:
            break
        for m in msgs:
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            removed += 1
    return removed


def fetch_cloudwatch_logs(log_group: str, lookback_s: int = LOG_LOOKBACK_S) -> list[str]:
    """Retorna as últimas linhas de log de um log group do CloudWatch."""
    logs   = boto3.client("logs", region_name=REGION)
    cutoff = int((time.time() - lookback_s) * 1000)
    lines  = []

    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=3,
        ).get("logStreams", [])

        for stream in streams:
            events = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=stream["logStreamName"],
                startTime=cutoff,
                limit=30,
            ).get("events", [])
            for e in events:
                ts  = datetime.datetime.fromtimestamp(e["timestamp"] / 1000).strftime("%H:%M:%S")
                lines.append(f"  [{ts}] {e['message'].rstrip()}")
    except Exception as exc:
        lines.append(f"  (erro ao buscar logs: {exc})")

    return lines


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    video_id = f"test-{int(time.time())}"    # único a cada execução
    s3_key   = f"{TENANT_ID}/videos/{video_id}.mp4"

    print("=" * 62)
    print("SIAB — Teste End-to-End: ingester → megadetector")
    print("=" * 62)
    print(f"  video_id  : {video_id}")
    print(f"  bucket    : {BUCKET}")
    print(f"  s3_key    : {s3_key}")

    s3  = boto3.client("s3",  region_name=REGION)
    sqs = boto3.client("sqs", region_name=REGION)

    # ── 1. Gera vídeo ────────────────────────────────────────────
    print("\n[1/4] Gerando vídeo sintético...")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        make_synthetic_video(video_path, fps=5, seconds=8)

        # ── 2. Upload S3 ──────────────────────────────────────────
        print(f"\n[2/4] Upload → s3://{BUCKET}/{s3_key}")
        s3.upload_file(video_path, BUCKET, s3_key)
        print("  Upload concluído.")
    finally:
        os.unlink(video_path)

    # ── 3. Drena fila + publica mensagem ──────────────────────────
    print(f"\n[3/4] Publicando na fila {VIDEOS_QUEUE_NAME}...")
    det_url  = queue_url(sqs, DETECTIONS_QUEUE)
    vid_url  = queue_url(sqs, VIDEOS_QUEUE_NAME)
    frm_url  = queue_url(sqs, FRAMES_QUEUE_NAME)

    for qname, qurl in [(DETECTIONS_QUEUE, det_url), (FRAMES_QUEUE_NAME, frm_url)]:
        drained = drain_queue(sqs, qurl)
        if drained:
            print(f"  {drained} mensagem(s) antiga(s) removida(s) de {qname}.")

    payload = {
        "video_s3_key": s3_key,
        "tenant_id":    TENANT_ID,
        "project_id":   PROJECT_ID,
        "video_id":     video_id,
    }
    resp = sqs.send_message(QueueUrl=vid_url, MessageBody=json.dumps(payload))
    print(f"  MessageId : {resp['MessageId']}")
    print(f"  Payload   : {json.dumps(payload)}")

    # ── 4. Polling siab-detections ────────────────────────────────
    print(f"\n[4/4] Aguardando resultado em {DETECTIONS_QUEUE}")
    print(f"      (cold start do container pode levar 20-40 s)")
    print(f"      timeout: {POLL_TIMEOUT_S}s\n")

    start     = time.time()
    resultado = None

    while time.time() - start < POLL_TIMEOUT_S:
        elapsed = int(time.time() - start)
        print(f"  [{elapsed:3d}s] aguardando...", end="\r", flush=True)

        resp = sqs.receive_message(
            QueueUrl=det_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10,
            MessageAttributeNames=["All"],
        )
        msgs = resp.get("Messages", [])

        if msgs:
            m = msgs[0]
            body = json.loads(m["Body"])
            sqs.delete_message(QueueUrl=det_url, ReceiptHandle=m["ReceiptHandle"])
            if body.get("video_id") == video_id:
                resultado = body
                break
            else:
                # Mensagem de outro teste — ignora e continua
                print(f"\n  (mensagem de video_id={body.get('video_id')} ignorada)")

    elapsed_total = int(time.time() - start)
    print()  # limpa carriage return

    # ── Resultado ─────────────────────────────────────────────────
    print("\n" + "=" * 62)

    if resultado is None:
        print(f"⏰  TIMEOUT após {elapsed_total}s — nenhum resultado recebido.")
        print("\n── Logs CloudWatch (últimos 10 min) ──────────────────────")
        for group in ["/aws/lambda/siab-ingester", "/aws/lambda/siab-megadetector"]:
            print(f"\n{group}:")
            lines = fetch_cloudwatch_logs(group)
            if lines:
                print("\n".join(lines[-15:]))   # últimas 15 linhas
            else:
                print("  (sem logs recentes)")
        return 1

    dets = resultado.get("detections", [])
    print(f"✅  Resultado recebido em {elapsed_total}s!")
    print(f"    tenant_id  : {resultado.get('tenant_id')}")
    print(f"    video_id   : {resultado.get('video_id')}")
    print(f"    Detecções  : {len(dets)}")

    if dets:
        categorias: dict[str, int] = {}
        for d in dets:
            categorias[d["category"]] = categorias.get(d["category"], 0) + 1
        top_conf = max(d["confidence"] for d in dets)
        print(f"    Categorias : {categorias}")
        print(f"    Top conf   : {top_conf:.3f}")
        print(f"\n    Detecções (primeiras 5):")
        for d in sorted(dets, key=lambda x: -x["confidence"])[:5]:
            bbox = [round(v, 3) for v in d["bbox"]]
            print(f"      {d['frame_s3_key']}  conf={d['confidence']:.3f}  cat={d['category']}  bbox={bbox}")
    else:
        print()
        print("    Nenhuma detecção acima do threshold (0.1).")
        print("    Pipeline funcionou — vídeo sintético não engana o MegaDetector.")
        print("    Para detecções reais, use vídeos de câmera-armadilha.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
