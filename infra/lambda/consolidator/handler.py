"""
Lambda handler — consolidação cross-vídeo de aparições.

Invocado pelo EventBridge Schedule a cada 15 minutos.
Descobre projetos activos varrendo siab-appearances (projeção mínima) e chama
consolidate_project_appearances() para cada (tenant_id, project_id) encontrado.

Decisão de design (ver ADR no código de infra):
    A siab-projects está vazia no piloto — o pipeline não escreve nela.
    Em vez de introduzir uma dependência nova, varremos siab-appearances com
    ProjectionExpression="tenant_id#project_id" para descobrir pares activos.
    Custo aceitável até ~50k aparições; escala vertical óbvia depois disso.
"""
import logging
import os

import boto3

from consolidator import consolidate_project_appearances

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

APPEARANCES_TABLE = os.environ.get("APPEARANCES_TABLE", "siab-appearances")
GAP_SECONDS       = float(os.environ.get("GAP_SECONDS", "300"))


def _discover_projects(table) -> list[tuple[str, str]]:
    """Varre siab-appearances (projeção mínima) → pares (tenant_id, project_id) únicos."""
    pairs: set[tuple[str, str]] = set()
    kwargs: dict = {
        "ProjectionExpression":     "#tp",
        "ExpressionAttributeNames": {"#tp": "tenant_id#project_id"},
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            composite = item.get("tenant_id#project_id", "")
            if "#" in composite:
                tenant_id, project_id = composite.split("#", 1)
                pairs.add((tenant_id, project_id))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return sorted(pairs)


def lambda_handler(event, context):
    ddb   = boto3.resource("dynamodb")
    table = ddb.Table(APPEARANCES_TABLE)

    projects = _discover_projects(table)
    logger.info("Discovered %d project(s): %s", len(projects), projects)

    if not projects:
        return {"consolidated": 0, "projects": []}

    results = []
    for tenant_id, project_id in projects:
        result = consolidate_project_appearances(
            tenant_id=tenant_id,
            project_id=project_id,
            gap_seconds=GAP_SECONDS,
            table=table,
        )
        logger.info(
            "consolidated | tenant=%s project=%s before=%d merged=%d deleted=%d after=%d",
            tenant_id, project_id,
            result.appearances_before, result.merged, result.deleted, result.appearances_after,
        )
        results.append({
            "tenant_id":          tenant_id,
            "project_id":         project_id,
            "merged":             result.merged,
            "deleted":            result.deleted,
            "discrepancies":      result.discrepancies,
            "appearances_before": result.appearances_before,
            "appearances_after":  result.appearances_after,
        })

    return {"consolidated": len(results), "projects": results}
