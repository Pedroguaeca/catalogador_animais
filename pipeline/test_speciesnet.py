"""
pipeline/test_speciesnet.py — Unit tests para speciesnet.py e speciesnet_handler.py

Usa mocks completos para S3, SpeciesNet e DynamoDB — sem chamadas à AWS ou à rede.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

from pipeline.megadetector import Detection
from pipeline.speciesnet import (
    Classification,
    _parse_label,
    classify_species,
)
from pipeline.speciesnet_handler import (
    _frame_index,
    _group_to_appearance,
    _write_appearance,
    gap_track,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_det(frame_num: int, tenant="t1", video="v1", conf=0.8):
    key = f"{tenant}/frames/{video}/frame_{frame_num:05d}.jpg"
    return Detection(
        frame_s3_key=key, confidence=conf, bbox=(0.1, 0.2, 0.3, 0.4), category="animal"
    )


def make_cls(frame_num: int, species="dasyprocta leporina", score=0.9, tenant="t1", video="v1"):
    return Classification(
        appearance_id=str(uuid.uuid4()),
        frame_s3_key=f"{tenant}/frames/{video}/frame_{frame_num:05d}.jpg",
        species=species,
        species_score=score,
        taxonomic_level="species",
        taxonomic_path="mammalia;rodentia;dasyproctidae;dasyprocta",
        camera_id=None,
        bbox=(0.1, 0.2, 0.3, 0.4),
        model_version="speciesnet-v5.0.5",
    )


# ── _parse_label ──────────────────────────────────────────────────────────────


class TestParseLabel:
    def test_full_species_label(self):
        label = "abc;mammalia;rodentia;dasyproctidae;dasyprocta;leporina;agouti"
        name, level, path = _parse_label(label)
        assert name == "dasyprocta leporina"
        assert level == "species"
        assert path == "mammalia;rodentia;dasyproctidae;dasyprocta"

    def test_genus_only(self):
        label = "abc;mammalia;carnivora;felidae;panthera;;big-cat"
        name, level, path = _parse_label(label)
        assert name == "panthera"
        assert level == "genus"
        assert "felidae" in path

    def test_family_only(self):
        label = "abc;mammalia;carnivora;felidae;;;cat-family"
        name, level, _ = _parse_label(label)
        assert name == "felidae"
        assert level == "family"

    def test_blank_label(self):
        label = "f1856211-cfb7-4a5b-9158-c0f72fd09ee6;;;;;;blank"
        name, level, path = _parse_label(label)
        assert name == "blank"
        assert level == "blank"
        assert path == ""

    def test_animal_label(self):
        label = "1f689929-883d-4dae-958c-3d57ab5b6c16;;;;;;animal"
        name, level, _ = _parse_label(label)
        assert name == "animal"
        assert level == "animal"

    def test_human_label(self):
        label = "990ae9dd-7a59-4344-afcb-1b7b21368000;mammalia;primates;hominidae;homo;sapiens;human"
        name, level, path = _parse_label(label)
        assert name == "homo sapiens"
        assert level == "species"

    def test_vehicle_label(self):
        label = "e2895ed5-780b-48f6-8a11-9e27cb594511;;;;;;vehicle"
        name, level, _ = _parse_label(label)
        assert name == "vehicle"
        assert level == "vehicle"

    def test_unknown_no_cv_result(self):
        label = "f2efdae9;no cv result;no cv result;no cv result;no cv result;no cv result;no cv result"
        name, level, _ = _parse_label(label)
        assert name == "unknown"
        assert level == "unknown"

    def test_malformed_short_label(self):
        name, level, path = _parse_label("only_one_part")
        assert name == "unknown"
        assert level == "unknown"
        assert path == ""

    def test_empty_genus_uses_species_alone(self):
        label = "abc;mammalia;rodentia;dasyproctidae;;leporina;agouti"
        name, level, _ = _parse_label(label)
        assert name == "leporina"
        assert level == "species"


# ── classify_species ──────────────────────────────────────────────────────────


class TestClassifySpecies:
    """Testa classify_species com SpeciesNet e S3 mockados."""

    def _mock_classify_fn(self, label="abc;mammalia;rodentia;dasyproctidae;dasyprocta;leporina;agouti", score=0.9):
        """Retorna um side_effect para model.classify que usa os filepaths reais."""

        def _classify(filepaths, detections_dict, run_mode="multi_thread", **kwargs):
            return {
                "predictions": [
                    {
                        "filepath": fp,
                        "classifications": {
                            "classes": [label],
                            "scores": [score],
                        },
                        "model_version": "speciesnet-v5.0.5",
                    }
                    for fp in filepaths
                ]
            }

        return _classify

    def test_returns_one_classification_per_detection(self, tmp_path):
        dets = [make_det(1), make_det(2)]

        def fake_download(bucket, key, local_path):
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.side_effect = self._mock_classify_fn()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        assert len(result) == 2
        assert all(isinstance(r, Classification) for r in result)

    def test_parsed_species_name(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.side_effect = self._mock_classify_fn(
            label="abc;mammalia;rodentia;dasyproctidae;dasyprocta;leporina;agouti",
            score=0.87,
        )

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        assert result[0].species == "dasyprocta leporina"
        assert result[0].species_score == pytest.approx(0.87)
        assert result[0].taxonomic_level == "species"

    def test_empty_detections_returns_empty(self):
        result = classify_species([], "t1")
        assert result == []

    def test_s3_failure_skips_frame(self, tmp_path):
        dets = [make_det(1), make_det(2)]

        def fake_download(bucket, key, local_path):
            if "frame_00001" in key:
                raise ClientError({"Error": {"Code": "NoSuchKey", "Message": ""}}, "GetObject")
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.side_effect = self._mock_classify_fn(score=0.7)

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        # Só frame 2 baixou → só 1 classificação
        assert len(result) == 1
        assert "frame_00002" in result[0].frame_s3_key

    def test_speciesnet_failure_skips_frame(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.return_value = {
            "predictions": [{"filepath": "irrelevant", "failures": ["CLASSIFIER"]}]
        }

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        assert result == []

    def test_deduplicates_frames_for_classifier(self, tmp_path):
        # Duas detecções no mesmo frame (dois animais) → classify chamado com 1 filepath
        dets = [make_det(1), make_det(1)]

        def fake_download(bucket, key, local_path):
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.side_effect = self._mock_classify_fn()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        # classify chamado com 1 filepath único
        called_fps = mock_model.classify.call_args[1]["filepaths"]
        assert len(called_fps) == 1
        # mas ambas as detecções recebem resultado
        assert len(result) == 2

    def test_bbox_passed_as_detection_hint(self, tmp_path):
        dets = [make_det(1)]
        dets[0] = Detection(
            frame_s3_key=dets[0].frame_s3_key,
            confidence=0.8,
            bbox=(0.2, 0.3, 0.5, 0.4),
            category="animal",
        )

        def fake_download(bucket, key, local_path):
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.side_effect = self._mock_classify_fn()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            classify_species(dets, "t1")

        det_dict = mock_model.classify.call_args[1]["detections_dict"]
        first_path = list(det_dict.keys())[0]
        bbox_sent = det_dict[first_path]["detections"][0]["bbox"]
        assert bbox_sent == [0.2, 0.3, 0.5, 0.4]

    def test_appearance_id_is_valid_uuid(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            open(local_path, "wb").close()

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classify.side_effect = self._mock_classify_fn()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        uuid.UUID(result[0].appearance_id)  # lança ValueError se inválido


# ── _frame_index ──────────────────────────────────────────────────────────────


class TestFrameIndex:
    def test_standard_key(self):
        assert _frame_index("t/frames/v/frame_00003.jpg") == 3

    def test_large_index(self):
        assert _frame_index("t/frames/v/frame_00123.jpg") == 123

    def test_zero(self):
        assert _frame_index("tenant/frames/vid/frame_00000.jpg") == 0

    def test_first_frame(self):
        assert _frame_index("t1/frames/v1/frame_00001.jpg") == 1


# ── gap_track ─────────────────────────────────────────────────────────────────


class TestGapTrack:
    def test_consecutive_frames_one_appearance(self):
        clss = [make_cls(i) for i in range(1, 6)]
        apps = gap_track(clss, gap_frames=15)
        assert len(apps) == 1
        assert apps[0]["frame_start"] == 1
        assert apps[0]["frame_end"] == 5
        assert apps[0]["support_frames"] == 5

    def test_gap_creates_two_appearances(self):
        clss = [make_cls(i) for i in [1, 2, 3]] + [make_cls(i) for i in [25, 26, 27]]
        apps = gap_track(clss, gap_frames=15)
        assert len(apps) == 2
        starts = sorted(a["frame_start"] for a in apps)
        assert starts == [1, 25]

    def test_exactly_at_gap_boundary_stays_one(self):
        # frame 1 e frame 16 com gap=15: diferença = 15 → mesmo grupo
        clss = [make_cls(1), make_cls(16)]
        apps = gap_track(clss, gap_frames=15)
        assert len(apps) == 1

    def test_one_over_gap_creates_two(self):
        # diferença = 16 → gap > 15 → dois grupos
        clss = [make_cls(1), make_cls(17)]
        apps = gap_track(clss, gap_frames=15)
        assert len(apps) == 2

    def test_two_species_independent_groups(self):
        clss = [make_cls(i, species="dasyprocta leporina") for i in [1, 2, 3]]
        clss += [make_cls(i, species="hydrochoerus hydrochaeris") for i in [4, 5, 6]]
        apps = gap_track(clss, gap_frames=15)
        assert len(apps) == 2
        found = {a["species"] for a in apps}
        assert "dasyprocta leporina" in found
        assert "hydrochoerus hydrochaeris" in found

    def test_two_species_two_appearances_each(self):
        sp1 = [make_cls(i, species="dasyprocta leporina") for i in [1, 2, 30, 31]]
        sp2 = [make_cls(i, species="hydrochoerus hydrochaeris") for i in [10, 11, 50, 51]]
        apps = gap_track(sp1 + sp2, gap_frames=15)
        assert len(apps) == 4

    def test_picks_best_crop_by_score(self):
        clss = [
            make_cls(1, score=0.5),
            make_cls(2, score=0.95),
            make_cls(3, score=0.7),
        ]
        apps = gap_track(clss, gap_frames=15)
        assert len(apps) == 1
        assert "frame_00002" in apps[0]["best_crop_s3_key"]
        assert apps[0]["species_score"] == pytest.approx(0.95)

    def test_empty_input_returns_empty(self):
        assert gap_track([]) == []

    def test_review_status_is_pending(self):
        apps = gap_track([make_cls(1)], gap_frames=15)
        assert apps[0]["review_status"] == "pending"

    def test_individual_count_is_one(self):
        apps = gap_track([make_cls(1)], gap_frames=15)
        assert apps[0]["individual_count"] == 1

    def test_appearance_id_is_uuid(self):
        apps = gap_track([make_cls(1)], gap_frames=15)
        uuid.UUID(apps[0]["appearance_id"])  # lança ValueError se inválido


# ── _write_appearance ─────────────────────────────────────────────────────────


class TestWriteAppearance:
    def _base_app(self, **overrides):
        app = {
            "appearance_id":    "test-app-uuid",
            "species":          "dasyprocta leporina",
            "species_score":    0.91,
            "taxonomic_level":  "species",
            "taxonomic_path":   "mammalia;rodentia;dasyproctidae;dasyprocta",
            "model_version":    "speciesnet-v5.0.5",
            "frame_start":      1,
            "frame_end":        5,
            "ts_start":         None,
            "ts_end":           None,
            "support_frames":   5,
            "best_crop_s3_key": "t1/frames/v1/frame_00002.jpg",
            "camera_id":        None,
            "bbox":             [0.1, 0.2, 0.3, 0.4],
            "individual_count": 1,
            "review_status":    "pending",
        }
        app.update(overrides)
        return app

    def test_puts_item_called_once(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        mock_table.put_item.assert_called_once()

    def test_pk_is_tenant_id(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["tenant_id"] == "t1"

    def test_sk_format(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["video_id#appearance_id"] == "v1#test-app-uuid"

    def test_gsi1_keys(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["tenant_id#project_id"] == "t1#p1"
        assert item["species#appearance_id"] == "dasyprocta leporina#test-app-uuid"

    def test_gsi2_keys(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["tenant_id#review_status"] == "t1#pending"
        assert item["project_id#appearance_id"] == "p1#test-app-uuid"

    def test_species_score_is_decimal(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(species_score=0.91234), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert isinstance(item["species_score"], Decimal)

    def test_bbox_elements_are_decimal(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert all(isinstance(v, Decimal) for v in item["bbox"])

    def test_none_fields_omitted(self):
        """ts_start, ts_end e camera_id None não devem aparecer no item DynamoDB."""
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert "ts_start" not in item
        assert "ts_end" not in item
        assert "camera_id" not in item

    def test_optional_fields_written_when_present(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(
                self._base_app(camera_id="cam-01", ts_start=0.0, ts_end=3.5),
                "t1", "p1", "v1",
            )
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["camera_id"] == "cam-01"
        assert item["ts_start"] == 0.0
        assert item["ts_end"] == 3.5

    def test_model_version_written(self):
        mock_table = MagicMock()
        with patch("pipeline.speciesnet_handler._appearances", mock_table):
            _write_appearance(self._base_app(), "t1", "p1", "v1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["model_version"] == "speciesnet-v5.0.5"
