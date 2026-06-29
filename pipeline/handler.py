"""
pipeline/handler.py — Dispatcher genérico para Lambda.

Uma única imagem Docker serve MegaDetector e SpeciesNet.
A variável de ambiente STAGE define qual estágio executar.
"""

import importlib
import logging
import os

logger = logging.getLogger(__name__)


def handler(event, context):
    """Entry point Lambda: roteia para o módulo correto via STAGE env var."""
    stage = os.environ.get("STAGE", "megadetector").lower()
    module_name = f"pipeline.{stage}_handler"

    logger.info("Iniciando estágio: %s", stage)
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise ValueError(
            f"STAGE inválido: '{stage}'. "
            f"Valores aceitos: megadetector, speciesnet"
        )

    return mod.lambda_handler(event, context)
