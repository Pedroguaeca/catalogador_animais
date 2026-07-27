"""
pipeline/test_gbif_allowlist_sync.py — Testes do sync da allowlist GBIF.

Usa mocks completos para DynamoDB, S3 e a chamada HTTP ao GBIF — sem rede.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from pipeline.gbif_allowlist_sync import (
    SyncResult,
    _discover_classified_species,
    sync_allowlist,
)


# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeFrameAnnotationsTable:
    """Tabela DynamoDB em memória — só implementa .scan(), igual ao uso real
    (sem GSI por ai_species, mesma limitação de _discover_projects)."""

    def __init__(self, items: list[dict]) -> None:
        self._items = items

    def scan(self, **kwargs) -> dict:
        return {"Items": self._items}


class _FakeS3:
    """S3 em memória — get_object/put_object sobre um dict {key: bytes}."""

    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self._objects = objects or {}

    def get_object(self, Bucket, Key):
        if Key not in self._objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": _FakeBody(self._objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):
        self._objects[Key] = Body


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self):
        return self._data


def make_frame(ai_species: str, taxonomic_level: str = "species") -> dict:
    return {"ai_species": ai_species, "taxonomic_level": taxonomic_level}


def make_ddb(items: list[dict]):
    fake_table = _FakeFrameAnnotationsTable(items)
    ddb = MagicMock()
    ddb.Table.return_value = fake_table
    return ddb


# ── _discover_classified_species ─────────────────────────────────────────────


class TestDiscoverClassifiedSpecies:
    def test_only_species_level_entries_counted(self):
        items = [
            make_frame("dasyprocta leporina", "species"),
            make_frame("didelphidae", "family"),
            make_frame("aves", "class"),
            make_frame("blank", "unidentified"),
        ]
        table = _FakeFrameAnnotationsTable(items)
        assert _discover_classified_species(table) == {"dasyprocta leporina"}

    def test_dedupes_and_lowercases(self):
        items = [
            make_frame("Dasyprocta Leporina", "species"),
            make_frame("dasyprocta leporina", "species"),
        ]
        table = _FakeFrameAnnotationsTable(items)
        assert _discover_classified_species(table) == {"dasyprocta leporina"}

    def test_empty_table(self):
        table = _FakeFrameAnnotationsTable([])
        assert _discover_classified_species(table) == set()


# ── sync_allowlist ────────────────────────────────────────────────────────────


class TestSyncAllowlist:
    def test_first_sync_queries_all_classified_species(self):
        ddb = make_ddb([make_frame("penelope purpurascens", "species")])
        s3 = _FakeS3()

        with patch(
            "pipeline.gbif_allowlist_sync._query_gbif_occurrence_br",
            return_value=0,
        ) as query:
            result = sync_allowlist(ddb_resource=ddb, s3_client=s3, bucket="b", table_name="t")

        query.assert_called_once_with("penelope purpurascens")
        assert result == SyncResult(checked=1, new=1, updated=1, failed=0)

        saved = json.loads(s3._objects["models/gbif/br_allowlist.json"])
        assert saved["penelope purpurascens"]["ocorre_br"] is False
        assert saved["penelope purpurascens"]["n_registros_gbif"] == 0

    def test_species_with_occurrence_marked_true(self):
        ddb = make_ddb([make_frame("cuniculus paca", "species")])
        s3 = _FakeS3()

        with patch(
            "pipeline.gbif_allowlist_sync._query_gbif_occurrence_br",
            return_value=42000,
        ):
            sync_allowlist(ddb_resource=ddb, s3_client=s3, bucket="b", table_name="t")

        saved = json.loads(s3._objects["models/gbif/br_allowlist.json"])
        assert saved["cuniculus paca"]["ocorre_br"] is True
        assert saved["cuniculus paca"]["n_registros_gbif"] == 42000

    def test_does_not_requery_species_already_cached(self):
        existing = {"cuniculus paca": {"ocorre_br": True, "n_registros_gbif": 100, "synced_at": "2026-01-01T00:00:00Z"}}
        ddb = make_ddb([make_frame("cuniculus paca", "species")])
        s3 = _FakeS3({"models/gbif/br_allowlist.json": json.dumps(existing).encode()})

        with patch("pipeline.gbif_allowlist_sync._query_gbif_occurrence_br") as query:
            result = sync_allowlist(ddb_resource=ddb, s3_client=s3, bucket="b", table_name="t")

        query.assert_not_called()
        assert result == SyncResult(checked=1, new=0, updated=0, failed=0)

    def test_network_failure_on_one_species_does_not_abort_sync(self):
        ddb = make_ddb([
            make_frame("cuniculus paca", "species"),
            make_frame("penelope purpurascens", "species"),
        ])
        s3 = _FakeS3()

        def fake_query(species):
            return None if species == "penelope purpurascens" else 50

        with patch(
            "pipeline.gbif_allowlist_sync._query_gbif_occurrence_br",
            side_effect=fake_query,
        ):
            result = sync_allowlist(ddb_resource=ddb, s3_client=s3, bucket="b", table_name="t")

        assert result.failed == 1
        assert result.updated == 1
        saved = json.loads(s3._objects["models/gbif/br_allowlist.json"])
        assert "cuniculus paca" in saved
        # espécie com falha de rede fica ausente do cache — consumidor trata
        # ausência como "precisa revisão" (default seguro), não como "ok".
        assert "penelope purpurascens" not in saved

    def test_no_new_species_skips_s3_write(self):
        existing = {"cuniculus paca": {"ocorre_br": True, "n_registros_gbif": 100, "synced_at": "2026-01-01T00:00:00Z"}}
        ddb = make_ddb([make_frame("cuniculus paca", "species")])
        s3 = _FakeS3({"models/gbif/br_allowlist.json": json.dumps(existing).encode()})
        s3.put_object = MagicMock(side_effect=AssertionError("não deveria gravar sem novidade"))

        sync_allowlist(ddb_resource=ddb, s3_client=s3, bucket="b", table_name="t")
