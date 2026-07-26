#!/usr/bin/env python3
"""
scripts/seed_species_catalog.py — Semeia siab-species com as categorias que
hoje estavam hardcoded em frontend/src/lib/reducer.ts (DEFAULT_CATEGORIES),
marcadas status=official.

Passo único de migração — depois disso, o catálogo vive só no banco (GET
/species, POST /species, fila de aprovação). Idempotente: já existente não
é sobrescrito.
"""

import os
import sys
from datetime import datetime, timezone

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.api import _slugify_species_name  # noqa: E402

SPECIES_TABLE = os.environ.get("SPECIES_TABLE", "siab-species")
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# Mesma lista que estava em DEFAULT_CATEGORIES (reducer.ts) antes da migração.
SEED_NAMES = [
    "Aramides", "Crypturellus", "Cutia", "Dasyprocta", "Irara", "Macuco",
    "Cateto", "Teiú", "Tinamus", "Paca", "Quati", "Anta",
]


def main() -> None:
    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(SPECIES_TABLE)
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    created, skipped = 0, 0
    for name in SEED_NAMES:
        species_id = _slugify_species_name(name)
        existing = table.get_item(Key={"species_id": species_id}).get("Item")
        if existing:
            print(f"  já existe: {species_id} (status={existing.get('status')}) — pulando")
            skipped += 1
            continue
        table.put_item(Item={
            "species_id":           species_id,
            "name":                 name,
            "status":               "official",
            "created_by":           "seed-script",
            "created_by_tenant_id": "global",
            "created_at":           now,
            "reviewed_by":          "seed-script",
            "reviewed_at":          now,
        })
        print(f"  criado: {species_id} ({name})")
        created += 1

    print(f"\nConcluído: {created} criados, {skipped} já existiam.")


if __name__ == "__main__":
    main()
