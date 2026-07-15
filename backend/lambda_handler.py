import logging

from mangum import Mangum
from backend.api import app

# Sem isso, logger.info(...) em backend/api.py fica silenciado (nível padrão
# é WARNING) — mesmo bug já corrigido no ingester/megadetector/speciesnet.
logging.getLogger().setLevel(logging.INFO)

handler = Mangum(app, lifespan="off")
