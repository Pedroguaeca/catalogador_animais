"""
backend/test_api.py — Testes dos 4 endpoints da API SIAB.

Usa FastAPI TestClient + unittest.mock.patch para isolar S3, SQS e DynamoDB.
"""

from __future__ import annotations

import io
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.api import app, _DEFAULT_TENANT as TENANT_ID, get_current_role, require_role
from backend.conftest import make_jwt as _make_test_jwt

# TestClient com Authorization header pré-configurado.
# O JWT é assinado com a chave de teste em conftest.py e validado pelo
# mesmo _verify_jwt de produção (JWT_VALIDATION=True, via fixture autouse).
client = TestClient(app, headers={"Authorization": f"Bearer {_make_test_jwt()}"})

# ── Factories de fixtures ──────────────────────────────────────────────────────


def _make_appearance(
    appearance_id: str = "app-001",
    camera_id: str = "0004",
    species: str = "dasyprocta leporina",
    ts_start: str = "2025-01-11T08:14:30",
    ts_end: str   = "2025-01-11T08:15:00",
    review_status: str = "pending",
    video_id: str = "vid-001",
    project_id: str = "proj-001",
    species_score: float = 0.9125,
    individual_count: int = 1,
    taxonomic_path: str = "mammalia;rodentia;dasyproctidae",
) -> dict:
    return {
        "tenant_id":               TENANT_ID,
        "project_id":              project_id,
        "video_id":                video_id,
        "appearance_id":           appearance_id,
        "video_id#appearance_id":  f"{video_id}#{appearance_id}",
        "tenant_id#project_id":    f"{TENANT_ID}#{project_id}",
        "species#appearance_id":   f"{species}#{appearance_id}",
        "tenant_id#review_status": f"{TENANT_ID}#{review_status}",
        "project_id#appearance_id": f"{project_id}#{appearance_id}",
        "camera_id":               camera_id,
        "species":                 species,
        "ts_start":                ts_start,
        "ts_end":                  ts_end,
        "support_frames":          3,
        "best_crop_s3_key":        f"frames/{appearance_id}.jpg",
        "species_score":           Decimal(str(species_score)),
        "individual_count":        individual_count,
        "review_status":           review_status,
        "taxonomic_level":         "species",
        "taxonomic_path":          taxonomic_path,
        "model_version":           "speciesnet-v5.0.5",
    }


# ── POST /projects/{project_id}/videos/upload-url ─────────────────────────────


class TestUploadVideo(unittest.TestCase):

    def _s3_mock(self, presigned_url="https://s3.amazonaws.com/bucket/key?X-Amz=sig"):
        m = MagicMock()
        m.generate_presigned_url.return_value = presigned_url
        return m

    def _sqs_mock(self, queue_url="https://sqs.us-east-1.amazonaws.com/123/siab-videos"):
        m = MagicMock()
        m.get_queue_url.return_value = {"QueueUrl": queue_url}
        m.send_message.return_value  = {"MessageId": "msg-abc"}
        return m

    def _videos_tbl_mock(self):
        m = MagicMock()
        m.put_item.return_value = {}
        m.get_item.return_value = {"Item": {
            "tenant_id": TENANT_ID,
            "project_id#video_id": "proj-001#vid-001",
            "s3_key": f"{TENANT_ID}/videos/vid-001.avi",
            "status": "pending_upload",
        }}
        m.update_item.return_value = {}
        return m

    def test_upload_url_returns_video_id_and_presigned_url(self):
        s3  = self._s3_mock()
        tbl = self._videos_tbl_mock()

        with patch("backend.api._s3_client",     return_value=s3), \
             patch("backend.api._videos_table",  return_value=tbl):
            resp = client.post(
                "/projects/proj-001/videos/upload-url",
                json={"filename": "DSCF0007.avi", "content_type": "video/x-msvideo"},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("video_id",   body)
        self.assertIn("upload_url", body)
        self.assertIn("s3_key",     body)
        self.assertTrue(body["s3_key"].startswith(f"{TENANT_ID}/videos/"))
        self.assertTrue(body["s3_key"].endswith(".avi"))

    def test_upload_url_creates_pending_record_in_dynamodb(self):
        s3  = self._s3_mock()
        tbl = self._videos_tbl_mock()

        with patch("backend.api._s3_client",    return_value=s3), \
             patch("backend.api._videos_table", return_value=tbl):
            client.post(
                "/projects/proj-001/videos/upload-url",
                json={"filename": "test.avi", "content_type": "video/x-msvideo"},
            )

        tbl.put_item.assert_called_once()
        item = tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"],  TENANT_ID)
        self.assertEqual(item["project_id"], "proj-001")
        self.assertEqual(item["status"],     "pending_upload")
        self.assertIn("video_id", item)
        self.assertIn("s3_key",   item)

    def test_confirm_publishes_to_sqs_without_ocr_fields(self):
        tbl = self._videos_tbl_mock()
        sqs = self._sqs_mock()

        with patch("backend.api._videos_table", return_value=tbl), \
             patch("backend.api._sqs_client",   return_value=sqs):
            resp = client.post("/projects/proj-001/videos/vid-001/confirm")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "processing")

        msg = json.loads(sqs.send_message.call_args[1]["MessageBody"])
        self.assertEqual(msg["tenant_id"],  TENANT_ID)
        self.assertEqual(msg["project_id"], "proj-001")
        self.assertIn("video_id",     msg)
        self.assertIn("video_s3_key", msg)
        # OCR fields devem estar AUSENTES da mensagem SQS
        self.assertNotIn("camera_id",     msg)
        self.assertNotIn("captured_at",   msg)
        self.assertNotIn("temperature_c", msg)

    def test_confirm_updates_status_to_uploaded(self):
        tbl = self._videos_tbl_mock()
        sqs = self._sqs_mock()

        with patch("backend.api._videos_table", return_value=tbl), \
             patch("backend.api._sqs_client",   return_value=sqs):
            client.post("/projects/proj-001/videos/vid-001/confirm")

        tbl.update_item.assert_called_once()
        call_kw = tbl.update_item.call_args[1]
        self.assertIn(":s", call_kw["ExpressionAttributeValues"])
        self.assertEqual(call_kw["ExpressionAttributeValues"][":s"], "uploaded")

    def test_confirm_returns_404_for_unknown_video(self):
        tbl = MagicMock()
        tbl.get_item.return_value = {}  # sem "Item"

        with patch("backend.api._videos_table", return_value=tbl):
            resp = client.post("/projects/proj-001/videos/nonexistent/confirm")

        self.assertEqual(resp.status_code, 404)


# ── GET /projects/{project_id}/appearances ────────────────────────────────────


class TestListAppearances(unittest.TestCase):

    def _table_mock(self, items: list[dict]) -> MagicMock:
        m = MagicMock()
        m.query.return_value = {"Items": items}
        return m

    def test_returns_all_appearances_for_project(self):
        items = [_make_appearance("a1"), _make_appearance("a2")]
        tbl   = self._table_mock(items)

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["items"]), 2)

    def test_filter_by_camera_id(self):
        items = [
            _make_appearance("a1", camera_id="0004"),
            _make_appearance("a2", camera_id="0005"),
        ]
        tbl = self._table_mock(items)

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances?camera_id=0004")

        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["camera_id"], "0004")

    def test_filter_by_species(self):
        items = [
            _make_appearance("a1", species="dasyprocta leporina"),
            _make_appearance("a2", species="puma concolor"),
        ]
        tbl = self._table_mock(items)

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances?species=puma")

        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertIn("puma", body["items"][0]["species"])

    def test_filter_by_review_status(self):
        items = [
            _make_appearance("a1", review_status="pending"),
            _make_appearance("a2", review_status="confirmed"),
        ]
        tbl = self._table_mock(items)

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances?review_status=confirmed")

        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["review_status"], "confirmed")

    def test_sorted_by_ts_start(self):
        items = [
            _make_appearance("a1", ts_start="2025-01-11T10:00:00"),
            _make_appearance("a2", ts_start="2025-01-11T08:00:00"),
            _make_appearance("a3", ts_start="2025-01-11T09:00:00"),
        ]
        tbl = self._table_mock(items)

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances")

        ids = [i["appearance_id"] for i in resp.json()["items"]]
        self.assertEqual(ids, ["a2", "a3", "a1"])

    def test_decimal_fields_serialized_as_float(self):
        items = [_make_appearance("a1", species_score=0.9125)]
        tbl   = self._table_mock(items)

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances")

        score = resp.json()["items"][0]["species_score"]
        self.assertIsInstance(score, float)
        self.assertAlmostEqual(score, 0.9125)

    def test_empty_project_returns_empty_list(self):
        tbl = self._table_mock([])

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)


# ── PATCH /appearances/{appearance_id}/review ─────────────────────────────────


class TestReviewAppearance(unittest.TestCase):

    def _setup_mocks(self, appearance: dict):
        app_tbl = MagicMock()
        rev_tbl = MagicMock()

        app_tbl.query.return_value = {"Items": [appearance]}
        app_tbl.update_item.return_value = {
            "Attributes": {**appearance, "review_status": "confirmed"}
        }
        rev_tbl.put_item.return_value = {}
        return app_tbl, rev_tbl

    def test_confirm_sets_review_status_confirmed(self):
        app = _make_appearance("app-001", review_status="pending")
        app_tbl, rev_tbl = self._setup_mocks(app)

        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            resp = client.patch(
                "/appearances/app-001/review",
                json={"action": "confirm"},
            )

        self.assertEqual(resp.status_code, 200)
        app_tbl.update_item.assert_called_once()
        call_kw = app_tbl.update_item.call_args[1]
        self.assertIn(":rs", call_kw["ExpressionAttributeValues"])
        self.assertEqual(call_kw["ExpressionAttributeValues"][":rs"], "confirmed")

    def test_reject_sets_review_status_rejected(self):
        app = _make_appearance("app-001", review_status="pending")
        app_tbl, rev_tbl = self._setup_mocks(app)
        app_tbl.update_item.return_value = {
            "Attributes": {**app, "review_status": "rejected"}
        }

        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            resp = client.patch(
                "/appearances/app-001/review",
                json={"action": "reject"},
            )

        self.assertEqual(resp.status_code, 200)
        call_kw = app_tbl.update_item.call_args[1]
        self.assertEqual(call_kw["ExpressionAttributeValues"][":rs"], "rejected")

    def test_correct_updates_species(self):
        app = _make_appearance("app-001", species="dasyprocta leporina")
        app_tbl, rev_tbl = self._setup_mocks(app)
        app_tbl.update_item.return_value = {
            "Attributes": {**app, "review_status": "confirmed", "species": "puma concolor"}
        }

        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            resp = client.patch(
                "/appearances/app-001/review",
                json={"action": "correct", "corrected_species": "puma concolor"},
            )

        self.assertEqual(resp.status_code, 200)
        call_kw = app_tbl.update_item.call_args[1]
        self.assertEqual(call_kw["ExpressionAttributeValues"][":rs"],  "confirmed")
        self.assertEqual(call_kw["ExpressionAttributeValues"][":sp"],  "puma concolor")

    def test_review_writes_to_reviews_table(self):
        app = _make_appearance("app-001")
        app_tbl, rev_tbl = self._setup_mocks(app)

        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            client.patch("/appearances/app-001/review", json={"action": "confirm"})

        rev_tbl.put_item.assert_called_once()
        item = rev_tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"],     TENANT_ID)
        self.assertEqual(item["appearance_id"], "app-001")
        self.assertEqual(item["action"],        "confirm")
        self.assertIn("reviewed_at",  item)
        self.assertIn("reviewer_id",  item)  # #4: reviewer_id gravado para rastreabilidade

    def test_confirm_writes_reviewer_id_to_appearances(self):
        """#4: reviewer_id deve ser gravado em siab-appearances, não só em siab-reviews."""
        app = _make_appearance("app-001", review_status="pending")
        app_tbl, rev_tbl = self._setup_mocks(app)

        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            client.patch("/appearances/app-001/review", json={"action": "confirm"})

        call_kw = app_tbl.update_item.call_args[1]
        self.assertIn(":rv", call_kw["ExpressionAttributeValues"])
        self.assertTrue(call_kw["ExpressionAttributeValues"][":rv"])  # não vazio
        self.assertIn("reviewer_id = :rv", call_kw["UpdateExpression"])

    def test_not_found_returns_404(self):
        app_tbl = MagicMock()
        app_tbl.query.return_value = {"Items": []}
        rev_tbl = MagicMock()

        with patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._reviews_table",     return_value=rev_tbl):
            resp = client.patch(
                "/appearances/nao-existe/review",
                json={"action": "confirm"},
            )

        self.assertEqual(resp.status_code, 404)

    def test_invalid_action_returns_422(self):
        resp = client.patch(
            "/appearances/app-001/review",
            json={"action": "delete"},
        )
        self.assertEqual(resp.status_code, 422)


# ── GET /projects/{project_id}/appearances/export ─────────────────────────────


class TestExportAppearances(unittest.TestCase):

    def _table_mock_confirmed(self, n: int = 2) -> MagicMock:
        items = [
            _make_appearance(
                f"a{i}",
                review_status="confirmed",
                ts_start=f"2025-01-11T{8+i:02d}:00:00",
                individual_count=2,
                taxonomic_path="mammalia;rodentia",
                species_score=0.9 + i * 0.01,
            )
            for i in range(n)
        ]
        m = MagicMock()
        m.query.return_value = {"Items": items}
        return m

    def test_returns_csv_content_type(self):
        tbl = self._table_mock_confirmed()
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers["content-type"])

    def test_csv_has_header_and_rows(self):
        tbl = self._table_mock_confirmed(2)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        lines = resp.text.strip().split("\n")
        self.assertGreater(len(lines), 2)  # header + 2 rows
        header = lines[0]
        self.assertIn("nome_cientifico", header)
        self.assertIn("camera",          header)
        self.assertIn("n_individuos",    header)
        self.assertIn("periodo",         header)

    def test_csv_excludes_pending_appearances(self):
        items = [
            _make_appearance("a1", review_status="confirmed"),
            _make_appearance("a2", review_status="pending"),
        ]
        tbl = MagicMock()
        tbl.query.return_value = {"Items": items}

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        lines = [l for l in resp.text.strip().split("\n") if l]
        self.assertEqual(len(lines), 2)  # header + 1 confirmed row

    def test_csv_period_derived_from_ts_start(self):
        items = [
            _make_appearance("a1", review_status="confirmed",
                             ts_start="2025-01-11T06:00:00"),  # Amanhecer
            _make_appearance("a2", review_status="confirmed",
                             ts_start="2025-01-11T22:00:00"),  # Noturno
        ]
        tbl = MagicMock()
        tbl.query.return_value = {"Items": items}

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        body = resp.text
        self.assertIn("Amanhecer", body)
        self.assertIn("Noturno",   body)

    def test_csv_fauna_group_from_taxonomic_path(self):
        items = [
            _make_appearance("a1", review_status="confirmed",
                             taxonomic_path="mammalia;rodentia"),
            _make_appearance("a2", review_status="confirmed",
                             taxonomic_path="aves;passeriformes"),
        ]
        tbl = MagicMock()
        tbl.query.return_value = {"Items": items}

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        body = resp.text
        self.assertIn("Mamífero", body)
        self.assertIn("Ave",      body)

    def test_csv_empty_project_has_only_header(self):
        tbl = MagicMock()
        tbl.query.return_value = {"Items": []}

        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        lines = [l for l in resp.text.strip().split("\n") if l]
        self.assertEqual(len(lines), 1)  # só o header

    def test_csv_attachment_filename(self):
        tbl = self._table_mock_confirmed(1)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/appearances/export")

        cd = resp.headers.get("content-disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn("siab_proj-001", cd)


class TestRoleAuth(unittest.TestCase):
    """Testa get_current_role() e require_role() sem adicionar endpoints permanentes."""

    # ── JWT helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _jwt(role: str) -> str:
        """JWT RS256 real assinado com a chave de teste em conftest.py."""
        return f"Bearer {_make_test_jwt(role=role)}"

    # ── Testes de get_current_role ────────────────────────────────────────────

    def test_get_current_role_analyst(self):
        role = get_current_role(authorization=self._jwt("analyst"))
        self.assertEqual(role, "analyst")

    def test_get_current_role_admin(self):
        role = get_current_role(authorization=self._jwt("admin"))
        self.assertEqual(role, "admin")

    def test_no_auth_header_raises_401(self):
        """Sem Authorization header → HTTPException 401 com JWT_VALIDATION=on."""
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            get_current_role(authorization=None)
        self.assertEqual(cm.exception.status_code, 401)

    # ── Testes de require_role via rota temporária ────────────────────────────

    @classmethod
    def setUpClass(cls):
        """Adiciona uma rota de teste que requer papel 'admin'. Removida em tearDownClass."""
        from fastapi import Depends

        @app.get("/_test/admin-only")
        def _admin_only(_role: str = Depends(require_role("admin"))):
            return {"ok": True}

        # Força o TestClient a reconhecer a nova rota
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Remove a rota temporária para não poluir outros testes."""
        app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != "/_test/admin-only"]

    def test_analyst_receives_403(self):
        resp = self.client.get("/_test/admin-only", headers={"Authorization": self._jwt("analyst")})
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Permissão insuficiente", resp.json()["detail"])

    def test_approver_receives_403_when_only_admin_allowed(self):
        resp = self.client.get("/_test/admin-only", headers={"Authorization": self._jwt("approver")})
        self.assertEqual(resp.status_code, 403)

    def test_admin_receives_200(self):
        resp = self.client.get("/_test/admin-only", headers={"Authorization": self._jwt("admin")})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})

    def test_no_auth_returns_401(self):
        """Sem Authorization header → 401 em rota protegida (JWT_VALIDATION=on)."""
        resp = self.client.get("/_test/admin-only")
        self.assertEqual(resp.status_code, 401)

    def test_require_role_multi_allowed(self):
        """require_role aceita múltiplos papéis — approver deve passar em rota approver|admin."""
        from fastapi import Depends

        @app.get("/_test/approver-or-admin")
        def _approver_or_admin(_role: str = Depends(require_role("approver", "admin"))):
            return {"ok": True}

        c = TestClient(app)
        self.assertEqual(c.get("/_test/approver-or-admin", headers={"Authorization": self._jwt("approver")}).status_code, 200)
        self.assertEqual(c.get("/_test/approver-or-admin", headers={"Authorization": self._jwt("admin")}).status_code, 200)
        self.assertEqual(c.get("/_test/approver-or-admin", headers={"Authorization": self._jwt("analyst")}).status_code, 403)

        # Limpa rota temporária
        app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != "/_test/approver-or-admin"]


# ── POST/GET/PATCH /projects/{project_id}/cameras ────────────────────────────


class TestCameras(unittest.TestCase):

    def _cam_mock(self, existing_item: dict | None = None) -> MagicMock:
        m = MagicMock()
        exc_class = type("ConditionalCheckFailedException", (Exception,), {})
        m.meta.client.exceptions.ConditionalCheckFailedException = exc_class
        m.put_item.return_value = {}
        m.get_item.return_value = {"Item": existing_item} if existing_item else {}
        m.query.return_value = {"Items": [existing_item] if existing_item else []}
        return m

    def _camera_item(self, camera_id: str = "CAM001") -> dict:
        return {
            "tenant_id":            TENANT_ID,
            "project_id#camera_id": f"proj-001#{camera_id}",
            "project_id":           "proj-001",
            "camera_id":            camera_id,
            "name":                 "Trilha Norte",
            "created_at":           "2025-01-01T00:00:00",
        }

    def test_create_returns_201_with_camera_fields(self):
        tbl = self._cam_mock()
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.post(
                "/projects/proj-001/cameras",
                json={"camera_id": "CAM001", "name": "Trilha Norte"},
            )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["camera_id"], "CAM001")
        self.assertEqual(body["project_id"], "proj-001")
        tbl.put_item.assert_called_once()

    def test_create_with_coordinates_stores_lat_lon(self):
        tbl = self._cam_mock()
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.post(
                "/projects/proj-001/cameras",
                json={"camera_id": "CAM002", "latitude": -3.4, "longitude": -60.1},
            )
        self.assertEqual(resp.status_code, 201)
        item = tbl.put_item.call_args[1]["Item"]
        self.assertIn("latitude", item)
        self.assertIn("longitude", item)

    def test_create_409_on_duplicate(self):
        tbl = self._cam_mock()
        exc_class = tbl.meta.client.exceptions.ConditionalCheckFailedException
        tbl.put_item.side_effect = exc_class("duplicate")
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.post(
                "/projects/proj-001/cameras",
                json={"camera_id": "CAM001"},
            )
        self.assertEqual(resp.status_code, 409)

    def test_list_returns_cameras_for_project(self):
        items = [self._camera_item("CAM001"), self._camera_item("CAM002")]
        tbl = self._cam_mock()
        tbl.query.return_value = {"Items": items}
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.get("/projects/proj-001/cameras")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["items"]), 2)

    def test_list_empty_project_returns_empty(self):
        tbl = self._cam_mock()
        tbl.query.return_value = {"Items": []}
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.get("/projects/proj-001/cameras")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_update_name_returns_updated_item(self):
        existing = self._camera_item()
        updated  = {**existing, "name": "Trilha Sul"}
        tbl = self._cam_mock(existing_item=existing)
        tbl.update_item.return_value = {"Attributes": updated}
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/CAM001",
                json={"name": "Trilha Sul"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Trilha Sul")

    def test_update_not_found_returns_404(self):
        tbl = self._cam_mock(existing_item=None)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/NONEXISTENT",
                json={"name": "X"},
            )
        self.assertEqual(resp.status_code, 404)

    def test_update_no_fields_returns_422(self):
        existing = self._camera_item()
        tbl = self._cam_mock(existing_item=existing)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/CAM001",
                json={},
            )
        self.assertEqual(resp.status_code, 422)


# ── PATCH /frames/annotation ─────────────────────────────────────────────────


class TestAnnotateFrame(unittest.TestCase):

    def _app_item_for_frame(self, video_id: str = "vid-001", appearance_id: str = "app-001") -> dict:
        return {
            "tenant_id":           TENANT_ID,
            "appearance_id":       appearance_id,
            "video_id#appearance_id": f"{video_id}#{appearance_id}",
            "frame_start":         1,
            "frame_end":           10,
        }

    def test_writes_annotation_to_table(self):
        ann_tbl = MagicMock()
        ann_tbl.put_item.return_value = {}
        app_item = self._app_item_for_frame()

        with patch("backend.api._appearances_for_frame", return_value=[app_item]), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._check_discrepancy"):
            resp = client.patch(
                "/frames/annotation",
                json={
                    "video_id":          "vid-001",
                    "frame_path":        "vid-001/frame_00003.jpg",
                    "annotated_species": "dasyprocta leporina",
                    "annotation_source": "chip_select",
                },
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["appearances_updated"], 1)
        ann_tbl.put_item.assert_called_once()
        item = ann_tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["annotated_species"], "dasyprocta leporina")
        self.assertEqual(item["annotation_source"], "chip_select")
        self.assertEqual(item["frame_idx"], 3)

    def test_no_matching_appearance_returns_no_appearance(self):
        with patch("backend.api._appearances_for_frame", return_value=[]):
            resp = client.patch(
                "/frames/annotation",
                json={
                    "video_id":          "vid-001",
                    "frame_path":        "vid-001/frame_00099.jpg",
                    "annotated_species": "dasyprocta leporina",
                    "annotation_source": "ai_confirm",
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "no_appearance")

    def test_invalid_annotation_source_returns_422(self):
        resp = client.patch(
            "/frames/annotation",
            json={
                "video_id":          "vid-001",
                "frame_path":        "vid-001/frame_00001.jpg",
                "annotated_species": "unknown",
                "annotation_source": "invalid_value",
            },
        )
        self.assertEqual(resp.status_code, 422)


# ── GET /appearances/{appearance_id}/frame-annotations ────────────────────────


class TestGetFrameAnnotations(unittest.TestCase):

    def _ann_item(self, appearance_id: str, frame_idx: int, species: str = "dasyprocta leporina") -> dict:
        return {
            "tenant_id":              TENANT_ID,
            "appearance_id#frame_idx": f"{appearance_id}#{frame_idx:05d}",
            "appearance_id":          appearance_id,
            "frame_path":             f"vid-001/frame_{frame_idx:05d}.jpg",
            "frame_s3_key":           f"{TENANT_ID}/frames/vid-001/frame_{frame_idx:05d}.jpg",
            "frame_idx":              frame_idx,
            "annotated_species":      species,
            "annotation_source":      "chip_select",
            "annotated_at":           "2025-01-11T08:14:30",
        }

    def test_returns_annotations_sorted_by_frame_idx(self):
        appearance = _make_appearance("app-001", ts_start="2025-01-11T08:14:30")
        appearance["frame_start"] = 1
        appearance["frame_end"]   = 10
        app_tbl = MagicMock()
        ann_items = [self._ann_item("app-001", 5), self._ann_item("app-001", 2)]
        ann_tbl = MagicMock()
        ann_tbl.query.return_value = {"Items": ann_items}

        with patch("backend.api._find_appearance", return_value=appearance), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._appearances_table", return_value=app_tbl), \
             patch("backend.api._presigned_url", return_value="https://s3.example.com/frame.jpg"):
            resp = client.get("/appearances/app-001/frame-annotations")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 2)
        idxs = [it["frame_idx"] for it in body["items"]]
        self.assertEqual(idxs, sorted(idxs))

    def test_appearance_not_found_returns_404(self):
        app_tbl = MagicMock()
        with patch("backend.api._find_appearance", return_value=None), \
             patch("backend.api._appearances_table", return_value=app_tbl):
            resp = client.get("/appearances/nonexistent/frame-annotations")
        self.assertEqual(resp.status_code, 404)


# ── GET /projects/{project_id}/stats ─────────────────────────────────────────


class TestProjectStats(unittest.TestCase):

    def _confirmed(
        self,
        appearance_id: str = "app-001",
        species: str = "dasyprocta leporina",
        camera_id: str = "CAM001",
        ts_start: str = "2025-01-11T08:14:30",
        taxonomic_path: str = "mammalia;rodentia;dasyproctidae",
    ) -> dict:
        a = _make_appearance(
            appearance_id=appearance_id,
            species=species,
            camera_id=camera_id,
            ts_start=ts_start,
            review_status="confirmed",
            taxonomic_path=taxonomic_path,
        )
        a["ts_end"] = ts_start
        a["tenant_id#review_status"] = f"{TENANT_ID}#confirmed"
        return a

    def _tbl_mock(self, items: list[dict]) -> MagicMock:
        m = MagicMock()
        m.query.return_value = {"Items": items}
        return m

    def test_empty_project_returns_zeros(self):
        tbl = self._tbl_mock([])
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_confirmed"],  0)
        self.assertEqual(body["distinct_species"], 0)
        self.assertEqual(body["active_cameras"],   0)
        self.assertEqual(body["by_fauna_group_and_month"], [])

    def test_aggregates_totals_correctly(self):
        items = [
            self._confirmed("a1", "dasyprocta leporina",    "CAM001", "2025-01-11T08:00:00"),
            self._confirmed("a2", "crypturellus soui",      "CAM002", "2025-02-15T09:00:00",
                            taxonomic_path="aves;tinamiformes;tinamidae"),
            self._confirmed("a3", "dasyprocta leporina",    "CAM001", "2025-01-20T10:00:00"),
        ]
        tbl = self._tbl_mock(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_confirmed"],  3)
        self.assertEqual(body["distinct_species"], 2)
        self.assertEqual(body["active_cameras"],   2)

    def test_by_camera_sorted_by_total_desc(self):
        items = [
            self._confirmed("a1", camera_id="CAM001"),
            self._confirmed("a2", camera_id="CAM001"),
            self._confirmed("a3", camera_id="CAM002"),
        ]
        tbl = self._tbl_mock(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        by_cam = resp.json()["by_camera"]
        self.assertEqual(by_cam[0]["camera_id"], "CAM001")
        self.assertEqual(by_cam[0]["total"], 2)
        self.assertEqual(by_cam[1]["camera_id"], "CAM002")

    def test_fauna_group_mastofauna_and_avifauna_grouped_by_month(self):
        items = [
            self._confirmed("a1", "dasyprocta leporina", ts_start="2025-01-11T08:00:00",
                            taxonomic_path="mammalia;rodentia;dasyproctidae"),
            self._confirmed("a2", "crypturellus soui",  ts_start="2025-01-15T09:00:00",
                            taxonomic_path="aves;tinamiformes;tinamidae"),
        ]
        tbl = self._tbl_mock(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        month_data = resp.json()["by_fauna_group_and_month"]
        self.assertEqual(len(month_data), 1)
        self.assertEqual(month_data[0]["month"], "2025-01")
        self.assertEqual(month_data[0]["mastofauna"], 1)
        self.assertEqual(month_data[0]["avifauna"],   1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
