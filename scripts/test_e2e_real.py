#!/usr/bin/env python3
"""
scripts/test_e2e_real.py — Teste E2E com vídeos reais de câmera-armadilha.

Fluxo completo:
    AVI local → S3 → siab-videos (SQS) → ingester Lambda
              → siab-frames (SQS) → megadetector Lambda
              → siab-detections (SQS) → speciesnet Lambda
              → DynamoDB siab-appearances  ← polling deste script

Uso:
    python scripts/test_e2e_real.py
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import threading
import time

import boto3
from boto3.dynamodb.conditions import Key

# ── Configuração ───────────────────────────────────────────────────────────────

REGION          = "us-east-1"
BUCKET          = "siab-media-dev"
TENANT_ID       = "consultoria-teste"
PROJECT_ID      = "projeto-junho-2026"
VIDEOS_QUEUE    = "siab-videos"
APPEARANCES_TBL = "siab-appearances"
POLL_INTERVAL_S = 30
TOTAL_TIMEOUT_S = 900   # 15 minutos

LOG_GROUPS = [
    "/aws/lambda/siab-ingester",
    "/aws/lambda/siab-megadetector",
    "/aws/lambda/siab-speciesnet",
]

VIDEOS = [
    {
        "local_path": os.path.expanduser("~/Downloads/DSCF0007.AVI"),
        "video_id":   "DSCF0007",
        "camera_id":  "CAM_0004",
        "notes":      "diurno, aparentemente vazio",
    },
    {
        "local_path": os.path.expanduser("~/Downloads/DSCF0023.AVI"),
        "video_id":   "DSCF0023",
        "camera_id":  "CAM_0009",
        "notes":      "noturno P&B, paca esperada",
    },
    {
        "local_path": "/tmp/CAM5_extracted/CAM 5/DSCF0008.AVI",
        "video_id":   "DSCF0008",
        "camera_id":  "CAM_0005",
        "notes":      "noturno P&B, onça-parda esperada",
    },
]


# ── Upload com barra de progresso ──────────────────────────────────────────────

class _Progress:
    def __init__(self, total: int, label: str):
        self._total   = total
        self._seen    = 0
        self._label   = label
        self._lock    = threading.Lock()
        self._t_start = time.time()

    def __call__(self, bytes_transferred: int):
        with self._lock:
            self._seen += bytes_transferred
            pct     = self._seen / self._total * 100
            elapsed = time.time() - self._t_start
            speed   = self._seen / elapsed / 1024 / 1024 if elapsed > 0 else 0
            bar     = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
            print(
                f"\r  {self._label} [{bar}] {pct:5.1f}%  {speed:4.1f} MB/s",
                end="", flush=True,
            )
            if self._seen >= self._total:
                print()


def upload_video(s3, video: dict) -> str:
    """Faz upload do vídeo local para S3 e retorna a chave S3."""
    local = video["local_path"]
    vid   = video["video_id"]
    ext   = os.path.splitext(local)[1].lower()   # ".avi"
    key   = f"{TENANT_ID}/videos/{vid}{ext}"

    size = os.path.getsize(local)
    print(f"\n  Arquivo  : {local}")
    print(f"  Destino  : s3://{BUCKET}/{key}  ({size/1024/1024:.0f} MB)")

    cb = _Progress(size, vid)
    s3.upload_file(
        local, BUCKET, key,
        Callback=cb,
        ExtraArgs={"ContentType": "video/x-msvideo"},
    )
    return key


# ── CloudWatch logs ────────────────────────────────────────────────────────────

def tail_logs(logs_client, since_ms: int, limit: int = 10) -> list[str]:
    """Retorna as últimas linhas de log de todas as Lambdas do pipeline."""
    lines = []
    for group in LOG_GROUPS:
        try:
            streams = logs_client.describe_log_streams(
                logGroupName=group,
                orderBy="LastEventTime",
                descending=True,
                limit=2,
            ).get("logStreams", [])
            for stream in streams:
                events = logs_client.get_log_events(
                    logGroupName=group,
                    logStreamName=stream["logStreamName"],
                    startTime=since_ms,
                    limit=limit,
                ).get("events", [])
                for e in events:
                    ts  = datetime.datetime.fromtimestamp(e["timestamp"] / 1000).strftime("%H:%M:%S")
                    msg = e["message"].strip()
                    fn  = group.split("/")[-1]
                    lines.append(f"  [{ts}] {fn}: {msg}")
        except Exception:
            pass
    return sorted(lines)


# ── DynamoDB ───────────────────────────────────────────────────────────────────

def query_appearances(table, seen_ids: set) -> list[dict]:
    """Retorna aparições novas (não vistas antes) para o tenant."""
    items  = []
    kwargs = dict(KeyConditionExpression=Key("tenant_id").eq(TENANT_ID))
    while True:
        resp = table.query(**kwargs)
        for item in resp.get("Items", []):
            app_id = item.get("appearance_id", "")
            if app_id not in seen_ids:
                seen_ids.add(app_id)
                items.append(item)
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def fmt_appearance(item: dict) -> str:
    score  = float(item.get("species_score", 0))
    frames = f"frames {item.get('frame_start')}–{item.get('frame_end')}"
    supp   = item.get("support_frames", "?")
    vid    = item.get("video_id", "?")
    return (
        f"  ✦ {item['species']:<35}  conf={score:.3f}  {frames}  "
        f"support={supp}  level={item.get('taxonomic_level','?')}  "
        f"video={vid}"
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    s3   = boto3.client("s3",       region_name=REGION)
    sqs  = boto3.client("sqs",      region_name=REGION)
    logs = boto3.client("logs",     region_name=REGION)
    ddb  = boto3.resource("dynamodb", region_name=REGION)

    table = ddb.Table(APPEARANCES_TBL)

    print("=" * 68)
    print("SIAB — Teste E2E com vídeos reais de câmera-armadilha")
    print("=" * 68)
    print(f"  tenant_id  : {TENANT_ID}")
    print(f"  project_id : {PROJECT_ID}")
    print(f"  vídeos     : {len(VIDEOS)}")
    print(f"  timeout    : {TOTAL_TIMEOUT_S // 60} min")

    # ── 1. Upload ─────────────────────────────────────────────────────────────
    print("\n[1/3] Upload dos vídeos para S3")
    print("─" * 68)

    s3_keys: dict[str, str] = {}   # video_id → s3_key
    for v in VIDEOS:
        if not os.path.exists(v["local_path"]):
            print(f"\n  ⚠  NÃO ENCONTRADO: {v['local_path']}")
            continue
        print(f"\n  {v['video_id']} — {v['camera_id']}  ({v['notes']})")
        try:
            key = upload_video(s3, v)
            s3_keys[v["video_id"]] = key
            print(f"  ✓ upload concluído → {key}")
        except Exception as exc:
            print(f"\n  ✗ falha no upload: {exc}")

    if not s3_keys:
        print("\nNenhum vídeo disponível para processar.")
        return 1

    # ── 2. Publicar mensagens na fila ─────────────────────────────────────────
    print(f"\n[2/3] Publicando {len(s3_keys)} mensagem(s) na fila {VIDEOS_QUEUE}")
    print("─" * 68)

    vid_url = sqs.get_queue_url(QueueName=VIDEOS_QUEUE)["QueueUrl"]

    for v in VIDEOS:
        vid = v["video_id"]
        if vid not in s3_keys:
            continue
        payload = {
            "video_s3_key": s3_keys[vid],
            "tenant_id":    TENANT_ID,
            "project_id":   PROJECT_ID,
            "video_id":     vid,
        }
        resp = sqs.send_message(QueueUrl=vid_url, MessageBody=json.dumps(payload))
        print(f"  ✓ {vid}  MessageId={resp['MessageId']}")

    # ── 3. Monitoramento ──────────────────────────────────────────────────────
    print(f"\n[3/3] Monitorando pipeline (max {TOTAL_TIMEOUT_S // 60} min)")
    print("─" * 68)
    print("  Polling DynamoDB a cada 30s. CloudWatch atualizado a cada 60s.")
    print("  (cold start megadetector ~2-3 min; speciesnet ~3-5 min)\n")

    start_ms      = int(time.time() * 1000)
    start_wall    = time.time()
    seen_ids: set = set()
    all_apps: list[dict] = []
    last_log_check = 0.0
    tick = 0

    while True:
        elapsed = int(time.time() - start_wall)

        # ── Consulta DynamoDB ────────────────────────────────────────────────
        new_apps = query_appearances(table, seen_ids)
        if new_apps:
            all_apps.extend(new_apps)
            print(f"\n  [{elapsed:4d}s] 🐾  {len(new_apps)} nova(s) aparição(ões):")
            for item in new_apps:
                print(fmt_appearance(item))

        # ── Logs CloudWatch (a cada 60s) ─────────────────────────────────────
        now = time.time()
        if now - last_log_check >= 60:
            last_log_check = now
            log_lines = tail_logs(logs, since_ms=start_ms, limit=8)
            if log_lines:
                print(f"\n  [{elapsed:4d}s] 📋 Logs recentes:")
                for line in log_lines[-12:]:
                    print(line)

        # ── Verificação de conclusão ─────────────────────────────────────────
        vids_com_resultado = {a.get("video_id") for a in all_apps}
        vids_enviados      = set(s3_keys.keys())
        if vids_com_resultado >= vids_enviados:
            print(f"\n  ✅ Todos os {len(vids_enviados)} vídeo(s) processados em {elapsed}s.")
            break

        if elapsed >= TOTAL_TIMEOUT_S:
            print(f"\n  ⏰ Timeout após {elapsed}s.")
            sem_resultado = vids_enviados - vids_com_resultado
            if sem_resultado:
                print(f"     Sem aparições: {', '.join(sorted(sem_resultado))}")
                print("\n  Logs finais:")
                for line in tail_logs(logs, since_ms=start_ms, limit=15):
                    print(line)
            break

        tick += 1
        print(f"  [{elapsed:4d}s] aguardando... ({len(all_apps)} aparições até agora)", end="\r", flush=True)
        time.sleep(POLL_INTERVAL_S)

    # ── Relatório final ───────────────────────────────────────────────────────
    print("\n")
    print("=" * 68)
    print("RELATÓRIO FINAL")
    print("=" * 68)

    total_elapsed = int(time.time() - start_wall)
    print(f"  Tempo total  : {total_elapsed}s ({total_elapsed // 60}m{total_elapsed % 60:02d}s)")
    print(f"  Vídeos       : {len(s3_keys)} enviados / {len(s3_keys)} processados esperados")
    print(f"  Aparições    : {len(all_apps)}")

    if not all_apps:
        print("\n  Nenhuma aparição gravada no DynamoDB.")
        return 0

    # Por vídeo
    print("\n── Por vídeo ──────────────────────────────────────────────────────")
    by_video: dict[str, list] = {}
    for a in all_apps:
        by_video.setdefault(a.get("video_id", "?"), []).append(a)

    for v in VIDEOS:
        vid  = v["video_id"]
        apps = by_video.get(vid, [])
        tag  = f"({v['camera_id']}, {v['notes']})"
        print(f"\n  {vid} {tag}")
        if not apps:
            print("    — sem aparições")
            continue
        for a in sorted(apps, key=lambda x: -float(x.get("species_score", 0))):
            print(fmt_appearance(a))

    # Por espécie
    print("\n── Espécies detectadas ────────────────────────────────────────────")
    by_species: dict[str, list[float]] = {}
    for a in all_apps:
        sp = a.get("species", "?")
        by_species.setdefault(sp, []).append(float(a.get("species_score", 0)))

    for sp, scores in sorted(by_species.items(), key=lambda kv: -max(kv[1])):
        avg = sum(scores) / len(scores)
        print(f"  {sp:<40}  n={len(scores)}  max={max(scores):.3f}  avg={avg:.3f}")

    # Diurno vs noturno
    print("\n── Diurno vs Noturno ──────────────────────────────────────────────")
    diurno   = by_video.get("DSCF0007", [])
    noturno  = [a for vid in ("DSCF0023", "DSCF0008") for a in by_video.get(vid, [])]
    print(f"  Diurno  (DSCF0007): {len(diurno)} aparições")
    print(f"  Noturno (DSCF0023+DSCF0008): {len(noturno)} aparições")
    if diurno:
        sp_diurno = {a.get("species") for a in diurno}
        print(f"    Espécies diurnas  : {', '.join(sp_diurno)}")
    if noturno:
        sp_noturno = {a.get("species") for a in noturno}
        print(f"    Espécies noturnas : {', '.join(sp_noturno)}")

    # Nível taxonômico
    print("\n── Nível taxonômico resolvido ─────────────────────────────────────")
    by_level: dict[str, int] = {}
    for a in all_apps:
        lv = a.get("taxonomic_level", "?")
        by_level[lv] = by_level.get(lv, 0) + 1
    for lv, count in sorted(by_level.items(), key=lambda kv: -kv[1]):
        print(f"  {lv:<12}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
