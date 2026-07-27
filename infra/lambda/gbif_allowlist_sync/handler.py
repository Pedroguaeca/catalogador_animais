"""
Lambda handler — sync mensal da allowlist geográfica GBIF.

Invocado pelo EventBridge Schedule uma vez por mês. Entrega (b) do geofencing
(SIAB-187): escaneia siab-frame-annotations pelas espécies que o SIAB já
classificou de verdade e consulta o GBIF (occurrence/search, country=BR) só
pras que ainda não estão no cache (models/gbif/br_allowlist.json no S3).
"""
import logging

from gbif_allowlist_sync import sync_allowlist

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    result = sync_allowlist()
    logger.info(
        "gbif_allowlist_sync | classificadas=%d novas=%d atualizadas=%d falhas=%d",
        result.checked, result.new, result.updated, result.failed,
    )
    return {
        "checked": result.checked,
        "new":     result.new,
        "updated": result.updated,
        "failed":  result.failed,
    }
