"""
pipeline/gbif_allowlist_sync.py — Sync periódico da allowlist geográfica GBIF.

Entrega (b) do geofencing (SIAB-187): o geofencing embutido do SpeciesNet
(country="BRA") resolve a maioria dos casos, mas comprovadamente não todos
(ex: Penelope purpurascens, marcada como permitida no Brasil no próprio
geofence_release.20260609.json do Google). Essa camada usa ocorrência real
no GBIF como segunda fonte, pra SINALIZAR pra revisão humana — nunca pra
bloquear ou trocar a espécie automaticamente (risco de falso negativo se a
allowlist do GBIF tiver buraco de amostragem).

Escopo (decisão 27/07, Opção B): em vez de iterar as 2064 espécies da
taxonomia global do SpeciesNet (não cabe em 15 min de Lambda — medido:
~1s/request sequencial via GBIF), o sync escaneia siab-frame-annotations
pelas espécies que o SIAB já classificou de verdade (~25 hoje) e só
consulta o GBIF pras que ainda não estão no cache. Cresce organicamente.
Espécie nunca sincronizada = tratada como "precisa revisão" por quem
consome o cache (default seguro, não uma lacuna silenciosa).

Fluxo:
    siab-frame-annotations (scan) → espécies novas → GBIF occurrence/search
    → merge no cache existente → grava br_allowlist.json no S3
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

BUCKET_NAME             = os.environ.get("SIAB_BUCKET",             "siab-media-dev")
FRAME_ANNOTATIONS_TABLE = os.environ.get("FRAME_ANNOTATIONS_TABLE", "siab-frame-annotations")
ALLOWLIST_S3_KEY        = os.environ.get("GBIF_ALLOWLIST_S3_KEY",   "models/gbif/br_allowlist.json")

GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"
GBIF_TIMEOUT_SECONDS = 10


@dataclass
class SyncResult:
    """Resultado de uma rodada de sync da allowlist GBIF.

    Attributes:
        checked:    Espécies já classificadas em siab-frame-annotations.
        new:        Espécies que ainda não estavam no cache (candidatas a consulta).
        updated:    Espécies consultadas com sucesso e gravadas/atualizadas no cache.
        failed:     Espécies com falha de rede/parsing na consulta ao GBIF (ficam
                    ausentes do cache — consumidor trata ausência como "precisa revisão").
    """

    checked: int
    new: int
    updated: int
    failed: int


# ── Descoberta de espécies reais do SIAB ─────────────────────────────────────


def _discover_classified_species(table) -> set[str]:
    """Varre siab-frame-annotations (projeção mínima) e retorna o conjunto de
    espécies (nível "species", nome científico em minúsculas) já classificadas
    pelo pipeline. Ignora rollups taxonômicos (aves/mammalia/didelphidae/...) —
    geo_review_flag só se aplica a classificações no nível espécie.

    Tabela não tem GSI por ai_species — scan completo, mesmo padrão já usado em
    _discover_projects() (infra/lambda/consolidator/handler.py) pra essa mesma
    limitação noutra tabela.
    """
    species: set[str] = set()
    kwargs: dict = {
        "ProjectionExpression": "ai_species, taxonomic_level",
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            if item.get("taxonomic_level") != "species":
                continue
            name = (item.get("ai_species") or "").strip().lower()
            if name:
                species.add(name)
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return species


# ── Cache no S3 ───────────────────────────────────────────────────────────────


def _load_existing_allowlist(s3_client, bucket: str, key: str) -> dict:
    """Baixa e faz parse do cache atual. Retorna {} se ainda não existir
    (primeiro sync) ou se o objeto estiver corrompido (não interrompe o sync)."""
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read())
    except s3_client.exceptions.NoSuchKey:
        return {}
    except Exception as exc:
        logger.warning("Cache GBIF existente ilegível (%s) — tratando como vazio.", exc)
        return {}


def _save_allowlist(s3_client, bucket: str, key: str, allowlist: dict) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(allowlist, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


# ── Consulta ao GBIF ──────────────────────────────────────────────────────────


def _query_gbif_occurrence_br(species: str) -> int | None:
    """Consulta quantos registros de ocorrência no Brasil o GBIF tem pra essa
    espécie. limit=0 — só precisamos do campo "count" da resposta, não dos
    registros em si.

    Retorna None em caso de falha de rede/parsing (o chamador decide o que
    fazer — aqui, não gravar entrada, deixando a espécie "sem cache" até o
    próximo sync tentar de novo).
    """
    params = urllib.parse.urlencode({
        "scientificName": species,
        "country":        "BR",
        "limit":          0,
    })
    url = f"{GBIF_OCCURRENCE_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=GBIF_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        return int(data.get("count", 0))
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.warning("Falha ao consultar GBIF para '%s': %s", species, exc)
        return None


# ── Entrypoint ────────────────────────────────────────────────────────────────


def sync_allowlist(
    ddb_resource=None,
    s3_client=None,
    bucket: str | None = None,
    table_name: str | None = None,
    s3_key: str | None = None,
) -> SyncResult:
    """Sincroniza a allowlist geográfica GBIF contra as espécies que o SIAB já
    classificou. Só consulta o GBIF pras espécies novas desde o último sync —
    entradas existentes não são re-consultadas (ocorrência geográfica de uma
    espécie não muda de mês pra mês)."""
    ddb = ddb_resource or boto3.resource("dynamodb")
    s3  = s3_client or boto3.client("s3")
    bucket = bucket or BUCKET_NAME
    table_name = table_name or FRAME_ANNOTATIONS_TABLE
    s3_key = s3_key or ALLOWLIST_S3_KEY

    table = ddb.Table(table_name)
    classified = _discover_classified_species(table)
    allowlist  = _load_existing_allowlist(s3, bucket, s3_key)

    new_species = sorted(classified - allowlist.keys())
    logger.info(
        "GBIF allowlist sync | classificadas=%d já_no_cache=%d novas=%d",
        len(classified), len(classified) - len(new_species), len(new_species),
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = 0
    failed  = 0
    for species in new_species:
        count = _query_gbif_occurrence_br(species)
        if count is None:
            failed += 1
            continue
        allowlist[species] = {
            "ocorre_br":        count > 0,
            "n_registros_gbif": count,
            "synced_at":        now,
        }
        updated += 1

    if updated:
        _save_allowlist(s3, bucket, s3_key, allowlist)

    return SyncResult(
        checked=len(classified),
        new=len(new_species),
        updated=updated,
        failed=failed,
    )
