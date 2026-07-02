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

from backend.api import app, TENANT_ID

client = TestClient(app)

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


# ── POST /projects/{project_id}/videos/upload ─────────────────────────────────


class TestUploadVideo(unittest.TestCase):

    def _mock_ocr(self, camera_id="0004", captured_at="2025-01-11T08:14:30",
                  location_source="ocr"):
        from pipeline.ocr import VideoMetadata
        return MagicMock(
            return_value=VideoMetadata(
                camera_id=camera_id,
                captured_at=captured_at,
                temperature_c=19.0,
                location_source=location_source,
            )
        )

    def _s3_mock(self):
        m = MagicMock()
        m.put_object.return_value = {}
        return m

    def _sqs_mock(self, queue_url="https://sqs.us-east-1.amazonaws.com/123/siab-videos"):
        m = MagicMock()
        m.get_queue_url.return_value  = {"QueueUrl": queue_url}
        m.send_message.return_value   = {"MessageId": "msg-abc"}
        return m

    def test_upload_returns_video_id_and_ocr_fields(self):
        s3  = self._s3_mock()
        sqs = self._sqs_mock()
        ocr = self._mock_ocr()

        with patch("backend.api._s3_client", return_value=s3), \
             patch("backend.api._sqs_client", return_value=sqs), \
             patch("backend.api.extract_video_metadata", ocr):

            resp = client.post(
                "/projects/proj-001/videos/upload",
                files={"file": ("DSCF0007.avi", b"fake-video-content", "video/x-msvideo")},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("video_id", body)
        self.assertEqual(body["camera_id"],       "0004")
        self.assertEqual(body["captured_at"],     "2025-01-11T08:14:30")
        self.assertEqual(body["location_source"], "ocr")

    def test_upload_publishes_to_sqs(self):
        s3  = self._s3_mock()
        sqs = self._sqs_mock()
        ocr = self._mock_ocr()

        with patch("backend.api._s3_client", return_value=s3), \
             patch("backend.api._sqs_client", return_value=sqs), \
             patch("backend.api.extract_video_metadata", ocr):

            resp = client.post(
                "/projects/proj-001/videos/upload",
                files={"file": ("test.avi", b"data", "video/x-msvideo")},
            )

        self.assertEqual(resp.status_code, 200)
        sqs.get_queue_url.assert_called_once_with(QueueName="siab-videos")
        sqs.send_message.assert_called_once()

        call_kwargs = sqs.send_message.call_args[1]
        msg = json.loads(call_kwargs["MessageBody"])
        self.assertEqual(msg["tenant_id"],  TENANT_ID)
        self.assertEqual(msg["project_id"], "proj-001")
        self.assertIn("video_id",     msg)
        self.assertIn("video_s3_key", msg)

    def test_upload_uses_correct_s3_key_prefix(self):
        s3  = self._s3_mock()
        sqs = self._sqs_mock()
        ocr = self._mock_ocr()

        with patch("backend.api._s3_client", return_value=s3), \
             patch("backend.api._sqs_client", return_value=sqs), \
             patch("backend.api.extract_video_metadata", ocr):

            resp = client.post(
                "/projects/proj-001/videos/upload",
                files={"file": ("vid.avi", b"x", "video/x-msvideo")},
            )

        s3_key = resp.json()["s3_key"]
        self.assertTrue(s3_key.startswith(f"{TENANT_ID}/videos/"))
        self.assertTrue(s3_key.endswith(".avi"))

    def test_upload_ocr_failure_returns_manual(self):
        """Quando o OCR falha, location_source deve ser 'manual'."""
        s3  = self._s3_mock()
        sqs = self._sqs_mock()

        with patch("backend.api._s3_client", return_value=s3), \
             patch("backend.api._sqs_client", return_value=sqs), \
             patch("backend.api.extract_video_metadata", side_effect=Exception("OCR error")):

            resp = client.post(
                "/projects/proj-001/videos/upload",
                files={"file": ("bad.avi", b"data", "video/x-msvideo")},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["location_source"], "manual")
        self.assertIsNone(resp.json()["camera_id"])


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
        self.assertIn("reviewed_at", item)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
