#!/usr/bin/env python3
"""
scripts/migrate_species_taxonomy.py — Fase 1 da reestruturação de taxonomia
(SIAB-taxonomy): migra siab-species (13 itens em texto livre) para
siab-taxon + siab-taxon-name, ligados pelo taxonKey do GBIF.

NÃO apaga siab-species. NÃO muda o que o app consulta (isso é Fase 2) — só
popula as tabelas novas, lidas depois por scripts/relatórios futuros.

Metodologia (e por que ela diverge da instrução original em 1 ponto):

  1. species/match (nome + kingdom=Animalia) — é o endpoint certo pra nome
     CIENTÍFICO (tolera erro de digitação dentro da nomenclatura Latina),
     mas NÃO foi desenhado pra nome popular.
  2. Descoberta ao testar os 13 nomes reais: "Quati" bate como matchType
     FUZZY + status ACCEPTED contra "Quasi" (um gênero de mosca sul-
     -americana, Diptera/Acroceridae) — um match tecnicamente "aceito" pela
     regra literal da task, mas taxonomicamente absurdo. "Paca" e "Teiú"
     batem em HIGHERRANK genérico (Chordata/Animalia), inúteis.
  3. Rede de segurança adicionada: todo matchType FUZZY é cruzado contra
     species/search (que resolve nome popular corretamente — testado com
     "onça-pintada"→Panthera onca, "Quati"→Nasua). Se o gênero/família do
     species/search não bater com o do species/match, o item cai pra
     NEEDS_REVIEW em vez de aceitar o FUZZY cegamente. Só EXACT (sempre) e
     FUZZY-confirmado-por-search são aceitos automaticamente.

Uso:
    python scripts/migrate_species_taxonomy.py            # roda de verdade
    python scripts/migrate_species_taxonomy.py --dry-run   # só mostra o que faria
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

REGION           = "us-east-1"
SPECIES_TABLE    = "siab-species"
TAXON_TABLE      = "siab-taxon"
TAXON_NAME_TABLE = "siab-taxon-name"

GBIF_MATCH_URL       = "https://api.gbif.org/v1/species/match"
GBIF_SEARCH_URL      = "https://api.gbif.org/v1/species/search"
GBIF_VERNACULAR_URL  = "https://api.gbif.org/v1/species/{}/vernacularNames"
GBIF_TIMEOUT         = 10
GBIF_REQUEST_DELAY_S = 0.3  # gentileza — não é rate limit documentado, só não martelar

TAXONOMY_S3_BUCKET = "siab-media-dev"
TAXONOMY_S3_KEY     = "models/speciesnet/v4.0.3a/taxonomy_release.20260609.txt"
BACKBONE_VERSION    = "GBIF Backbone Taxonomy"  # espécie/match não devolve nº de versão explícito


def _http_get_json(url: str, retries: int = 2) -> dict:
    """GBIF ocasionalmente dá timeout de handshake TLS sob rede instável —
    retry simples evita contar isso como ambiguidade taxonômica real no
    relatório final."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=GBIF_TIMEOUT) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def gbif_match(name: str) -> dict:
    params = urllib.parse.urlencode({"name": name, "kingdom": "Animalia"})
    return _http_get_json(f"{GBIF_MATCH_URL}?{params}")


def gbif_search_top(name: str) -> dict | None:
    params = urllib.parse.urlencode({"q": name, "limit": 5})
    data = _http_get_json(f"{GBIF_SEARCH_URL}?{params}")
    results = data.get("results", [])
    return results[0] if results else None


def gbif_vernacular_names_pt(taxon_key: int) -> list[str]:
    url = GBIF_VERNACULAR_URL.format(taxon_key) + "?limit=1000"
    data = _http_get_json(url)
    return [
        r["vernacularName"] for r in data.get("results", [])
        if r.get("language") == "por" and r.get("vernacularName")
    ]


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip().lower()


def _slugify(s: str) -> str:
    s = _normalize(s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s


def _name_id(taxon_key: int, source: str, name: str) -> str:
    """slugify() normaliza acento pra virar legível (bom pra debug), mas
    ISSO SOZINHO colide — "Onça" e "Onca" são vernacularNames DISTINTOS
    devolvidos pelo GBIF pro mesmo taxon_key, e ambos slugificam pra "onca".
    Achado rodando a migração de verdade: 8 nomes novos esperados, só 7
    sobreviveram (um put_item silenciosamente sobrescreveu o outro). Hash
    curto do nome ORIGINAL (não normalizado) garante unicidade sem perder
    legibilidade."""
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{taxon_key}#{source}#{_slugify(name)}-{h}"


def classify_name_type(original: str, canonical_name: str | None) -> str:
    """SCIENTIFIC se a string original bate (normalizada) com o canonicalName
    devolvido pelo GBIF; senão VERNACULAR."""
    if canonical_name and _normalize(original) == _normalize(canonical_name):
        return "SCIENTIFIC"
    return "VERNACULAR"


def resolve_taxon_key(match: dict) -> int | None:
    """usageKey se ACCEPTED; acceptedUsageKey se SYNONYM; None nos demais casos
    (DOUBTFUL etc. — cai pra NEEDS_REVIEW no chamador)."""
    status = match.get("status")
    if status == "ACCEPTED":
        return match.get("usageKey")
    if status == "SYNONYM":
        return match.get("acceptedUsageKey")
    return None


def fuzzy_match_confirmed_by_search(original: str, match: dict) -> bool:
    """Rede de segurança contra FUZZY absurdo (ver docstring do módulo) — só
    aceita o FUZZY do species/match se o top result do species/search
    concordar em gênero OU família."""
    top = gbif_search_top(original)
    time.sleep(GBIF_REQUEST_DELAY_S)
    if not top:
        return False
    match_genus  = (match.get("genus") or "").lower()
    match_family = (match.get("family") or "").lower()
    top_genus    = (top.get("genus") or "").lower()
    top_family   = (top.get("family") or "").lower()
    return bool(
        (match_genus and match_genus == top_genus)
        or (match_family and match_family == top_family)
    )


def load_speciesnet_taxonomy(s3_client) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Duas tabelas de lookup a partir do arquivo de referência do SpeciesNet
    (formato GUID;class;order;family;genus;species;common_name):
      - species_map: (genus.lower(), species_epithet.lower()) -> GUID
      - genus_map:   genus.lower() -> GUID, só das linhas "<genero> species"
        (campo species vazio) — SpeciesNet tem uma entrada assim por gênero,
        usada quando o táxon migrado é rank=GENUS (maioria dos 13 itens
        curados são nome de gênero, não de espécie completa)."""
    obj = s3_client.get_object(Bucket=TAXONOMY_S3_BUCKET, Key=TAXONOMY_S3_KEY)
    text = obj["Body"].read().decode("utf-8")
    species_map: dict[tuple[str, str], str] = {}
    genus_map: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) != 7:
            continue
        guid, _cls, _order, _family, genus, species, _common = parts
        if genus and species:
            species_map[(genus.lower(), species.lower())] = guid
        elif genus and not species:
            genus_map[genus.lower()] = guid
    return species_map, genus_map


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Não escreve nada — só mostra o que faria")
    args = parser.parse_args()

    ddb = boto3.resource("dynamodb", region_name=REGION)
    s3  = boto3.client("s3", region_name=REGION)

    species_tbl    = ddb.Table(SPECIES_TABLE)
    taxon_tbl      = ddb.Table(TAXON_TABLE)
    taxon_name_tbl = ddb.Table(TAXON_NAME_TABLE)

    print("→ Lendo siab-species...")
    items = species_tbl.scan().get("Items", [])
    print(f"  {len(items)} itens encontrados.\n")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    results_exact:  list[str] = []
    results_fuzzy:  list[str] = []
    results_review: list[tuple[str, str]] = []  # (nome, motivo)
    migrated_taxon_keys: dict[str, int] = {}  # nome original -> taxon_key
    dry_run_taxon_data:  dict[int, dict] = {}  # taxon_key -> taxon_item (só usado em --dry-run)

    for item in items:
        name = item["name"]
        print(f"── {name!r} ", end="")
        try:
            match = gbif_match(name)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"→ FALHA DE REDE ({exc}), pulando")
            results_review.append((name, f"GBIF inacessível: {exc}"))
            continue
        time.sleep(GBIF_REQUEST_DELAY_S)

        match_type = match.get("matchType")
        status     = match.get("status")
        print(f"→ matchType={match_type} status={status} canonicalName={match.get('canonicalName')!r}")

        accepted = False
        if match_type == "EXACT" and status in ("ACCEPTED", "SYNONYM"):
            accepted = True
            results_exact.append(name)
        elif match_type == "FUZZY" and status in ("ACCEPTED", "SYNONYM"):
            if fuzzy_match_confirmed_by_search(name, match):
                accepted = True
                results_fuzzy.append(name)
            else:
                results_review.append((name, f"FUZZY não confirmado por species/search (species/match sugeria {match.get('canonicalName')!r} — provável falso positivo, ver Quati/Quasi no relatório)"))
        else:
            results_review.append((name, f"matchType={match_type} status={status} — sem correspondência taxonômica útil"))

        if not accepted:
            continue

        taxon_key = resolve_taxon_key(match)
        if taxon_key is None:
            results_review.append((name, "status inesperado sem usageKey/acceptedUsageKey"))
            continue

        migrated_taxon_keys[name] = taxon_key

        taxon_item = {
            "taxon_key":       taxon_key,
            "scientific_name": match.get("canonicalName") or match.get("scientificName"),
            "rank":            match.get("rank"),
            "kingdom":         match.get("kingdom"),
            "phylum":          match.get("phylum"),
            "class":           match.get("class"),
            "order":           match.get("order"),
            "family":          match.get("family"),
            "genus":           match.get("genus"),
            "backbone_version": BACKBONE_VERSION,
            "last_synced_at":  now,
        }
        taxon_item = {k: v for k, v in taxon_item.items() if v is not None}

        name_type = classify_name_type(name, match.get("canonicalName"))
        name_id   = _name_id(taxon_key, "SIAB-curated", name)
        name_item = {
            "name_id":      name_id,
            "taxon_key":    taxon_key,
            "name":         name,
            "name_type":    name_type,
            "language":     None if name_type == "SCIENTIFIC" else "por",
            "region":       "BR" if name_type == "VERNACULAR" else None,
            "is_preferred": True,
            "source":       "SIAB-curated",
        }
        name_item = {k: v for k, v in name_item.items() if v is not None}

        if args.dry_run:
            print(f"   [dry-run] taxon_key={taxon_key} taxon={taxon_item}")
            print(f"   [dry-run] name={name_item}")
            dry_run_taxon_data[taxon_key] = taxon_item
        else:
            taxon_tbl.put_item(Item=taxon_item)
            taxon_name_tbl.put_item(Item=name_item)

    print("\n→ Populando nomes vernaculares em português (GBIF)...")
    new_vernacular_count = 0
    existing_vernacular_count = 0
    for name, taxon_key in migrated_taxon_keys.items():
        try:
            vernaculars = gbif_vernacular_names_pt(taxon_key)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  ⚠ {name} (taxon_key={taxon_key}): falha ao buscar vernacularNames ({exc})")
            continue
        time.sleep(GBIF_REQUEST_DELAY_S)

        if not vernaculars:
            continue

        # Nomes SIAB-curated já gravados pra este taxon_key — não duplicar.
        existing_names_norm = set()
        if not args.dry_run:
            resp = taxon_name_tbl.query(
                IndexName="by-taxon-key",
                KeyConditionExpression=Key("taxon_key").eq(taxon_key),
            )
            existing_names_norm = {_normalize(it["name"]) for it in resp.get("Items", [])}

        for vname in set(vernaculars):
            if _normalize(vname) in existing_names_norm:
                existing_vernacular_count += 1
                continue
            new_vernacular_count += 1
            vname_id = _name_id(taxon_key, "GBIF", vname)
            vname_item = {
                "name_id":      vname_id,
                "taxon_key":    taxon_key,
                "name":         vname,
                "name_type":    "VERNACULAR",
                "language":     "por",
                "is_preferred": False,
                "source":       "GBIF",
            }
            if args.dry_run:
                print(f"   [dry-run] {name} (taxon_key={taxon_key}): + {vname!r}")
            else:
                taxon_name_tbl.put_item(Item=vname_item)

    print(f"  {new_vernacular_count} nomes novos do GBIF, {existing_vernacular_count} já existiam (SIAB-curated).\n")

    print("→ Cruzando com a taxonomia do SpeciesNet (taxonomy_release.20260609.txt)...")
    species_map, genus_map = load_speciesnet_taxonomy(s3)
    print(f"  {len(species_map)} pares (genus, species) + {len(genus_map)} entradas só-de-gênero carregadas.")
    guid_matches = 0
    for name, taxon_key in migrated_taxon_keys.items():
        # Em --dry-run não há nada gravado em siab-taxon ainda pra reler —
        # usa os dados já calculados no loop de migração acima em vez de
        # tentar um get_item que sempre voltaria vazio.
        genus = None
        sci   = None
        if not args.dry_run:
            taxon_item = taxon_tbl.get_item(Key={"taxon_key": taxon_key}).get("Item")
            if taxon_item:
                genus = (taxon_item.get("genus") or "").lower()
                sci   = taxon_item.get("scientific_name") or ""
        else:
            genus = dry_run_taxon_data.get(taxon_key, {}).get("genus", "").lower()
            sci   = dry_run_taxon_data.get(taxon_key, {}).get("scientific_name", "")
        if not genus:
            continue

        parts   = sci.split() if sci else []
        epithet = parts[1].lower() if len(parts) >= 2 else ""

        guid = species_map.get((genus, epithet)) if epithet else None
        if not guid:
            guid = genus_map.get(genus)  # fallback: táxon é rank=GENUS, sem epíteto

        if guid:
            guid_matches += 1
            print(f"   {name} → speciesnet_guid={guid}")
            if not args.dry_run:
                taxon_tbl.update_item(
                    Key={"taxon_key": taxon_key},
                    UpdateExpression="SET speciesnet_guid = :g",
                    ExpressionAttributeValues={":g": guid},
                )
        else:
            print(f"   {name}: sem correspondência no SpeciesNet")
    print(f"  {guid_matches}/{len(migrated_taxon_keys)} táxons migrados têm GUID correspondente no SpeciesNet.\n")

    print("═" * 70)
    print("RESUMO DA MIGRAÇÃO")
    print("═" * 70)
    print(f"EXACT:  {len(results_exact)}  → {results_exact}")
    print(f"FUZZY (confirmado por species/search): {len(results_fuzzy)}  → {results_fuzzy}")
    print(f"NEEDS_REVIEW: {len(results_review)}")
    for name, reason in results_review:
        print(f"  - {name!r}: {reason}")
    print(f"\nTotal migrado: {len(migrated_taxon_keys)}/{len(items)}")
    print(f"Nomes vernaculares novos (GBIF): {new_vernacular_count}")
    print(f"Nomes vernaculares já existentes: {existing_vernacular_count}")
    print(f"speciesnet_guid preenchido: {guid_matches}/{len(migrated_taxon_keys)}")


if __name__ == "__main__":
    main()
