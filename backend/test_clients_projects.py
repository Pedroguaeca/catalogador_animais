"""
Testes de SIAB-150 (Fase 1 — núcleo de dados de clientes/projetos):
  - POST /clients
  - GET  /clients
  - POST /projects
  - GET  /projects
  - FK: POST /projects/{project_id}/videos/upload-url valida project_id existente

A fixture _patch_jwt em backend/conftest.py é autouse=True — JWT_VALIDATION=True
em todos os testes sem SIAB_JWT_VALIDATION=off.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from boto3.dynamodb.conditions import Attr, Key
from fastapi.testclient import TestClient

from backend.api import _project_exists, app
from backend.conftest import DEFAULT_TENANT, make_jwt

TENANT_ID = DEFAULT_TENANT

_TOKEN = make_jwt()
client = TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"})
no_auth_client = TestClient(app)


def _clients_tbl_mock(items: list[dict] | None = None, get_item: dict | None = None) -> MagicMock:
    m = MagicMock()
    m.query.return_value    = {"Items": items or []}
    m.put_item.return_value = {}
    m.get_item.return_value = {"Item": get_item} if get_item else {}
    return m


def _projects_tbl_mock(items: list[dict] | None = None) -> MagicMock:
    # Count sempre coerente com Items (como uma resposta real do DynamoDB
    # traria) - necessário desde que _project_exists passou a usar
    # Select="COUNT" (SIAB, correção do bug real do Limit=1).
    m = MagicMock()
    m.query.return_value    = {"Items": items or [], "Count": len(items or [])}
    m.put_item.return_value = {}
    return m


# ══════════════════════════════════════════════════════════════════════════════
# POST /clients
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateClient(unittest.TestCase):

    def test_happy_path_returns_201_with_generated_client_id(self):
        tbl = _clients_tbl_mock()
        with patch("backend.api._clients_table", return_value=tbl):
            resp = client.post("/clients", json={"nome": "Cliente Teste"})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["nome"], "Cliente Teste")
        # client_id é gerado (uuid4) — nunca o nome digitado usado como chave
        self.assertNotEqual(body["client_id"], "Cliente Teste")
        self.assertNotEqual(body["client_id"], "cliente-teste")
        self.assertEqual(len(body["client_id"]), 36)  # formato uuid4

    def test_empty_nome_returns_422(self):
        resp = client.post("/clients", json={"nome": "   "})
        self.assertEqual(resp.status_code, 422)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.post("/clients", json={"nome": "X"})
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_item_uses_jwt_tenant(self):
        tbl = _clients_tbl_mock()
        with patch("backend.api._clients_table", return_value=tbl):
            client.post("/clients", json={"nome": "X"})
        item = tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"], TENANT_ID)


# ══════════════════════════════════════════════════════════════════════════════
# GET /clients
# ══════════════════════════════════════════════════════════════════════════════

class TestListClients(unittest.TestCase):

    def test_returns_items_for_tenant(self):
        items = [{"tenant_id": TENANT_ID, "client_id": "c1", "nome": "Cliente A"}]
        tbl = _clients_tbl_mock(items=items)
        with patch("backend.api._clients_table", return_value=tbl):
            resp = client.get("/clients")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["nome"], "Cliente A")

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/clients")
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════════════
# POST /projects
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateProject(unittest.TestCase):

    def _existing_client(self, client_id="c1"):
        return {"tenant_id": TENANT_ID, "client_id": client_id, "nome": "Cliente Teste"}

    def test_happy_path_returns_201_with_generated_project_id(self):
        clients_tbl  = _clients_tbl_mock(get_item=self._existing_client())
        projects_tbl = _projects_tbl_mock()
        with patch("backend.api._clients_table",  return_value=clients_tbl), \
             patch("backend.api._projects_table", return_value=projects_tbl):
            resp = client.post("/projects", json={
                "client_id": "c1", "nome": "Projeto Junho", "estado": "SP", "bioma": "Mata Atlântica",
            })
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["nome"],   "Projeto Junho")
        self.assertEqual(body["estado"], "SP")
        self.assertEqual(body["bioma"],  "Mata Atlântica")
        self.assertEqual(body["client_id"], "c1")
        self.assertEqual(len(body["project_id"]), 36)  # uuid4
        self.assertEqual(body["client_id#project_id"], f"c1#{body['project_id']}")

    def test_unknown_client_id_returns_404(self):
        clients_tbl = _clients_tbl_mock(get_item=None)
        with patch("backend.api._clients_table", return_value=clients_tbl):
            resp = client.post("/projects", json={
                "client_id": "nao-existe", "nome": "X", "estado": "SP", "bioma": "Cerrado",
            })
        self.assertEqual(resp.status_code, 404)

    def test_invalid_estado_returns_422(self):
        clients_tbl = _clients_tbl_mock(get_item=self._existing_client())
        with patch("backend.api._clients_table", return_value=clients_tbl):
            resp = client.post("/projects", json={
                "client_id": "c1", "nome": "X", "estado": "XX", "bioma": "Cerrado",
            })
        self.assertEqual(resp.status_code, 422)

    def test_invalid_bioma_returns_422(self):
        clients_tbl = _clients_tbl_mock(get_item=self._existing_client())
        with patch("backend.api._clients_table", return_value=clients_tbl):
            resp = client.post("/projects", json={
                "client_id": "c1", "nome": "X", "estado": "SP", "bioma": "Bioma Inventado",
            })
        self.assertEqual(resp.status_code, 422)

    def test_optional_fields_omitted_when_not_sent(self):
        clients_tbl  = _clients_tbl_mock(get_item=self._existing_client())
        projects_tbl = _projects_tbl_mock()
        with patch("backend.api._clients_table",  return_value=clients_tbl), \
             patch("backend.api._projects_table", return_value=projects_tbl):
            client.post("/projects", json={
                "client_id": "c1", "nome": "X", "estado": "SP", "bioma": "Cerrado",
            })
        item = projects_tbl.put_item.call_args[1]["Item"]
        self.assertNotIn("data", item)
        self.assertNotIn("nome_area_estudo", item)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.post("/projects", json={
            "client_id": "c1", "nome": "X", "estado": "SP", "bioma": "Cerrado",
        })
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════════════
# GET /projects
# ══════════════════════════════════════════════════════════════════════════════

class TestListProjects(unittest.TestCase):

    def test_returns_items_for_tenant(self):
        items = [{"tenant_id": TENANT_ID, "client_id#project_id": "c1#p1",
                  "client_id": "c1", "project_id": "p1", "nome": "Projeto A"}]
        tbl = _projects_tbl_mock(items=items)
        with patch("backend.api._projects_table", return_value=tbl):
            resp = client.get("/projects")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["nome"], "Projeto A")

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/projects")
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════════════
# FK: POST /projects/{project_id}/videos/upload-url valida project_id existente
# ══════════════════════════════════════════════════════════════════════════════

class TestVideoUploadValidatesProjectExists(unittest.TestCase):

    def test_nonexistent_project_returns_422(self):
        projects_tbl = _projects_tbl_mock(items=[])  # nenhum projeto encontrado
        with patch("backend.api._projects_table", return_value=projects_tbl):
            resp = client.post(
                "/projects/proj-inexistente/videos/upload-url",
                json={"filename": "vid.avi", "content_type": "video/x-msvideo"},
            )
        self.assertEqual(resp.status_code, 422)

    def test_existing_project_does_not_block_upload(self):
        projects_tbl = _projects_tbl_mock(items=[{"tenant_id": TENANT_ID, "project_id": "proj-001"}])
        videos_tbl   = MagicMock()
        videos_tbl.put_item.return_value = {}
        s3 = MagicMock()
        s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/bucket/key"
        with patch("backend.api._projects_table", return_value=projects_tbl), \
             patch("backend.api._videos_table",   return_value=videos_tbl), \
             patch("backend.api._s3_client",      return_value=s3):
            resp = client.post(
                "/projects/proj-001/videos/upload-url",
                json={"filename": "vid.avi", "content_type": "video/x-msvideo"},
            )
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════════════
# Regressão do bug real: _project_exists usava Limit=1 junto de
# FilterExpression. Limit corta quantos itens o DynamoDB AVALIA antes do
# filtro rodar, não quantos sobrevivem a ele — com Limit=1, só o primeiro
# item da partição (por ordem de sort key client_id#project_id) era
# examinado. Achado ao vivo em produção: upload do projeto "Tst"
# (4731e347...) rejeitado com 422 porque "Teste2" (10badcc5...) vinha antes
# na ordem de sort key — mesmo "Tst" existindo de verdade.
#
# _projects_tbl_mock (MagicMock com .query.return_value fixo) NUNCA teria
# pego esse bug — ele já devolve os itens "corretos" prontos, sem reproduzir
# a semântica real de Limit-antes-do-filtro do DynamoDB. Por isso o fake
# abaixo simula essa semântica de propósito.
# ══════════════════════════════════════════════════════════════════════════════

class _FakeProjectsTableDynamoSemantics:
    """Reproduz o comportamento real do DynamoDB Query: se Limit for
    passado, só os primeiros N itens (na ordem dada ao fake, simulando
    ordem de sort key) são avaliados — o FilterExpression roda DEPOIS,
    só sobre esse subconjunto já cortado. Select="COUNT" devolve só a
    contagem, sem os itens."""

    def __init__(self, items_in_sk_order: list[dict]):
        self._items = items_in_sk_order

    def query(self, KeyConditionExpression=None, FilterExpression=None, Limit=None, Select=None, **_kwargs):
        evaluated = self._items[:Limit] if Limit is not None else list(self._items)
        if FilterExpression is not None:
            attr_name = FilterExpression._values[0].name
            target    = FilterExpression._values[1]
            matched = [it for it in evaluated if it.get(attr_name) == target]
        else:
            matched = evaluated
        if Select == "COUNT":
            return {"Count": len(matched)}
        return {"Items": matched, "Count": len(matched)}


class TestProjectExistsRegressionAgainstLimitBug(unittest.TestCase):

    def _projects_in_sk_order(self):
        # Mesma ordem observada ao vivo em produção (client_id#project_id
        # ascendente): "10badcc5..." vem antes de "4731e347...".
        return [
            {"tenant_id": TENANT_ID, "project_id": "10badcc5-8a2d-467e-b04a-d8556e050cba", "nome": "Teste2"},
            {"tenant_id": TENANT_ID, "project_id": "4731e347-9938-499a-b1b0-25f67823795f", "nome": "Tst"},
            {"tenant_id": TENANT_ID, "project_id": "7ffab04c-ce2b-4e66-a5f3-09b3aaf0ac11", "nome": "Abras"},
        ]

    def test_project_first_in_sk_order_is_found(self):
        tbl = _FakeProjectsTableDynamoSemantics(self._projects_in_sk_order())
        with patch("backend.api._projects_table", return_value=tbl):
            self.assertTrue(_project_exists(TENANT_ID, "10badcc5-8a2d-467e-b04a-d8556e050cba"))

    def test_project_second_in_sk_order_is_found(self):
        # Cenário exato do incidente: "Tst" não é o primeiro da partição -
        # com Limit=1 isso "não existia" pro upload, mesmo existindo.
        tbl = _FakeProjectsTableDynamoSemantics(self._projects_in_sk_order())
        with patch("backend.api._projects_table", return_value=tbl):
            self.assertTrue(_project_exists(TENANT_ID, "4731e347-9938-499a-b1b0-25f67823795f"))

    def test_project_last_in_sk_order_is_found(self):
        tbl = _FakeProjectsTableDynamoSemantics(self._projects_in_sk_order())
        with patch("backend.api._projects_table", return_value=tbl):
            self.assertTrue(_project_exists(TENANT_ID, "7ffab04c-ce2b-4e66-a5f3-09b3aaf0ac11"))

    def test_genuinely_nonexistent_project_returns_false(self):
        tbl = _FakeProjectsTableDynamoSemantics(self._projects_in_sk_order())
        with patch("backend.api._projects_table", return_value=tbl):
            self.assertFalse(_project_exists(TENANT_ID, "nao-existe-de-verdade"))

    def test_fake_reproduces_old_limit1_bug_if_reintroduced(self):
        """Prova de que o fake é fiel à semântica real: se alguém reintroduzir
        Limit=1 nessa query, o item que não é o primeiro da partição some -
        exatamente o bug original. Não testa _project_exists (já corrigido),
        só confirma que o fake serve de rede de segurança pra esse padrão."""
        tbl = _FakeProjectsTableDynamoSemantics(self._projects_in_sk_order())
        resp = tbl.query(
            KeyConditionExpression=Key("tenant_id").eq(TENANT_ID),
            FilterExpression=Attr("project_id").eq("4731e347-9938-499a-b1b0-25f67823795f"),
            Limit=1,
        )
        self.assertEqual(resp["Items"], [])


if __name__ == "__main__":
    unittest.main()
