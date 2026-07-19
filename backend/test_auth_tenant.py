"""
Testes de autenticação (401) e isolamento de tenant para os 4 endpoints
que anteriormente só tinham cobertura de happy path:

  - POST   /projects/{id}/videos/upload
  - GET    /projects/{id}/appearances
  - PATCH  /appearances/{id}/review
  - GET    /projects/{id}/appearances/export

A fixture _patch_jwt de backend/conftest.py é autouse=True — JWT_VALIDATION=True.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.api import app
from backend.conftest import DEFAULT_TENANT, make_jwt
from backend.test_endpoints_new import _condition_values, _video_item, _frame_ann_item, _mock_groups_source

TENANT_ID = DEFAULT_TENANT

_TOKEN = make_jwt()
client        = TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"})
no_auth_client = TestClient(app)


# ── Helpers compartilhados ─────────────────────────────────────────────────────

def _make_appearance(
    appearance_id: str = "app-001",
    tenant_id: str = TENANT_ID,
    review_status: str = "pending",
    species: str = "dasyprocta leporina",
    ts_start: str = "2025-01-11T08:00:00",
    camera_id: str = "CAM01",
) -> dict:
    vid_id = "vid-001"
    return {
        "tenant_id":               tenant_id,
        "appearance_id":           appearance_id,
        "video_id":                vid_id,
        "video_id#appearance_id":  f"{vid_id}#{appearance_id}",
        "tenant_id#project_id":    f"{tenant_id}#proj-001",
        "project_id":              "proj-001",
        "species":                 species,
        "review_status":           review_status,
        "tenant_id#review_status": f"{tenant_id}#{review_status}",
        "ts_start":                ts_start,
        "camera_id":               camera_id,
        "species_score":           0.91,
        "support_frames":          3,
        "individual_count":        1,
    }


def _app_tbl(items: list[dict]) -> MagicMock:
    m = MagicMock()
    m.query.return_value = {"Items": items}
    m.update_item.return_value = {"Attributes": items[0] if items else {}}
    return m


def _s3_mock(presigned_url: str = "https://s3.amazonaws.com/bucket/key?X-Amz=sig") -> MagicMock:
    m = MagicMock()
    m.generate_presigned_url.return_value = presigned_url
    return m


def _sqs_mock() -> MagicMock:
    m = MagicMock()
    m.get_queue_url.return_value = {"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/siab-videos"}
    m.send_message.return_value  = {"MessageId": "msg-test"}
    return m


def _videos_tbl_mock(tenant_id: str = TENANT_ID) -> MagicMock:
    m = MagicMock()
    m.put_item.return_value    = {}
    m.update_item.return_value = {}
    m.get_item.return_value    = {"Item": {
        "tenant_id":           tenant_id,
        "project_id#video_id": "proj-001#vid-001",
        "s3_key":              f"{tenant_id}/videos/vid-001.avi",
        "status":              "pending_upload",
    }}
    return m


# ══════════════════════════════════════════════════════════════════════════════
# POST /projects/{project_id}/videos/upload-url — auth + tenant isolation
# POST /projects/{project_id}/videos/{video_id}/confirm — auth + tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestUploadVideoAuth(unittest.TestCase):

    # ── upload-url ──────────────────────────────────────────────────────────

    def test_upload_url_no_auth_returns_401(self):
        resp = no_auth_client.post(
            "/projects/proj-001/videos/upload-url",
            json={"filename": "vid.avi"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_upload_url_bad_token_returns_401(self):
        resp = client.post(
            "/projects/proj-001/videos/upload-url",
            json={"filename": "vid.avi"},
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_upload_url_expired_token_returns_401(self):
        resp = client.post(
            "/projects/proj-001/videos/upload-url",
            json={"filename": "vid.avi"},
            headers={"Authorization": f"Bearer {make_jwt(expired=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_upload_url_s3_key_uses_jwt_tenant(self):
        """O s3_key retornado usa o tenant_id do JWT, não parâmetro da URL."""
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        tbl = _videos_tbl_mock("outro-tenant")
        s3  = _s3_mock()
        with patch("backend.api._s3_client",    return_value=s3), \
             patch("backend.api._videos_table", return_value=tbl):
            resp = client.post(
                "/projects/proj-001/videos/upload-url",
                json={"filename": "vid.avi", "content_type": "video/x-msvideo"},
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        self.assertEqual(resp.status_code, 200)
        s3_key = resp.json()["s3_key"]
        self.assertTrue(s3_key.startswith("outro-tenant/videos/"),
                        f"S3 key deveria começar com 'outro-tenant/videos/', foi: {s3_key}")
        self.assertFalse(s3_key.startswith(TENANT_ID))

    def test_upload_url_dynamodb_record_uses_jwt_tenant(self):
        """O registro gravado em siab-videos usa tenant_id do JWT."""
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        tbl = _videos_tbl_mock("outro-tenant")
        s3  = _s3_mock()
        with patch("backend.api._s3_client",    return_value=s3), \
             patch("backend.api._videos_table", return_value=tbl):
            client.post(
                "/projects/proj-001/videos/upload-url",
                json={"filename": "v.avi"},
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        item = tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"], "outro-tenant")
        self.assertNotEqual(item["tenant_id"], TENANT_ID)

    # ── confirm ─────────────────────────────────────────────────────────────

    def test_confirm_no_auth_returns_401(self):
        resp = no_auth_client.post("/projects/proj-001/videos/vid-001/confirm")
        self.assertEqual(resp.status_code, 401)

    def test_confirm_bad_token_returns_401(self):
        resp = client.post(
            "/projects/proj-001/videos/vid-001/confirm",
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_confirm_sqs_message_uses_jwt_tenant(self):
        """tenant_id na mensagem SQS vem do JWT, não de parâmetro externo."""
        import json as _json
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        tbl = _videos_tbl_mock("outro-tenant")
        sqs = _sqs_mock()
        with patch("backend.api._videos_table", return_value=tbl), \
             patch("backend.api._sqs_client",   return_value=sqs):
            client.post(
                "/projects/proj-001/videos/vid-001/confirm",
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        msg = _json.loads(sqs.send_message.call_args[1]["MessageBody"])
        self.assertEqual(msg["tenant_id"], "outro-tenant")
        self.assertNotEqual(msg["tenant_id"], TENANT_ID)


# ══════════════════════════════════════════════════════════════════════════════
# GET /projects/{project_id}/appearances — auth + tenant isolation + paginação
# ══════════════════════════════════════════════════════════════════════════════

class TestListAppearancesAuth(unittest.TestCase):

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/projects/proj-001/appearances")
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        resp = client.get(
            "/projects/proj-001/appearances",
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_gsi_pk_uses_jwt_tenant(self):
        """GSI 'by-species' usa PK 'tenant_id#project_id' do JWT — não parâmetro externo."""
        tbl = _app_tbl([])
        with patch("backend.api._appearances_table", return_value=tbl):
            client.get("/projects/proj-001/appearances")
        call_kw = tbl.query.call_args[1]
        vals = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn(f"{TENANT_ID}#proj-001", vals)

    def test_tenant_isolation_other_tenant_sees_no_items(self):
        """Tenant B com mesmo project_id consulta com PK diferente, não vê dados de A."""
        tbl            = _app_tbl([])
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get(
                "/projects/proj-001/appearances",
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        self.assertEqual(resp.status_code, 200)
        call_kw = tbl.query.call_args[1]
        vals = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn("outro-tenant#proj-001", vals)
        self.assertNotIn(f"{TENANT_ID}#proj-001", vals)

    def test_pagination_follows_last_evaluated_key(self):
        """_appearances_from_project pagina corretamente via LastEvaluatedKey."""
        page1 = [_make_appearance(f"a{i}") for i in range(3)]
        page2 = [_make_appearance(f"a{i}") for i in range(3, 5)]
        tbl   = MagicMock()
        tbl.query.side_effect = [
            {"Items": page1, "LastEvaluatedKey": {"pk": "key1"}},
            {"Items": page2},
        ]
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances")
        self.assertEqual(resp.json()["count"], 5)
        self.assertEqual(tbl.query.call_count, 2)

    def test_limit_parameter_caps_results(self):
        """Parâmetro limit corta a lista após buscar tudo do DynamoDB."""
        items = [_make_appearance(f"a{i}") for i in range(10)]
        tbl   = _app_tbl(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances?limit=3")
        self.assertEqual(resp.json()["count"], 3)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /appearances/{appearance_id}/review — auth + tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestReviewAppearanceAuth(unittest.TestCase):

    def _setup(self, items: list[dict]):
        app_tbl = MagicMock()
        rev_tbl = MagicMock()
        app_tbl.query.return_value       = {"Items": items}
        app_tbl.update_item.return_value = {"Attributes": items[0] if items else {}}
        rev_tbl.put_item.return_value    = {}
        return app_tbl, rev_tbl

    def test_no_auth_returns_401(self):
        resp = no_auth_client.patch(
            "/appearances/app-001/review",
            json={"action": "confirm"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        resp = client.patch(
            "/appearances/app-001/review",
            json={"action": "confirm"},
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_cannot_review_other_tenant_appearance(self):
        """Tenant B não consegue revisar aparição de Tenant A — _find_appearance retorna None."""
        # O mock retorna a aparição de Tenant A, mas _find_appearance filtra por tenant_id do JWT
        app_item_a = _make_appearance("app-001", tenant_id=TENANT_ID)
        # Para tenant B, a query retorna lista vazia (sem dados do tenant A)
        app_tbl = MagicMock()
        app_tbl.query.return_value = {"Items": []}  # nenhum item para tenant B
        rev_tbl = MagicMock()

        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            resp = client.patch(
                "/appearances/app-001/review",
                json={"action": "confirm"},
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        self.assertEqual(resp.status_code, 404)
        # Confirmar que a query usou o tenant do JWT (tenant B), não o tenant A
        call_kw = app_tbl.query.call_args[1]
        vals    = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn("outro-tenant", vals)
        self.assertNotIn(TENANT_ID,   vals)

    def test_review_record_tenant_id_comes_from_jwt(self):
        """review gravado em siab-reviews usa tenant_id do JWT."""
        app = _make_appearance("app-001")
        app_tbl, rev_tbl = self._setup([app])
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        # Para tenant B a query retorna o app_item (simulando que ele pertence a B)
        app_tbl.query.return_value = {"Items": [
            {**app, "tenant_id": "outro-tenant",
             "tenant_id#review_status": "outro-tenant#pending"}
        ]}
        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            client.patch(
                "/appearances/app-001/review",
                json={"action": "confirm"},
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        rev_item = rev_tbl.put_item.call_args[1]["Item"]
        self.assertEqual(rev_item["tenant_id"], "outro-tenant")
        self.assertNotEqual(rev_item["tenant_id"], TENANT_ID)


# ══════════════════════════════════════════════════════════════════════════════
# GET /projects/{project_id}/appearances/export — auth + tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestExportAppearancesAuth(unittest.TestCase):

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/projects/proj-001/appearances/export")
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        resp = client.get(
            "/projects/proj-001/appearances/export",
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_query_uses_jwt_tenant(self):
        """Export usa _confirmed_appearance_groups — query em siab-videos usa tenant_id do JWT."""
        vid_tbl = MagicMock()
        vid_tbl.query.return_value = {"Items": []}
        with patch("backend.api._videos_table", return_value=vid_tbl):
            client.get("/projects/proj-001/appearances/export")
        call_kw = vid_tbl.query.call_args[1]
        vals    = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn(TENANT_ID, vals)

    def test_tenant_isolation_other_tenant_gets_separate_query(self):
        """Tenant B exporta com tenant_id diferente na query — dados de A não vazam."""
        vid_tbl = MagicMock()
        vid_tbl.query.return_value = {"Items": []}
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        with patch("backend.api._videos_table", return_value=vid_tbl):
            resp = client.get(
                "/projects/proj-001/appearances/export",
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        self.assertEqual(resp.status_code, 200)
        call_kw = vid_tbl.query.call_args[1]
        vals    = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn("outro-tenant", vals)
        self.assertNotIn(TENANT_ID, vals)

    def test_export_only_confirmed_from_jwt_tenant(self):
        """Apenas frames com annotated_species (confirmados) do tenant do JWT aparecem no CSV."""
        videos = [_video_item("vid-001"), _video_item("vid-002"), _video_item("vid-003")]
        frames = [
            [_frame_ann_item("vid-001", species="dasyprocta leporina")],   # confirmado
            [_frame_ann_item("vid-002", species=None)],                    # não revisado ainda
            [_frame_ann_item("vid-003", species="puma concolor")],         # confirmado
        ]
        vid_tbl, ann_tbl = _mock_groups_source(videos, frames)
        with patch("backend.api._videos_table", return_value=vid_tbl), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl):
            resp = client.get("/projects/proj-001/appearances/export")
        lines = [l for l in resp.text.strip().split("\n") if l]
        self.assertEqual(len(lines), 3)  # header + 2 confirmadas


if __name__ == "__main__":
    unittest.main(verbosity=2)
