"""
Testes dos 6 endpoints sem cobertura anterior:
  - POST   /projects/{id}/cameras
  - GET    /projects/{id}/cameras
  - PATCH  /projects/{id}/cameras/{camera_id}
  - PATCH  /frames/annotation
  - GET    /appearances/{id}/frame-annotations
  - GET    /projects/{id}/stats

Cada classe cobre: happy path, autenticação (401 sem token / token inválido),
isolamento de tenant, casos extremos (404, 409, 422) e paginação DynamoDB.

A fixture _patch_jwt em backend/conftest.py é autouse=True — JWT_VALIDATION=True
em todos os testes sem SIAB_JWT_VALIDATION=off.
"""
from __future__ import annotations

import json
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from boto3.dynamodb.conditions import ConditionExpressionBuilder
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api import app
from backend.conftest import DEFAULT_TENANT, make_jwt

TENANT_ID = DEFAULT_TENANT

_expr_builder = ConditionExpressionBuilder()

def _condition_values(cond) -> list:
    """Extrai os valores literais de um boto3 KeyConditionExpression para assertions."""
    expr = _expr_builder.build_expression(cond)
    return list(expr.attribute_value_placeholders.values())

# ── Cliente padrão (admin do tenant de teste) ─────────────────────────────────
_TOKEN = make_jwt()
client = TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"})

# ── Cliente sem Authorization header ─────────────────────────────────────────
no_auth_client = TestClient(app)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _cam_item(
    camera_id: str = "CAM01",
    project_id: str = "proj-001",
    tenant_id: str = TENANT_ID,
    name: str | None = "Camera 1",
    lat: float | None = -23.5,
    lon: float | None = -46.6,
) -> dict:
    item: dict = {
        "tenant_id":            tenant_id,
        "project_id#camera_id": f"{project_id}#{camera_id}",
        "project_id":           project_id,
        "camera_id":            camera_id,
        "created_at":           "2025-01-11T08:00:00",
    }
    if name is not None:
        item["name"] = name
    if lat is not None:
        item["latitude"] = Decimal(str(lat))
    if lon is not None:
        item["longitude"] = Decimal(str(lon))
    return item


def _client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": code}},
        "put_item",
    )


def _tbl_mock_for_cameras(items: list[dict] | None = None) -> MagicMock:
    m = MagicMock()
    m.query.return_value  = {"Items": items or []}
    m.put_item.return_value = {}
    m.get_item.return_value = {"Item": items[0]} if items else {}
    m.update_item.return_value = {"Attributes": items[0] if items else {}}
    # para o 409: o cliente de exceptions é acessado via meta.client.exceptions
    m.meta.client.exceptions.ConditionalCheckFailedException = type(
        "ConditionalCheckFailedException", (ClientError,), {}
    )
    return m


# ══════════════════════════════════════════════════════════════════════════════
# POST /projects/{project_id}/cameras
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateCamera(unittest.TestCase):

    def test_happy_path_returns_201(self):
        tbl = _tbl_mock_for_cameras()
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.post(
                "/projects/proj-001/cameras",
                json={"camera_id": "CAM01", "name": "Trilha Norte",
                      "latitude": -23.5, "longitude": -46.6},
            )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["camera_id"],  "CAM01")
        self.assertEqual(body["project_id"], "proj-001")
        self.assertIn("created_at", body)

    def test_duplicate_returns_409(self):
        """put_item com ConditionalCheckFailedException → 409."""
        tbl = _tbl_mock_for_cameras()
        exc_cls = tbl.meta.client.exceptions.ConditionalCheckFailedException
        tbl.put_item.side_effect = exc_cls(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "put_item",
        )
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.post(
                "/projects/proj-001/cameras",
                json={"camera_id": "CAM01"},
            )
        self.assertEqual(resp.status_code, 409)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.post(
            "/projects/proj-001/cameras",
            json={"camera_id": "CAM01"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        bad_token = make_jwt(bad_signature=True)
        resp = client.post(
            "/projects/proj-001/cameras",
            json={"camera_id": "CAM01"},
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_expired_token_returns_401(self):
        expired_token = make_jwt(expired=True)
        resp = client.post(
            "/projects/proj-001/cameras",
            json={"camera_id": "CAM01"},
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_missing_camera_id_returns_422(self):
        resp = client.post(
            "/projects/proj-001/cameras",
            json={"name": "No ID"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_tenant_isolation_item_uses_jwt_tenant(self):
        """tenant_id no item criado vem do JWT, não de parâmetro externo."""
        tbl = _tbl_mock_for_cameras()
        with patch("backend.api._cameras_table", return_value=tbl):
            client.post("/projects/proj-001/cameras", json={"camera_id": "CAM01"})
        item = tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"], TENANT_ID)


# ══════════════════════════════════════════════════════════════════════════════
# GET /projects/{project_id}/cameras
# ══════════════════════════════════════════════════════════════════════════════

class TestListCameras(unittest.TestCase):

    def test_happy_path_returns_cameras(self):
        items = [_cam_item("CAM01"), _cam_item("CAM02")]
        tbl   = _tbl_mock_for_cameras(items)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.get("/projects/proj-001/cameras")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"],      2)
        self.assertEqual(body["project_id"], "proj-001")

    def test_empty_project_returns_zero(self):
        tbl = _tbl_mock_for_cameras([])
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.get("/projects/proj-001/cameras")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/projects/proj-001/cameras")
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        resp = client.get(
            "/projects/proj-001/cameras",
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_query_uses_jwt_tenant(self):
        """Query DynamoDB usa tenant_id do JWT como PK — não parâmetro externo."""
        tbl = _tbl_mock_for_cameras([])
        with patch("backend.api._cameras_table", return_value=tbl):
            client.get("/projects/proj-001/cameras")
        call_kw = tbl.query.call_args[1]
        vals = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn(TENANT_ID, vals)

    def test_tenant_isolation_other_tenant_sees_no_cameras(self):
        """Tenant B com mesmo project_id não vê câmeras do Tenant A."""
        tbl   = _tbl_mock_for_cameras([])
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.get(
                "/projects/proj-001/cameras",
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        self.assertEqual(resp.status_code, 200)
        call_kw = tbl.query.call_args[1]
        vals = _condition_values(call_kw["KeyConditionExpression"])
        self.assertNotIn(TENANT_ID, vals)
        self.assertIn("outro-tenant", vals)

    def test_pagination_follows_last_evaluated_key(self):
        """Loop de paginação segue LastEvaluatedKey até o fim."""
        page1 = [_cam_item(f"CAM{i:02d}") for i in range(3)]
        page2 = [_cam_item(f"CAM{i:02d}") for i in range(3, 5)]
        tbl   = MagicMock()
        tbl.query.side_effect = [
            {"Items": page1, "LastEvaluatedKey": {"pk": "key1"}},
            {"Items": page2},
        ]
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.get("/projects/proj-001/cameras")
        self.assertEqual(resp.json()["count"], 5)
        self.assertEqual(tbl.query.call_count, 2)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /projects/{project_id}/cameras/{camera_id}
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateCamera(unittest.TestCase):

    def _setup(self, existing: dict | None = None):
        tbl = MagicMock()
        tbl.get_item.return_value    = {"Item": existing} if existing else {}
        tbl.update_item.return_value = {"Attributes": existing or {}}
        return tbl

    def test_happy_path_updates_name(self):
        cam = _cam_item("CAM01")
        tbl = self._setup(cam)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/CAM01",
                json={"name": "Novo Nome"},
            )
        self.assertEqual(resp.status_code, 200)
        tbl.update_item.assert_called_once()

    def test_happy_path_updates_gps(self):
        cam = _cam_item("CAM01")
        tbl = self._setup(cam)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/CAM01",
                json={"latitude": -10.0, "longitude": -60.0},
            )
        self.assertEqual(resp.status_code, 200)
        expr_vals = tbl.update_item.call_args[1]["ExpressionAttributeValues"]
        self.assertIn(":lat", expr_vals)
        self.assertIn(":lon", expr_vals)

    def test_not_found_returns_404(self):
        tbl = self._setup(None)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/NAO-EXISTE",
                json={"name": "X"},
            )
        self.assertEqual(resp.status_code, 404)

    def test_empty_body_returns_422(self):
        cam = _cam_item("CAM01")
        tbl = self._setup(cam)
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/CAM01",
                json={},
            )
        self.assertEqual(resp.status_code, 422)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.patch(
            "/projects/proj-001/cameras/CAM01",
            json={"name": "X"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_get_item_uses_jwt_tenant(self):
        """get_item usa tenant_id do JWT na chave — câmera de outro tenant retorna 404."""
        tbl = self._setup(None)  # não encontra nada para o tenant do JWT
        with patch("backend.api._cameras_table", return_value=tbl):
            resp = client.patch(
                "/projects/proj-001/cameras/CAM-OUTRO-TENANT",
                json={"name": "X"},
            )
        self.assertEqual(resp.status_code, 404)
        key = tbl.get_item.call_args[1]["Key"]
        self.assertEqual(key["tenant_id"], TENANT_ID)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /frames/annotation
# ══════════════════════════════════════════════════════════════════════════════

def _make_app_item(
    appearance_id: str = "app-001",
    video_id: str = "vid-001",
    species: str = "dasyprocta leporina",
    frame_start: int = 10,
    frame_end: int = 30,
) -> dict:
    return {
        "tenant_id":               TENANT_ID,
        "appearance_id":           appearance_id,
        "video_id":                video_id,
        "video_id#appearance_id":  f"{video_id}#{appearance_id}",
        "species":                 species,
        "frame_start":             frame_start,
        "frame_end":               frame_end,
        "review_status":           "pending",
        "tenant_id#review_status": f"{TENANT_ID}#pending",
        "project_id":              "proj-001",
    }


class TestAnnotateFrame(unittest.TestCase):

    def _setup(self, appearances: list[dict] | None = None):
        ann_tbl  = MagicMock()
        ann_tbl.put_item.return_value = {}
        # _check_discrepancy queries ann_tbl for annotation items with annotated_species;
        # returning [] means no discrepancy detected → app_tbl.update_item called once with "pending"
        ann_tbl.query.return_value    = {"Items": []}
        app_tbl  = MagicMock()
        app_tbl.update_item.return_value = {}
        return ann_tbl, app_tbl

    def test_happy_path_returns_ok(self):
        app_item = _make_app_item()
        ann_tbl, app_tbl = self._setup([app_item])

        with patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._appearances_for_frame",   return_value=[app_item]):
            resp = client.patch(
                "/frames/annotation",
                json={
                    "video_id":           "vid-001",
                    "frame_path":         "vid-001_00020.jpg",
                    "annotated_species":  "dasyprocta leporina",
                    "annotation_source":  "ai_confirm",
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["appearances_updated"], 1)

    def test_no_matching_appearance_returns_no_appearance(self):
        ann_tbl, app_tbl = self._setup([])
        with patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._appearances_for_frame",   return_value=[]):
            resp = client.patch(
                "/frames/annotation",
                json={
                    "video_id":           "vid-001",
                    "frame_path":         "vid-001_00099.jpg",
                    "annotated_species":  "puma concolor",
                    "annotation_source":  "ai_confirm",
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "no_appearance")

    def test_annotation_is_persisted(self):
        """put_item chamado com os campos corretos."""
        app_item = _make_app_item()
        ann_tbl, app_tbl = self._setup([app_item])
        with patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._appearances_for_frame",   return_value=[app_item]):
            client.patch(
                "/frames/annotation",
                json={
                    "video_id":           "vid-001",
                    "frame_path":         "vid-001_00020.jpg",
                    "annotated_species":  "dasyprocta leporina",
                    "annotation_source":  "ai_confirm",
                },
            )
        ann_tbl.put_item.assert_called_once()
        item = ann_tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"],         TENANT_ID)
        self.assertEqual(item["annotated_species"],  "dasyprocta leporina")
        self.assertEqual(item["annotation_source"],  "ai_confirm")
        self.assertIn("annotated_at", item)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.patch(
            "/frames/annotation",
            json={"video_id": "v", "frame_path": "v_00001.jpg",
                  "annotated_species": "x", "annotation_source": "ai_confirm"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        resp = client.patch(
            "/frames/annotation",
            json={"video_id": "v", "frame_path": "v_00001.jpg",
                  "annotated_species": "x", "annotation_source": "ai_confirm"},
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_annotation_uses_jwt_tenant(self):
        """frame_s3_key e tenant_id no item gravado usam o tenant do JWT."""
        app_item = _make_app_item()
        ann_tbl, app_tbl = self._setup([app_item])
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        with patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._appearances_for_frame",   return_value=[app_item]):
            client.patch(
                "/frames/annotation",
                json={"video_id": "vid-001", "frame_path": "vid-001_00020.jpg",
                      "annotated_species": "puma concolor", "annotation_source": "ai_confirm"},
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        item = ann_tbl.put_item.call_args[1]["Item"]
        self.assertEqual(item["tenant_id"], "outro-tenant")
        self.assertTrue(item["frame_s3_key"].startswith("outro-tenant/frames/"))

    def test_missing_fields_returns_422(self):
        resp = client.patch("/frames/annotation", json={"video_id": "only-this"})
        self.assertEqual(resp.status_code, 422)


# ══════════════════════════════════════════════════════════════════════════════
# GET /appearances/{appearance_id}/frame-annotations
# ══════════════════════════════════════════════════════════════════════════════

class TestGetFrameAnnotations(unittest.TestCase):

    def _setup(self, app_item: dict | None, annotations: list[dict] | None = None):
        app_tbl = MagicMock()
        app_tbl.query.return_value = {"Items": [app_item] if app_item else []}
        ann_tbl = MagicMock()
        ann_tbl.query.return_value = {"Items": annotations or []}
        return app_tbl, ann_tbl

    def test_happy_path_returns_annotations(self):
        app_item = _make_app_item()
        anns = [
            {"tenant_id": TENANT_ID, "appearance_id#frame_idx": "app-001#00020",
             "appearance_id": "app-001", "frame_idx": 20,
             "annotated_species": "dasyprocta leporina", "frame_s3_key": "t/frames/f.jpg"},
        ]
        app_tbl, ann_tbl = self._setup(app_item, anns)
        with patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._presigned_url",           return_value="https://presigned"):
            resp = client.get("/appearances/app-001/frame-annotations")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"],         1)
        self.assertEqual(body["appearance_id"], "app-001")
        self.assertIn("thumbnail_url",          body["items"][0])

    def test_not_found_returns_404(self):
        app_tbl, ann_tbl = self._setup(None)
        with patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl):
            resp = client.get("/appearances/nao-existe/frame-annotations")
        self.assertEqual(resp.status_code, 404)

    def test_no_annotations_returns_empty(self):
        app_item = _make_app_item()
        app_tbl, ann_tbl = self._setup(app_item, [])
        with patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl):
            resp = client.get("/appearances/app-001/frame-annotations")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_annotations_sorted_by_frame_idx(self):
        app_item = _make_app_item()
        anns = [
            {"tenant_id": TENANT_ID, "appearance_id#frame_idx": "app-001#00030",
             "appearance_id": "app-001", "frame_idx": 30, "frame_s3_key": "k"},
            {"tenant_id": TENANT_ID, "appearance_id#frame_idx": "app-001#00010",
             "appearance_id": "app-001", "frame_idx": 10, "frame_s3_key": "k"},
        ]
        app_tbl, ann_tbl = self._setup(app_item, anns)
        with patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl), \
             patch("backend.api._presigned_url",           return_value=None):
            resp = client.get("/appearances/app-001/frame-annotations")
        idxs = [i["frame_idx"] for i in resp.json()["items"]]
        self.assertEqual(idxs, sorted(idxs))

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/appearances/app-001/frame-annotations")
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_query_uses_jwt_tenant(self):
        """Query em _find_appearance usa tenant_id do JWT, não de parâmetro externo."""
        app_tbl, ann_tbl = self._setup(None)
        tenant_b_token = make_jwt(tenant_id="outro-tenant")
        with patch("backend.api._appearances_table",       return_value=app_tbl), \
             patch("backend.api._frame_annotations_table", return_value=ann_tbl):
            resp = client.get(
                "/appearances/app-001/frame-annotations",
                headers={"Authorization": f"Bearer {tenant_b_token}"},
            )
        # _find_appearance retorna None para "outro-tenant" → 404
        self.assertEqual(resp.status_code, 404)
        call_kw = app_tbl.query.call_args[1]
        vals = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn("outro-tenant", vals)
        self.assertNotIn(TENANT_ID, vals)


# ══════════════════════════════════════════════════════════════════════════════
# GET /projects/{project_id}/stats
# ══════════════════════════════════════════════════════════════════════════════

def _make_confirmed_appearance(
    appearance_id: str = "app-001",
    species: str = "dasyprocta leporina",
    camera_id: str = "CAM01",
    ts_start: str = "2025-01-11T08:00:00",
    ts_end: str   = "2025-01-11T08:01:00",
    taxonomic_path: str = "mammalia;rodentia;dasyproctidae",
) -> dict:
    return {
        "tenant_id":                f"{TENANT_ID}",
        "tenant_id#review_status":  f"{TENANT_ID}#confirmed",
        "project_id#appearance_id": f"proj-001#{appearance_id}",
        "project_id":               "proj-001",
        "appearance_id":            appearance_id,
        "species":                  species,
        "camera_id":                camera_id,
        "ts_start":                 ts_start,
        "ts_end":                   ts_end,
        "taxonomic_path":           taxonomic_path,
        "review_status":            "confirmed",
        "support_frames":           3,
        "individual_count":         1,
    }


class TestGetProjectStats(unittest.TestCase):

    def _tbl(self, items: list[dict]) -> MagicMock:
        m = MagicMock()
        m.query.return_value = {"Items": items}
        return m

    def test_happy_path_returns_stats(self):
        items = [
            _make_confirmed_appearance("a1", species="dasyprocta leporina", camera_id="CAM01"),
            _make_confirmed_appearance("a2", species="puma concolor",       camera_id="CAM02"),
        ]
        tbl = self._tbl(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_confirmed"],  2)
        self.assertEqual(body["distinct_species"], 2)
        self.assertEqual(body["active_cameras"],   2)
        self.assertIsNotNone(body["period_start"])
        self.assertIsNotNone(body["period_end"])

    def test_empty_project_returns_zeros(self):
        tbl = self._tbl([])
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_confirmed"],  0)
        self.assertEqual(body["distinct_species"], 0)
        self.assertEqual(body["active_cameras"],   0)
        self.assertIsNone(body["period_start"])

    def test_by_fauna_group_aggregation(self):
        items = [
            _make_confirmed_appearance("a1", taxonomic_path="mammalia;rodentia",
                                       ts_start="2025-01-11T08:00:00"),
            _make_confirmed_appearance("a2", taxonomic_path="aves;passeriformes",
                                       ts_start="2025-01-11T10:00:00"),
        ]
        tbl = self._tbl(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        by_month = resp.json()["by_fauna_group_and_month"]
        self.assertEqual(len(by_month), 1)  # mesmo mês (2025-01)
        row = by_month[0]
        self.assertEqual(row["mastofauna"], 1)
        self.assertEqual(row["avifauna"],   1)

    def test_by_camera_aggregation(self):
        items = [
            _make_confirmed_appearance("a1", camera_id="CAM01"),
            _make_confirmed_appearance("a2", camera_id="CAM01"),
            _make_confirmed_appearance("a3", camera_id="CAM02"),
        ]
        tbl = self._tbl(items)
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        by_cam = resp.json()["by_camera"]
        cam_totals = {c["camera_id"]: c["total"] for c in by_cam}
        self.assertEqual(cam_totals["CAM01"], 2)
        self.assertEqual(cam_totals["CAM02"], 1)

    def test_no_auth_returns_401(self):
        resp = no_auth_client.get("/projects/proj-001/stats")
        self.assertEqual(resp.status_code, 401)

    def test_bad_token_returns_401(self):
        resp = client.get(
            "/projects/proj-001/stats",
            headers={"Authorization": f"Bearer {make_jwt(bad_signature=True)}"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_tenant_isolation_gsi_pk_uses_jwt_tenant(self):
        """GSI by-review-status usa PK 'tenant_id#confirmed' do JWT."""
        tbl = self._tbl([])
        with patch("backend.api._appearances_table", return_value=tbl):
            client.get("/projects/proj-001/stats")
        call_kw = tbl.query.call_args[1]
        vals = _condition_values(call_kw["KeyConditionExpression"])
        self.assertIn(f"{TENANT_ID}#confirmed", vals)

    def test_pagination_follows_last_evaluated_key(self):
        page1 = [_make_confirmed_appearance(f"a{i}") for i in range(3)]
        page2 = [_make_confirmed_appearance(f"a{i}") for i in range(3, 5)]
        tbl   = MagicMock()
        tbl.query.side_effect = [
            {"Items": page1, "LastEvaluatedKey": {"pk": "key1"}},
            {"Items": page2},
        ]
        with patch("backend.api._appearances_table", return_value=tbl):
            resp = client.get("/projects/proj-001/stats")
        self.assertEqual(resp.json()["total_confirmed"], 5)
        self.assertEqual(tbl.query.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
