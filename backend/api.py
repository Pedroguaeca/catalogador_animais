"""
backend/api.py — Backend FastAPI do SIAB (MVP interno).

Endpoints:
    POST   /projects/{project_id}/videos/upload-url      — gera URL pré-assinada S3 + cria registro pending
    POST   /projects/{project_id}/videos/{video_id}/confirm — confirma upload; dispara pipeline via SQS
    GET    /projects/{project_id}/appearances             — lista aparições com filtros
    PATCH  /appearances/{appearance_id}/review            — revisão humana de aparição
    GET    /projects/{project_id}/appearances/export      — CSV exportação

Mudança de comportamento (upload):
    Antes: frontend enviava o vídeo no corpo da requisição → API fazia OCR síncrono e retornava
           camera_id/captured_at imediatamente. Limitado a 10 MB pelo API Gateway.
    Agora: frontend obtém URL pré-assinada S3, envia o vídeo DIRETO ao S3 (sem passar pelo
           API Gateway), depois confirma via /confirm. O OCR migrou para o ingester Lambda,
           que extrai camera_id/captured_at ao processar o vídeo. Sem limite de tamanho.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jose import ExpiredSignatureError, JWTError, jwk, jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Configuração ───────────────────────────────────────────────────────────────

_DEFAULT_TENANT         = os.environ.get("SIAB_TENANT",              "consultoria-teste")
BUCKET                  = os.environ.get("SIAB_BUCKET",              "siab-media-dev")
APPEARANCES_TABLE       = os.environ.get("APPEARANCES_TABLE",        "siab-appearances")
REVIEWS_TABLE           = os.environ.get("REVIEWS_TABLE",            "siab-reviews")
FRAME_ANNOTATIONS_TABLE = os.environ.get("FRAME_ANNOTATIONS_TABLE",  "siab-frame-annotations")
CAMERAS_TABLE           = os.environ.get("CAMERAS_TABLE",            "siab-cameras")
VIDEOS_TABLE            = os.environ.get("VIDEOS_TABLE",             "siab-videos")
VIDEOS_QUEUE_NAME       = os.environ.get("VIDEOS_QUEUE_NAME",        "siab-videos")
AWS_REGION              = os.environ.get("AWS_DEFAULT_REGION",       "us-east-1")

# Cognito — obrigatório em produção; ausente = modo dev (sem validação de assinatura)
_USER_POOL_ID    = os.environ.get("COGNITO_USER_POOL_ID",    "us-east-1_muBMGRYkB")
_APP_CLIENT_ID   = os.environ.get("COGNITO_APP_CLIENT_ID",   "50pl8rj5st1l9bt1eb8h5csqud")
_COGNITO_ISSUER  = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{_USER_POOL_ID}"
_JWKS_URL        = f"{_COGNITO_ISSUER}/.well-known/jwks.json"

# SIAB_JWT_VALIDATION=off desabilita verificação de assinatura (dev local sem Cognito)
_JWT_VALIDATION  = os.environ.get("SIAB_JWT_VALIDATION", "on").lower() != "off"

# Cache em memória das chaves públicas Cognito (recarregado ao encontrar kid desconhecido)
_jwks_cache: dict[str, dict] = {}   # kid → JWK dict

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


def _frame_annotations_table():
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(FRAME_ANNOTATIONS_TABLE)


def _cameras_table():
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(CAMERAS_TABLE)


def _videos_table():
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(VIDEOS_TABLE)


# ── Schemas ────────────────────────────────────────────────────────────────────


class UploadUrlRequest(BaseModel):
    filename:     str
    content_type: str = "video/x-msvideo"


class ReviewRequest(BaseModel):
    action: Literal["confirm", "reject", "correct"]
    corrected_species: str | None = None


class AnnotationRequest(BaseModel):
    video_id:          str
    frame_path:        str
    annotated_species: str
    annotation_source: Literal["ai_confirm", "chip_select", "new_category"]


class CameraCreate(BaseModel):
    camera_id: str
    name:      str | None = None
    latitude:  float | None = None
    longitude: float | None = None


class CameraUpdate(BaseModel):
    name:      str | None = None
    latitude:  float | None = None
    longitude: float | None = None


# ── Auth ───────────────────────────────────────────────────────────────────────


def _load_jwks(force: bool = False) -> None:
    """Busca as chaves públicas JWKS do Cognito e popula _jwks_cache (kid → JWK)."""
    global _jwks_cache
    if _jwks_cache and not force:
        return
    try:
        with urllib.request.urlopen(_JWKS_URL, timeout=5) as resp:
            data = json.loads(resp.read())
        _jwks_cache = {k["kid"]: k for k in data.get("keys", [])}
        logger.info("JWKS carregadas: %d chaves", len(_jwks_cache))
    except Exception as exc:
        logger.error("Falha ao carregar JWKS de %s: %s", _JWKS_URL, exc)


def _verify_jwt(token: str) -> dict:
    """Valida JWT Cognito: assinatura RS256, issuer, audience, expiração, token_use.

    Raises HTTPException(401) em qualquer falha de validação.
    Returns o payload decodificado e verificado.
    """
    if not _JWT_VALIDATION:
        # Modo dev: decodifica sem verificar (apenas quando SIAB_JWT_VALIDATION=off)
        import base64 as _b64
        payload_b64 = token.split(".")[1]
        pad = (4 - len(payload_b64) % 4) % 4
        return json.loads(_b64.b64decode(payload_b64 + "=" * pad))

    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token malformado.")

    kid = header.get("kid", "")
    if kid not in _jwks_cache:
        _load_jwks(force=True)
    if kid not in _jwks_cache:
        raise HTTPException(status_code=401, detail="Chave de assinatura desconhecida.")

    try:
        public_key = jwk.construct(_jwks_cache[kid])
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=_APP_CLIENT_ID,
            issuer=_COGNITO_ISSUER,
            options={"verify_at_hash": False},
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token inválido: {exc}")

    if payload.get("token_use") not in ("id", "access"):
        raise HTTPException(status_code=401, detail="token_use inválido.")

    return payload


def _jwt_payload(authorization: str | None) -> dict | None:
    """Valida o JWT do header Authorization.

    - Header ausente + validação ON  → HTTPException(401)   [produção]
    - Header ausente + validação OFF → retorna None          [dev local]
    - Token presente, inválido       → HTTPException(401)   [sempre]
    - Token presente, válido         → retorna payload       [sempre]
    """
    if not authorization or not authorization.startswith("Bearer "):
        if _JWT_VALIDATION:
            raise HTTPException(status_code=401, detail="Authorization header ausente.")
        return None  # dev local: sem token → fallback
    return _verify_jwt(authorization[7:])


def get_current_tenant(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Extrai custom:tenant_id do JWT Cognito verificado.
    Em produção (JWT_VALIDATION=on), header ausente resulta em 401."""
    payload = _jwt_payload(authorization)
    if payload is None:
        return _DEFAULT_TENANT  # só alcançável em dev (JWT_VALIDATION=off)
    tid = payload.get("custom:tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="custom:tenant_id ausente no token.")
    return str(tid)


def get_current_role(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Extrai custom:role do JWT Cognito verificado.
    Em produção (JWT_VALIDATION=on), header ausente resulta em 401."""
    payload = _jwt_payload(authorization)
    if payload is None:
        return "analyst"  # só alcançável em dev (JWT_VALIDATION=off)
    return str(payload.get("custom:role", "analyst"))


def get_current_sub(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Extrai o sub (user ID) do JWT Cognito verificado."""
    payload = _jwt_payload(authorization)
    if payload is None:
        return "anonymous"
    return str(payload.get("sub", "anonymous"))


def require_role(*allowed_roles: str):
    """Factory de dependência FastAPI para autorização por papel.

    Usage:
        @app.post("/path", dependencies=[Depends(require_role("approver", "admin"))])
    """
    def dependency(role: str = Depends(get_current_role)) -> str:
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permissão insuficiente. Necessário: {list(allowed_roles)}. Actual: {role}",
            )
        return role
    return dependency


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


# Curated genus → dashboard group. Covers common Brazilian/Pan-Tropical taxa.
# Incomplete by design — unlisted genera fall to "outros". Expand as needed.
_GENUS_GROUP: dict[str, str] = {
    # Mastofauna
    "dasyprocta": "mastofauna", "cuniculus": "mastofauna", "mazama": "mastofauna",
    "tamandua": "mastofauna", "myrmecophaga": "mastofauna", "puma": "mastofauna",
    "panthera": "mastofauna", "leopardus": "mastofauna", "nasua": "mastofauna",
    "procyon": "mastofauna", "eira": "mastofauna", "tayassu": "mastofauna",
    "pecari": "mastofauna", "tapirus": "mastofauna", "cerdocyon": "mastofauna",
    "chrysocyon": "mastofauna", "didelphis": "mastofauna", "hydrochoerus": "mastofauna",
    "dasypus": "mastofauna", "cabassous": "mastofauna", "bradypus": "mastofauna",
    "choloepus": "mastofauna", "alouatta": "mastofauna", "cebus": "mastofauna",
    "sapajus": "mastofauna", "callicebus": "mastofauna", "callithrix": "mastofauna",
    "speothos": "mastofauna",
    # Avifauna
    "psophia": "avifauna", "crax": "avifauna", "penelope": "avifauna",
    "crypturellus": "avifauna", "tinamus": "avifauna", "pteroglossus": "avifauna",
    "ramphastos": "avifauna", "ara": "avifauna", "amazona": "avifauna",
    "mitu": "avifauna", "ortalis": "avifauna", "pauxi": "avifauna",
    # Herpetofauna (répteis + anfíbios)
    "caiman": "herpetofauna", "melanosuchus": "herpetofauna", "paleosuchus": "herpetofauna",
    "eunectes": "herpetofauna", "boa": "herpetofauna", "corallus": "herpetofauna",
    "tupinambis": "herpetofauna", "iguana": "herpetofauna", "chelonoidis": "herpetofauna",
    "podocnemis": "herpetofauna", "rhinella": "herpetofauna", "leptodactylus": "herpetofauna",
}


def _fauna_group_dash(taxonomic_path: str | None, species: str | None = None) -> str:
    """Grupo de fauna para o dashboard: mastofauna / avifauna / herpetofauna / outros.

    Prioridade: palavras-chave na taxonomic_path → tabela de gêneros curada → 'outros'.
    """
    if taxonomic_path:
        p = taxonomic_path.lower()
        if "mammalia" in p:
            return "mastofauna"
        if "aves" in p:
            return "avifauna"
        if "reptilia" in p or "amphibia" in p:
            return "herpetofauna"
    genus = (species or "").strip().lower().split()[0] if species else ""
    return _GENUS_GROUP.get(genus, "outros")


def _ts_parts(ts: str | None) -> tuple[str, str]:
    """Separa ts_start ISO em (data DD/MM/YYYY, horário HH:MM:SS)."""
    if not ts or len(ts) < 19:
        return "", ""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
    except ValueError:
        return "", ""


def _presigned_url(s3_key: str | None, expiry: int = 3600) -> str | None:
    """Gera presigned URL para leitura de um objeto S3. Retorna None se key ausente ou falha."""
    if not s3_key:
        return None
    # Normaliza: remove prefixo s3://bucket/ se presente
    key = str(s3_key)
    if key.startswith("s3://"):
        parts = key[5:].split("/", 1)
        key = parts[1] if len(parts) > 1 else ""
    if not key:
        return None
    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=expiry,
        )
    except Exception:
        return None


def _frame_idx_from_path(frame_path: str) -> int:
    """Extrai índice numérico do frame. '69bf.../frame_00003.jpg' → 3"""
    stem = os.path.splitext(os.path.basename(frame_path))[0]
    return int(stem.split("_")[-1])


def _appearances_for_frame(video_id: str, frame_idx: int, tenant_id: str) -> list[dict]:
    """Retorna as aparições cujo intervalo [frame_start, frame_end] cobre frame_idx."""
    resp = _appearances_table().query(
        KeyConditionExpression=Key("tenant_id").eq(tenant_id)
            & Key("video_id#appearance_id").begins_with(f"{video_id}#")
    )
    return [
        a for a in resp.get("Items", [])
        if int(a.get("frame_start", 0)) <= frame_idx <= int(a.get("frame_end", 0))
    ]


def _ensure_camera(tenant_id: str, project_id: str, camera_id: str) -> bool:
    """Cria câmera provisória se ainda não existir. Retorna True se foi criada agora."""
    tbl = _cameras_table()
    try:
        tbl.put_item(
            Item={
                "tenant_id":          tenant_id,
                "project_id#camera_id": f"{project_id}#{camera_id}",
                "project_id":         project_id,
                "camera_id":          camera_id,
                "created_at":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            },
            ConditionExpression="attribute_not_exists(#sk)",
            ExpressionAttributeNames={"#sk": "project_id#camera_id"},
        )
        return True
    except tbl.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    except Exception as exc:
        logger.warning("_ensure_camera falhou para %s/%s/%s: %s", tenant_id, project_id, camera_id, exc)
        return False


def _check_discrepancy(appearance_id: str, app_sk: str, tenant_id: str) -> None:
    """Flagga uma aparição quando suas anotações de frame divergem de espécie."""
    app_tbl = _appearances_table()
    ann_tbl = _frame_annotations_table()

    ann_resp = ann_tbl.query(
        KeyConditionExpression=(
            Key("tenant_id").eq(tenant_id)
            & Key("appearance_id#frame_idx").begins_with(f"{appearance_id}#")
        )
    )
    species_set = {a["annotated_species"] for a in ann_resp.get("Items", [])}

    if len(species_set) > 1:
        app_tbl.update_item(
            Key={"tenant_id": tenant_id, "video_id#appearance_id": app_sk},
            UpdateExpression="SET review_status = :rs, discrepant_species = :ds, #tr = :tr",
            ExpressionAttributeNames={"#tr": "tenant_id#review_status"},
            ExpressionAttributeValues={
                ":rs": "flagged_discrepancy",
                ":ds": list(species_set),
                ":tr": f"{tenant_id}#flagged_discrepancy",
            },
        )
    else:
        app_tbl.update_item(
            Key={"tenant_id": tenant_id, "video_id#appearance_id": app_sk},
            UpdateExpression="REMOVE discrepant_species SET review_status = :rs, #tr = :tr",
            ExpressionAttributeNames={"#tr": "tenant_id#review_status"},
            ExpressionAttributeValues={
                ":rs": "pending",
                ":tr": f"{tenant_id}#pending",
            },
        )


# ── Endpoint 1 — Upload de vídeo ──────────────────────────────────────────────


@app.post("/projects/{project_id}/videos/upload-url")
def generate_upload_url(
    project_id: str,
    body: UploadUrlRequest,
    tenant_id: str = Depends(get_current_tenant),
):
    """Gera URL pré-assinada S3 para upload direto (sem passar pelo API Gateway).

    Fluxo:
        1. Frontend chama este endpoint → recebe upload_url + video_id
        2. Frontend faz PUT direto ao S3 usando upload_url (sem Authorization header — a URL já está assinada)
        3. Frontend chama POST /projects/{id}/videos/{video_id}/confirm para disparar o pipeline
    """
    video_id = str(uuid.uuid4())
    ext      = os.path.splitext(body.filename)[1].lower() or ".avi"
    s3_key   = f"{tenant_id}/videos/{video_id}{ext}"
    now      = datetime.now(timezone.utc).isoformat()

    # Registro inicial em siab-videos
    _videos_table().put_item(Item={
        "tenant_id":         tenant_id,
        "project_id#video_id": f"{project_id}#{video_id}",
        "project_id":        project_id,
        "video_id":          video_id,
        "s3_key":            s3_key,
        "original_filename": body.filename,
        "status":            "pending_upload",
        "created_at":        now,
    })

    # URL pré-assinada PUT (expira em 1 hora)
    # O frontend DEVE enviar Content-Type igual ao informado aqui
    upload_url = _s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": body.content_type},
        ExpiresIn=3600,
    )

    logger.info("URL gerada | tenant=%s project=%s video_id=%s", tenant_id, project_id, video_id)
    return {"video_id": video_id, "upload_url": upload_url, "s3_key": s3_key}


@app.post("/projects/{project_id}/videos/{video_id}/confirm")
def confirm_upload(
    project_id: str,
    video_id:   str,
    tenant_id:  str = Depends(get_current_tenant),
):
    """Confirma que o upload direto ao S3 foi concluído e dispara o pipeline.

    Atualiza siab-videos para status='uploaded' e publica mensagem SQS para
    o ingester. O OCR (camera_id, captured_at, temperature_c) e a criação de
    câmera acontecem dentro do ingester, de forma assíncrona.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Busca o registro para obter s3_key
    vid_item = _videos_table().get_item(
        Key={"tenant_id": tenant_id, "project_id#video_id": f"{project_id}#{video_id}"}
    ).get("Item")
    if not vid_item:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    s3_key = vid_item["s3_key"]

    # Atualiza status para uploaded
    _videos_table().update_item(
        Key={"tenant_id": tenant_id, "project_id#video_id": f"{project_id}#{video_id}"},
        UpdateExpression="SET #st = :s, uploaded_at = :t",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "uploaded", ":t": now},
    )

    # Dispara pipeline (sem OCR — o ingester extrai esses metadados)
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

    logger.info("Upload confirmado | tenant=%s project=%s video_id=%s", tenant_id, project_id, video_id)
    return {"video_id": video_id, "status": "processing"}


# ── Endpoints 2-4 — Câmeras ───────────────────────────────────────────────────


@app.post("/projects/{project_id}/cameras", status_code=201)
def create_camera(
    project_id: str,
    body: CameraCreate,
    tenant_id: str = Depends(get_current_tenant),
):
    """Cria uma câmera no projeto. 409 se camera_id já existir."""
    tbl  = _cameras_table()
    item = {
        "tenant_id":            tenant_id,
        "project_id#camera_id": f"{project_id}#{body.camera_id}",
        "project_id":           project_id,
        "camera_id":            body.camera_id,
        "created_at":           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if body.name is not None:
        item["name"] = body.name
    if body.latitude is not None:
        item["latitude"] = Decimal(str(body.latitude))
    if body.longitude is not None:
        item["longitude"] = Decimal(str(body.longitude))

    try:
        tbl.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(#sk)",
            ExpressionAttributeNames={"#sk": "project_id#camera_id"},
        )
    except tbl.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPException(
            status_code=409,
            detail=f"Câmera '{body.camera_id}' já existe no projeto '{project_id}'.",
        )

    return _clean(item)


@app.get("/projects/{project_id}/cameras")
def list_cameras(
    project_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    """Lista todas as câmeras do projeto."""
    tbl   = _cameras_table()
    items: list[dict] = []
    kwargs: dict = {
        "KeyConditionExpression": (
            Key("tenant_id").eq(tenant_id)
            & Key("project_id#camera_id").begins_with(f"{project_id}#")
        ),
    }
    while True:
        resp = tbl.query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek

    return {"project_id": project_id, "count": len(items), "items": _clean(items)}


@app.patch("/projects/{project_id}/cameras/{camera_id}")
def update_camera(
    project_id: str,
    camera_id: str,
    body: CameraUpdate,
    tenant_id: str = Depends(get_current_tenant),
):
    """Atualiza name/latitude/longitude de uma câmera existente."""
    tbl = _cameras_table()
    key = {
        "tenant_id":            tenant_id,
        "project_id#camera_id": f"{project_id}#{camera_id}",
    }

    if tbl.get_item(Key=key).get("Item") is None:
        raise HTTPException(status_code=404, detail=f"Câmera '{camera_id}' não encontrada.")

    set_parts, names, values = [], {}, {}
    if body.name is not None:
        set_parts.append("#n = :name")
        names[":name"] = body.name
        names["#n"]    = "name"
    if body.latitude is not None:
        set_parts.append("latitude = :lat")
        values[":lat"] = Decimal(str(body.latitude))
    if body.longitude is not None:
        set_parts.append("longitude = :lon")
        values[":lon"] = Decimal(str(body.longitude))

    if not set_parts:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")

    # Merge names dict (expression attribute names) into values dict — DynamoDB SDK expects them separate
    expr_names  = {k: v for k, v in names.items() if k.startswith("#")}
    expr_values = {k: v for k, v in names.items() if k.startswith(":")}
    expr_values.update(values)

    kwargs: dict = {
        "Key":              key,
        "UpdateExpression": "SET " + ", ".join(set_parts),
        "ExpressionAttributeValues": expr_values,
        "ReturnValues": "ALL_NEW",
    }
    if expr_names:
        kwargs["ExpressionAttributeNames"] = expr_names

    resp = tbl.update_item(**kwargs)
    return _clean(resp.get("Attributes", {}))


# ── Endpoint 5 — Listar aparições ─────────────────────────────────────────────


@app.get("/projects/{project_id}/appearances")
def list_appearances(
    project_id: str,
    camera_id:     str | None = Query(default=None),
    species:       str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit:         int        = Query(default=100, ge=1, le=1000),
    tenant_id:     str        = Depends(get_current_tenant),
):
    """Lista aparições do projeto, ordenadas por ts_start. Filtros opcionais."""
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

    def _enrich(a: dict) -> dict:
        cleaned = _clean(a)
        cleaned["thumbnail_url"] = _presigned_url(a.get("best_crop_s3_key"))
        return cleaned

    return {
        "project_id": project_id,
        "count":      len(items),
        "items":      [_enrich(a) for a in items],
    }


# ── Endpoint 3 — Revisão humana ───────────────────────────────────────────────


@app.patch("/appearances/{appearance_id}/review")
def review_appearance(
    appearance_id: str,
    body: ReviewRequest,
    tenant_id:   str = Depends(get_current_tenant),
    reviewer_id: str = Depends(get_current_sub),
):
    """Grava revisão e atualiza review_status + reviewer_id da aparição."""
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

    # Grava revisão em siab-reviews (com reviewer_id para rastreabilidade)
    review_record: dict = {
        "tenant_id":                tenant_id,
        "appearance_id#reviewed_at": f"{appearance_id}#{reviewed_at}",
        "appearance_id":            appearance_id,
        "project_id":               project_id,
        "action":                   body.action,
        "reviewed_at":              reviewed_at,
        "reviewer_id":              reviewer_id,
    }
    if body.corrected_species:
        review_record["corrected_species"] = body.corrected_species
    rev_tbl.put_item(Item=review_record)

    # Atualiza siab-appearances (inclui reviewer_id para auditoria inline)
    update_expr  = "SET review_status = :rs, #tr = :tr, reviewer_id = :rv"
    expr_names   = {"#tr": "tenant_id#review_status"}
    expr_vals: dict = {
        ":rs": new_status,
        ":tr": f"{tenant_id}#{new_status}",
        ":rv": reviewer_id,
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


# ── Endpoint 4 — Anotação de frame ────────────────────────────────────────────


@app.patch("/frames/annotation")
def annotate_frame(
    body: AnnotationRequest,
    tenant_id: str = Depends(get_current_tenant),
):
    """Persiste anotação de espécie por frame e verifica discrepâncias nas aparições."""
    frame_idx    = _frame_idx_from_path(body.frame_path)
    frame_s3_key = f"{tenant_id}/frames/{body.frame_path}"
    annotated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    ann_tbl = _frame_annotations_table()

    matched = _appearances_for_frame(body.video_id, frame_idx, tenant_id)
    if not matched:
        return {"status": "no_appearance", "frame_idx": frame_idx}

    for app_item in matched:
        appearance_id = app_item.get("appearance_id", "")
        app_sk        = app_item["video_id#appearance_id"]
        ann_tbl.put_item(Item={
            "tenant_id":              tenant_id,
            "appearance_id#frame_idx": f"{appearance_id}#{frame_idx:05d}",
            "appearance_id":          appearance_id,
            "frame_path":             body.frame_path,
            "frame_s3_key":           frame_s3_key,
            "frame_idx":              frame_idx,
            "annotated_species":      body.annotated_species,
            "annotation_source":      body.annotation_source,
            "annotated_at":           annotated_at,
        })
        _check_discrepancy(appearance_id, app_sk, tenant_id)

    return {"status": "ok", "frame_idx": frame_idx, "appearances_updated": len(matched)}


# ── Endpoint 5 — Anotações de frame por aparição ─────────────────────────────


@app.get("/appearances/{appearance_id}/frame-annotations")
def get_frame_annotations(
    appearance_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    """Retorna as anotações de frame de uma aparição, ordenadas por frame_idx."""
    app_tbl   = _appearances_table()
    ann_tbl   = _frame_annotations_table()
    app_item  = _find_appearance(app_tbl, tenant_id, appearance_id)
    if not app_item:
        raise HTTPException(status_code=404, detail="Aparição não encontrada")
    f_start = int(app_item.get("frame_start", 0))
    f_end   = int(app_item.get("frame_end", f_start))

    ann_resp = ann_tbl.query(
        KeyConditionExpression=(
            Key("tenant_id").eq(tenant_id)
            & Key("appearance_id#frame_idx").begins_with(f"{appearance_id}#")
        )
    )
    items = sorted(ann_resp.get("Items", []), key=lambda x: int(x.get("frame_idx", 0)))
    result = [
        {**_clean(it), "thumbnail_url": _presigned_url(it.get("frame_s3_key"))}
        for it in items
    ]
    return {
        "appearance_id": appearance_id,
        "frame_start":   f_start,
        "frame_end":     f_end,
        "count":         len(result),
        "items":         result,
    }


# ── Endpoint 6 — Dashboard stats ─────────────────────────────────────────────


@app.get("/projects/{project_id}/stats")
def get_project_stats(
    project_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    """Agrega aparições confirmadas de um projeto para o dashboard."""
    from collections import defaultdict

    table     = _appearances_table()
    pk        = f"{tenant_id}#confirmed"
    sk_prefix = f"{project_id}#"

    items: list[dict] = []
    kwargs: dict = {
        "IndexName": "by-review-status",
        "KeyConditionExpression": (
            Key("tenant_id#review_status").eq(pk)
            & Key("project_id#appearance_id").begins_with(sk_prefix)
        ),
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek

    if not items:
        return {
            "total_confirmed": 0,
            "distinct_species": 0,
            "active_cameras": 0,
            "period_start": None,
            "period_end": None,
            "by_fauna_group_and_month": [],
            "by_camera": [],
            "species_richness": [],
        }

    distinct_species = len({a.get("species") for a in items if a.get("species")})
    active_cameras   = len({a.get("camera_id") for a in items if a.get("camera_id")})

    ts_starts = sorted(a["ts_start"] for a in items if a.get("ts_start"))
    ts_ends   = sorted(a["ts_end"]   for a in items if a.get("ts_end"))
    period_start = ts_starts[0][:10]  if ts_starts else None
    period_end   = ts_ends[-1][:10]   if ts_ends   else (ts_starts[-1][:10] if ts_starts else None)

    # ── Fauna × mês ───────────────────────────────────────────────────────────
    month_groups: dict[str, dict[str, int]] = defaultdict(
        lambda: {"mastofauna": 0, "avifauna": 0, "herpetofauna": 0}
    )
    for a in items:
        month = (a.get("ts_start") or "")[:7]
        if not month:
            continue
        grp = _fauna_group_dash(a.get("taxonomic_path"), a.get("species"))
        if grp in ("mastofauna", "avifauna", "herpetofauna"):
            month_groups[month][grp] += 1

    by_fauna_group_and_month = [
        {"month": m, **v}
        for m, v in sorted(month_groups.items())
    ]

    # ── Por câmera ────────────────────────────────────────────────────────────
    cam_totals:  dict[str, int]            = defaultdict(int)
    cam_species: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in items:
        cam = a.get("camera_id") or "Desconhecida"
        sp  = a.get("species") or ""
        cam_totals[cam] += 1
        if sp:
            cam_species[cam][sp] += 1

    by_camera = [
        {
            "camera_id":   cam,
            "total":       cam_totals[cam],
            "top_species": sorted(cam_species[cam], key=lambda s: -cam_species[cam][s])[:3],
        }
        for cam in sorted(cam_totals, key=lambda c: -cam_totals[c])
    ]

    # ── Riqueza de espécies ───────────────────────────────────────────────────
    sp_data: dict[str, dict] = {}
    for a in items:
        sp = a.get("species") or ""
        if not sp:
            continue
        if sp not in sp_data:
            sp_data[sp] = {
                "species": sp,
                "group":   _fauna_group_dash(a.get("taxonomic_path"), sp),
                "count":   0,
            }
        sp_data[sp]["count"] += 1

    species_richness = sorted(sp_data.values(), key=lambda x: -x["count"])

    return {
        "total_confirmed":          len(items),
        "distinct_species":         distinct_species,
        "active_cameras":           active_cameras,
        "period_start":             period_start,
        "period_end":               period_end,
        "by_fauna_group_and_month": by_fauna_group_and_month,
        "by_camera":                by_camera,
        "species_richness":         species_richness,
    }


# ── Endpoint 7 — Export CSV ───────────────────────────────────────────────────


@app.get("/projects/{project_id}/appearances/export")
def export_appearances(
    project_id: str,
    tenant_id: str = Depends(get_current_tenant),
):
    """Exporta aparições confirmadas em CSV (formato do formulário manual)."""
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


# ── Task A — Frame carousel endpoint ─────────────────────────────────────────


@app.get("/projects/{project_id}/appearances/{appearance_id}/frames")
def list_appearance_frames(
    project_id:    str,
    appearance_id: str,
    tenant_id:     str = Depends(get_current_tenant),
):
    """Retorna URLs presigned para todos os frames de uma aparição (frame_start..frame_end)."""
    item = _find_appearance(_appearances_table(), tenant_id, appearance_id)
    if not item:
        raise HTTPException(status_code=404, detail="Aparição não encontrada")

    video_id    = item.get("video_id", "")
    frame_start = int(item.get("frame_start", 0))
    frame_end   = int(item.get("frame_end",   frame_start))
    best_key    = item.get("best_crop_s3_key", "")
    best_idx    = _frame_idx_from_path(best_key) if best_key else frame_start
    bbox        = _clean(item.get("bbox")) if item.get("bbox") else None

    frames = [
        {
            "frame_idx": idx,
            "url":       _presigned_url(f"{tenant_id}/frames/{video_id}/frame_{idx:05d}.jpg"),
            "is_best":   idx == best_idx,
            "bbox":      bbox if idx == best_idx else None,
        }
        for idx in range(frame_start, frame_end + 1)
    ]

    return {
        "appearance_id": appearance_id,
        "frame_count":   len(frames),
        "frames":        frames,
    }


# ── Task B — Vídeos list + delete ────────────────────────────────────────────


@app.get("/projects/{project_id}/videos")
def list_videos(
    project_id: str,
    tenant_id:  str = Depends(get_current_tenant),
):
    """Lista vídeos do projecto com status de display calculado a partir das aparições."""
    vid_tbl = _videos_table()

    vids: list[dict] = []
    kwargs: dict = {
        "KeyConditionExpression": (
            Key("tenant_id").eq(tenant_id)
            & Key("project_id#video_id").begins_with(f"{project_id}#")
        ),
    }
    while True:
        resp = vid_tbl.query(**kwargs)
        vids.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek

    # Busca todas as aparições do projecto de uma vez (evita N+1)
    appearances = _appearances_from_project(_appearances_table(), tenant_id, project_id)
    by_video: dict[str, list[dict]] = {}
    for a in appearances:
        by_video.setdefault(a.get("video_id", ""), []).append(a)

    def _display_status(vid_status: str, apps: list[dict]) -> str:
        if not apps:
            return "Processando"
        if all(a.get("review_status") in ("confirmed", "rejected") for a in apps):
            return "Revisado"
        return "Aguardando revisão"

    result = []
    for v in sorted(vids, key=lambda x: x.get("captured_at") or x.get("uploaded_at") or ""):
        vid_id = v.get("video_id", "")
        apps   = by_video.get(vid_id, [])
        result.append(_clean({
            "video_id":          vid_id,
            "original_filename": v.get("original_filename"),
            "camera_id":         v.get("camera_id"),
            "captured_at":       v.get("captured_at"),
            "uploaded_at":       v.get("uploaded_at"),
            "status":            v.get("status"),
            "display_status":    _display_status(str(v.get("status", "")), apps),
            "species":           sorted({a.get("species") for a in apps if a.get("species")}),
            "appearance_count":  len(apps),
        }))

    return {"project_id": project_id, "count": len(result), "videos": result}


@app.delete("/projects/{project_id}/videos/{video_id}", status_code=204)
def delete_video(
    project_id: str,
    video_id:   str,
    tenant_id:  str = Depends(get_current_tenant),
):
    """Remove vídeo: apaga S3 frames + ficheiro + aparições + registo DynamoDB."""
    vid_tbl = _videos_table()
    app_tbl = _appearances_table()

    vid_item = vid_tbl.get_item(
        Key={"tenant_id": tenant_id, "project_id#video_id": f"{project_id}#{video_id}"}
    ).get("Item")
    if not vid_item:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    s3 = _s3_client()

    # Apaga frames no S3
    prefix = f"{tenant_id}/frames/{video_id}/"
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        objs = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": objs})

    # Apaga ficheiro de vídeo
    s3_key = vid_item.get("s3_key")
    if s3_key:
        try:
            s3.delete_object(Bucket=BUCKET, Key=s3_key)
        except Exception:
            pass

    # Apaga aparições associadas
    apps = app_tbl.query(
        KeyConditionExpression=(
            Key("tenant_id").eq(tenant_id)
            & Key("video_id#appearance_id").begins_with(f"{video_id}#")
        )
    ).get("Items", [])
    for a in apps:
        app_tbl.delete_item(
            Key={"tenant_id": tenant_id, "video_id#appearance_id": a["video_id#appearance_id"]}
        )

    # Apaga registo do vídeo
    vid_tbl.delete_item(
        Key={"tenant_id": tenant_id, "project_id#video_id": f"{project_id}#{video_id}"}
    )

    return Response(status_code=204)
