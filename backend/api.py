"""
backend/api.py — Backend FastAPI do SIAB (MVP interno).

Endpoints:
    POST   /projects/{project_id}/videos/upload      — upload de vídeo + OCR + fila
    GET    /projects/{project_id}/appearances         — lista aparições com filtros
    PATCH  /appearances/{appearance_id}/review        — revisão humana de aparição
    GET    /projects/{project_id}/appearances/export  — CSV exportação

Tenant fixo para MVP: "consultoria-teste" (sem Cognito).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pipeline.ocr import VideoMetadata, extract_video_metadata

logger = logging.getLogger(__name__)

# ── Configuração ───────────────────────────────────────────────────────────────

TENANT_ID         = os.environ.get("SIAB_TENANT",        "consultoria-teste")
BUCKET            = os.environ.get("SIAB_BUCKET",        "siab-media-dev")
APPEARANCES_TABLE = os.environ.get("APPEARANCES_TABLE",  "siab-appearances")
REVIEWS_TABLE     = os.environ.get("REVIEWS_TABLE",      "siab-reviews")
VIDEOS_QUEUE_NAME = os.environ.get("VIDEOS_QUEUE_NAME",  "siab-videos")
AWS_REGION        = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="SIAB API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8501",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Factories AWS (substituíveis em testes via patch) ─────────────────────────


def _s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def _sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)


def _appearances_table():
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(APPEARANCES_TABLE)


def _reviews_table():
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(REVIEWS_TABLE)


# ── Schemas ────────────────────────────────────────────────────────────────────


class ReviewRequest(BaseModel):
    action: Literal["confirm", "reject", "correct"]
    corrected_species: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _clean(obj):
    """Converte tipos DynamoDB (Decimal, sets) para tipos JSON-serializáveis."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, Decimal):
        f = float(obj)
        return int(f) if f == int(f) else f
    return obj


def _appearances_from_project(
    table,
    tenant_id: str,
    project_id: str,
) -> list[dict]:
    """Busca todas as aparições do projeto via GSI-1, com paginação automática."""
    pk   = f"{tenant_id}#{project_id}"
    items: list[dict] = []
    kwargs: dict = {
        "IndexName": "by-species",
        "KeyConditionExpression": Key("tenant_id#project_id").eq(pk),
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items


def _find_appearance(table, tenant_id: str, appearance_id: str) -> dict | None:
    """Localiza uma aparição pelo appearance_id no tenant."""
    resp = table.query(
        KeyConditionExpression=Key("tenant_id").eq(tenant_id),
        FilterExpression=Attr("appearance_id").eq(appearance_id),
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _period(ts_start: str | None) -> str:
    """Retorna o período do dia baseado no horário do timestamp."""
    if not ts_start:
        return ""
    try:
        hour = int(ts_start[11:13])
    except (IndexError, ValueError):
        return ""
    if 5 <= hour < 7:
        return "Amanhecer"
    if 7 <= hour < 17:
        return "Diurno"
    if 17 <= hour < 19:
        return "Entardecer"
    return "Noturno"


def _fauna_group(taxonomic_path: str | None) -> str:
    """Retorna o grupo de fauna a partir do caminho taxonômico."""
    if not taxonomic_path:
        return ""
    p = taxonomic_path.lower()
    if "mammalia" in p:
        return "Mamífero"
    if "aves" in p:
        return "Ave"
    if "reptilia" in p:
        return "Réptil"
    if "amphibia" in p:
        return "Anfíbio"
    return "Fauna"


def _ts_parts(ts: str | None) -> tuple[str, str]:
    """Separa ts_start ISO em (data DD/MM/YYYY, horário HH:MM:SS)."""
    if not ts or len(ts) < 19:
        return "", ""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
    except ValueError:
        return "", ""


# ── Endpoint 1 — Upload de vídeo ──────────────────────────────────────────────


@app.post("/projects/{project_id}/videos/upload")
async def upload_video(project_id: str, file: UploadFile = File(...)):
    """Faz upload de vídeo, roda OCR, publica na fila siab-videos."""
    tenant_id = TENANT_ID
    video_id  = str(uuid.uuid4())

    ext       = os.path.splitext(file.filename or "video.avi")[1].lower() or ".avi"
    s3_key    = f"{tenant_id}/videos/{video_id}{ext}"

    content = await file.read()

    # Upload para S3
    s3 = _s3_client()
    s3.put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=content,
        ContentType=file.content_type or "video/x-msvideo",
    )

    # OCR num arquivo temporário local
    meta: VideoMetadata
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        meta = extract_video_metadata(tmp_path)
    except Exception as exc:
        logger.warning("OCR falhou para %s: %s", video_id, exc)
        meta = VideoMetadata(
            camera_id=None,
            captured_at=None,
            temperature_c=None,
            location_source="manual",
        )
    finally:
        os.unlink(tmp_path)

    # Publica na fila siab-videos para o ingester Lambda consumir
    sqs = _sqs_client()
    queue_url = sqs.get_queue_url(QueueName=VIDEOS_QUEUE_NAME)["QueueUrl"]
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({
            "video_s3_key": s3_key,
            "tenant_id":    tenant_id,
            "project_id":   project_id,
            "video_id":     video_id,
        }),
    )

    logger.info(
        "Vídeo enviado | tenant=%s project=%s video_id=%s camera=%s ts=%s source=%s",
        tenant_id, project_id, video_id, meta.camera_id, meta.captured_at, meta.location_source,
    )

    return {
        "video_id":        video_id,
        "s3_key":          s3_key,
        "camera_id":       meta.camera_id,
        "captured_at":     meta.captured_at,
        "location_source": meta.location_source,
    }


# ── Endpoint 2 — Listar aparições ─────────────────────────────────────────────


@app.get("/projects/{project_id}/appearances")
def list_appearances(
    project_id: str,
    camera_id:     str | None = Query(default=None),
    species:       str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit:         int        = Query(default=100, ge=1, le=1000),
):
    """Lista aparições do projeto, ordenadas por ts_start. Filtros opcionais."""
    tenant_id = TENANT_ID
    table     = _appearances_table()
    items     = _appearances_from_project(table, tenant_id, project_id)

    # Filtros opcionais em Python (MVP — dataset pequeno)
    if camera_id:
        items = [a for a in items if a.get("camera_id") == camera_id]
    if species:
        items = [a for a in items if species.lower() in str(a.get("species", "")).lower()]
    if review_status:
        items = [a for a in items if a.get("review_status") == review_status]

    # Ordena por ts_start (None vai ao final)
    items.sort(key=lambda a: a.get("ts_start") or "9999")
    items = items[:limit]

    return {
        "project_id": project_id,
        "count":      len(items),
        "items":      [_clean(a) for a in items],
    }


# ── Endpoint 3 — Revisão humana ───────────────────────────────────────────────


@app.patch("/appearances/{appearance_id}/review")
def review_appearance(appearance_id: str, body: ReviewRequest):
    """Grava revisão e atualiza review_status da aparição."""
    tenant_id   = TENANT_ID
    app_tbl     = _appearances_table()
    rev_tbl     = _reviews_table()
    reviewed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    app_item = _find_appearance(app_tbl, tenant_id, appearance_id)
    if app_item is None:
        raise HTTPException(status_code=404, detail="Aparição não encontrada")

    sk         = app_item["video_id#appearance_id"]
    project_id = app_item.get("project_id", "")
    new_status = "confirmed" if body.action in ("confirm", "correct") else "rejected"
    new_species = (
        body.corrected_species if body.action == "correct" and body.corrected_species
        else str(app_item.get("species", ""))
    )

    # Grava revisão em siab-reviews
    review_record: dict = {
        "tenant_id":                tenant_id,
        "appearance_id#reviewed_at": f"{appearance_id}#{reviewed_at}",
        "appearance_id":            appearance_id,
        "project_id":               project_id,
        "action":                   body.action,
        "reviewed_at":              reviewed_at,
    }
    if body.corrected_species:
        review_record["corrected_species"] = body.corrected_species
    rev_tbl.put_item(Item=review_record)

    # Atualiza siab-appearances
    update_expr  = "SET review_status = :rs, #tr = :tr"
    expr_names   = {"#tr": "tenant_id#review_status"}
    expr_vals: dict = {
        ":rs": new_status,
        ":tr": f"{tenant_id}#{new_status}",
    }
    if body.action == "correct" and body.corrected_species:
        update_expr += ", species = :sp, #sa = :sa"
        expr_names["#sa"] = "species#appearance_id"
        expr_vals[":sp"]  = new_species
        expr_vals[":sa"]  = f"{new_species}#{appearance_id}"

    resp = app_tbl.update_item(
        Key={"tenant_id": tenant_id, "video_id#appearance_id": sk},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_vals,
        ReturnValues="ALL_NEW",
    )

    return _clean(resp.get("Attributes", {}))


# ── Endpoint 4 — Export CSV ───────────────────────────────────────────────────


@app.get("/projects/{project_id}/appearances/export")
def export_appearances(project_id: str):
    """Exporta aparições confirmadas em CSV (formato do formulário manual)."""
    tenant_id = TENANT_ID
    table     = _appearances_table()
    items     = _appearances_from_project(table, tenant_id, project_id)
    confirmed = [a for a in items if a.get("review_status") == "confirmed"]
    confirmed.sort(key=lambda a: a.get("ts_start") or "9999")

    fieldnames = [
        "nome_arquivo", "camera", "lat", "long",
        "data", "horario", "periodo",
        "nome_popular", "nome_cientifico", "grupo_fauna",
        "n_individuos", "qualidade", "obs",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for app in confirmed:
        ts       = app.get("ts_start")
        data, hr = _ts_parts(ts)
        writer.writerow({
            "nome_arquivo":    os.path.basename(str(app.get("best_crop_s3_key", ""))),
            "camera":          app.get("camera_id", ""),
            "lat":             "",
            "long":            "",
            "data":            data,
            "horario":         hr,
            "periodo":         _period(ts),
            "nome_popular":    "",
            "nome_cientifico": app.get("species", ""),
            "grupo_fauna":     _fauna_group(str(app.get("taxonomic_path", ""))),
            "n_individuos":    int(app.get("individual_count", 1)),
            "qualidade":       round(float(app.get("species_score", 0)), 4),
            "obs":             "",
        })

    filename = f"siab_{project_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
