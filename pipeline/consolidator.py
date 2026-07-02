"""
pipeline/consolidator.py — Consolida aparições entre vídeos consecutivos da mesma câmera.

Para cada (camera_id, species), ordena as aparições por ts_start e mescla pares
cujo gap (ts_end[i] → ts_start[i+1]) seja ≤ gap_seconds.

A aparição sobrevivente mantém o appearance_id/video_id da mais antiga.
A redundante é deletada do DynamoDB.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

APPEARANCES_TABLE  = os.environ.get("APPEARANCES_TABLE", "siab-appearances")
DEFAULT_GAP_SECONDS = 300.0


@dataclass
class ConsolidationResult:
    """Resultado da operação de consolidação de aparições.

    Attributes:
        merged:             Número de pares consolidados.
        deleted:            Aparições removidas (uma por par consolidado).
        appearances_before: Total de aparições antes da consolidação.
        appearances_after:  Total de aparições após a consolidação.
    """

    merged: int
    deleted: int
    appearances_before: int
    appearances_after: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_ts(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).strip().replace("Z", ""))
    except ValueError:
        return None


def _gap_seconds(ts_end, ts_start) -> float | None:
    """Retorna o gap em segundos entre ts_end de uma aparição e ts_start da próxima."""
    t1 = _parse_ts(ts_end)
    t2 = _parse_ts(ts_start)
    if t1 is None or t2 is None:
        return None
    return (t2 - t1).total_seconds()


def _score(app: dict) -> float:
    return float(app.get("species_score", 0))


def _merge(survivor: dict, victim: dict) -> dict:
    """Retorna cópia de survivor com campos atualizados pela mesclagem com victim.

    Regras:
        ts_start        = survivor (mais antigo)
        ts_end          = victim (mais recente)
        support_frames  = soma
        best_crop_s3_key = frame com maior species_score
        individual_count = máximo
    """
    merged = dict(survivor)
    merged["ts_end"] = victim["ts_end"]
    merged["support_frames"] = (
        int(survivor.get("support_frames", 1)) + int(victim.get("support_frames", 1))
    )
    merged["individual_count"] = max(
        int(survivor.get("individual_count", 1)),
        int(victim.get("individual_count", 1)),
    )
    if _score(victim) > _score(survivor):
        merged["best_crop_s3_key"] = victim["best_crop_s3_key"]
        merged["species_score"] = Decimal(str(round(float(victim["species_score"]), 4)))
        if victim.get("bbox"):
            merged["bbox"] = victim["bbox"]
    return merged


# ── DynamoDB ──────────────────────────────────────────────────────────────────


def _query_all_appearances(table, tenant_id: str, project_id: str) -> list[dict]:
    """Busca todas as aparições do projeto via GSI-1 (by-species), com paginação."""
    pk_val = f"{tenant_id}#{project_id}"
    items: list[dict] = []
    kwargs: dict = {
        "IndexName": "by-species",
        "KeyConditionExpression": Key("tenant_id#project_id").eq(pk_val),
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items


def _update_survivor(table, survivor: dict) -> None:
    """Persiste os campos mesclados na aparição sobrevivente."""
    table.update_item(
        Key={
            "tenant_id":              survivor["tenant_id"],
            "video_id#appearance_id": survivor["video_id#appearance_id"],
        },
        UpdateExpression=(
            "SET ts_end = :te, support_frames = :sf, "
            "best_crop_s3_key = :bc, individual_count = :ic, "
            "species_score = :ss"
        ),
        ExpressionAttributeValues={
            ":te": survivor["ts_end"],
            ":sf": int(survivor["support_frames"]),
            ":bc": survivor["best_crop_s3_key"],
            ":ic": int(survivor["individual_count"]),
            ":ss": Decimal(str(round(float(survivor["species_score"]), 4))),
        },
    )


def _delete_appearance(table, tenant_id: str, sk: str) -> None:
    """Remove uma aparição redundante da tabela."""
    table.delete_item(
        Key={
            "tenant_id":              tenant_id,
            "video_id#appearance_id": sk,
        }
    )


# ── Função principal ──────────────────────────────────────────────────────────


def consolidate_project_appearances(
    tenant_id: str,
    project_id: str,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
    table=None,
) -> ConsolidationResult:
    """Consolida aparições entre vídeos consecutivos da mesma câmera.

    Fluxo:
        1. Busca todas as aparições do projeto (GSI-1).
        2. Filtra as que têm ts_start, ts_end e camera_id preenchidos.
        3. Agrupa por (camera_id, species).
        4. Em cada grupo, ordena por ts_start e mescla pares consecutivos
           cujo gap ≤ gap_seconds.

    Args:
        tenant_id:   Identificador do tenant.
        project_id:  Identificador do projeto.
        gap_seconds: Gap máximo (em segundos) para consolidar dois pares.
        table:       Tabela DynamoDB (injeção para testes; usa env se None).

    Returns:
        ConsolidationResult com contadores da operação.
    """
    if table is None:
        ddb   = boto3.resource("dynamodb")
        table = ddb.Table(APPEARANCES_TABLE)

    all_items          = _query_all_appearances(table, tenant_id, project_id)
    appearances_before = len(all_items)

    eligible = [
        a for a in all_items
        if a.get("ts_start") and a.get("ts_end") and a.get("camera_id")
    ]

    groups: dict[tuple, list[dict]] = {}
    for app in eligible:
        key = (str(app["camera_id"]), str(app["species"]))
        groups.setdefault(key, []).append(app)

    merged_count  = 0
    deleted_count = 0

    for group in groups.values():
        group.sort(key=lambda a: _parse_ts(a["ts_start"]) or datetime.min)

        i = 0
        while i < len(group) - 1:
            curr = group[i]
            nxt  = group[i + 1]
            gap  = _gap_seconds(curr["ts_end"], nxt["ts_start"])

            if gap is not None and 0 <= gap <= gap_seconds:
                merged = _merge(curr, nxt)
                _update_survivor(table, merged)
                _delete_appearance(table, tenant_id, nxt["video_id#appearance_id"])
                group[i] = merged
                group.pop(i + 1)
                merged_count  += 1
                deleted_count += 1
            else:
                i += 1

    logger.info(
        "consolidate | tenant=%s project=%s before=%d merged=%d deleted=%d after=%d",
        tenant_id, project_id, appearances_before, merged_count, deleted_count,
        appearances_before - deleted_count,
    )

    return ConsolidationResult(
        merged=merged_count,
        deleted=deleted_count,
        appearances_before=appearances_before,
        appearances_after=appearances_before - deleted_count,
    )
