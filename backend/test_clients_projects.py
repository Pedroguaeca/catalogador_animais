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

from fastapi.testclient import TestClient

from backend.api import app
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
    m = MagicMock()
    m.query.return_value    = {"Items": items or []}
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


if __name__ == "__main__":
    unittest.main()
