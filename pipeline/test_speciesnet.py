"""
pipeline/test_speciesnet.py — Unit tests para speciesnet.py e speciesnet_handler.py

Usa mocks completos para S3, SpeciesNet e DynamoDB — sem chamadas à AWS ou à rede.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import PIL.Image
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
    _write_frame_annotations,
    gap_track,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_dummy_jpeg(path: str) -> None:
    """Escreve um JPEG mínimo válido — PIL.Image.open() precisa de bytes reais."""
    PIL.Image.new("RGB", (10, 10), color=(120, 120, 120)).save(path, format="JPEG")


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
    """Testa classify_species com SpeciesNet e S3 mockados.

    O pipeline chama model.classifier.preprocess()/predict() por detecção
    (não o model.classify() em lote) para evitar SemLock no Lambda — ver
    comentário em speciesnet.py:255. Os mocks abaixo refletem essa API real.
    """

    def _mock_model(self, label="abc;mammalia;rodentia;dasyproctidae;dasyprocta;leporina;agouti", score=0.9):
        """Retorna um MagicMock de SpeciesNet com .classifier.preprocess/predict mockados."""
        mock_model = MagicMock()
        mock_model.classifier.preprocess.return_value = "preprocessed"
        mock_model.classifier.predict.return_value = {
            "classifications": {"classes": [label], "scores": [score]},
            "model_version": "speciesnet-v5.0.5",
        }
        return mock_model

    def test_returns_one_classification_per_detection(self, tmp_path):
        dets = [make_det(1), make_det(2)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        assert len(result) == 2
        assert all(isinstance(r, Classification) for r in result)

    def test_parsed_species_name(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model(
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
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model(score=0.7)

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        # Só frame 2 baixou → só 1 classificação
        assert len(result) == 1
        assert "frame_00002" in result[0].frame_s3_key

    def test_speciesnet_failure_skips_frame(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = MagicMock()
        mock_model.classifier.preprocess.return_value = "preprocessed"
        mock_model.classifier.predict.return_value = {"failures": ["CLASSIFIER"]}

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        assert result == []

    def test_deduplicates_frames_for_classifier(self, tmp_path):
        # Duas detecções no mesmo frame (dois animais) → download/classificação 1x
        dets = [make_det(1), make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        # download_file chamado 1x só (frame único)
        assert mock_s3.download_file.call_count == 1
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
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            classify_species(dets, "t1")

        bboxes_sent = mock_model.classifier.preprocess.call_args[1]["bboxes"]
        assert (bboxes_sent[0].xmin, bboxes_sent[0].ymin, bboxes_sent[0].width, bboxes_sent[0].height) == (
            0.2, 0.3, 0.5, 0.4,
        )

    def test_appearance_id_is_valid_uuid(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1")

        uuid.UUID(result[0].appearance_id)  # lança ValueError se inválido


# ── classify_species + geofence (country) ──────────────────────────────────────


class TestClassifySpeciesGeofence:
    """Testa a integração com geofence_animal_classification quando country é passado."""

    DIDELPHIS_VIRGINIANA = (
        "uuid1;mammalia;didelphimorphia;didelphidae;didelphis;virginiana;virginia opossum"
    )
    DIDELPHIS_FAMILY_ROLLUP = (
        "uuid2;mammalia;didelphimorphia;didelphidae;;;possum family"
    )

    def _mock_ensemble(self):
        """Ensemble fake com taxonomy_map/geofence_map mínimos pro rollup de família."""
        mock_ensemble = MagicMock()
        mock_ensemble.taxonomy_map = {
            "mammalia;didelphimorphia;didelphidae;;": self.DIDELPHIS_FAMILY_ROLLUP,
        }
        mock_ensemble.geofence_map = {
            # BRA não está no allow-list -> geofenced quando country="BRA"
            "mammalia;didelphimorphia;didelphidae;didelphis;virginiana": {
                "allow": {"USA": []}
            },
        }
        return mock_ensemble

    def _mock_model(self, labels, scores):
        mock_model = MagicMock()
        mock_model.classifier.preprocess.return_value = "preprocessed"
        mock_model.classifier.predict.return_value = {
            "classifications": {"classes": labels, "scores": scores},
            "model_version": "speciesnet-v5.0.5",
        }
        return mock_model

    def test_geofenced_species_rolls_up_to_family(self, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model([self.DIDELPHIS_VIRGINIANA], [0.95])
        mock_ensemble = self._mock_ensemble()

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet._get_ensemble", return_value=mock_ensemble) as get_ensemble, \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1", country="BRA")

        get_ensemble.assert_called_once()
        assert result[0].species == "didelphidae"
        assert result[0].taxonomic_level == "family"

    def test_non_geofenced_species_passes_through(self, tmp_path):
        """Espécie fora do geofence_map (ex: fauna já plausível pro BR) não é alterada."""
        dets = [make_det(1)]
        label = "abc;mammalia;rodentia;dasyproctidae;dasyprocta;leporina;agouti"

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model([label], [0.9])
        mock_ensemble = self._mock_ensemble()  # não tem entrada de geofence pra essa espécie

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet._get_ensemble", return_value=mock_ensemble), \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1", country="BRA")

        assert result[0].species == "dasyprocta leporina"
        assert result[0].species_score == pytest.approx(0.9)

    def test_no_country_skips_geofence_entirely(self, tmp_path):
        """Sem country, nem carrega o ensemble — comportamento idêntico ao anterior."""
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model([self.DIDELPHIS_VIRGINIANA], [0.95])

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet._get_ensemble") as get_ensemble, \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1", country=None)

        get_ensemble.assert_not_called()
        assert result[0].species == "didelphis virginiana"


class TestClassifySpeciesGbifAllowlist:
    """Entrega (b) do geofencing (SIAB-187): camada GBIF depois do geofence
    embutido. Só sinaliza (geo_review_flag) — nunca troca species/score."""

    def _mock_model(self, label, score):
        mock_model = MagicMock()
        mock_model.classifier.preprocess.return_value = "preprocessed"
        mock_model.classifier.predict.return_value = {
            "classifications": {"classes": [label], "scores": [score]},
            "model_version": "speciesnet-v5.0.5",
        }
        return mock_model

    def _run(self, label, score, country, allowlist, tmp_path):
        dets = [make_det(1)]

        def fake_download(bucket, key, local_path):
            _write_dummy_jpeg(local_path)

        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = fake_download
        mock_model = self._mock_model(label, score)
        mock_ensemble = MagicMock(taxonomy_map={}, geofence_map={})

        with patch("pipeline.speciesnet._get_model", return_value=mock_model), \
             patch("pipeline.speciesnet._get_ensemble", return_value=mock_ensemble), \
             patch("pipeline.speciesnet._get_gbif_allowlist", return_value=allowlist) as get_allowlist, \
             patch("pipeline.speciesnet.boto3.client", return_value=mock_s3):
            result = classify_species(dets, "t1", country=country)
        return result, get_allowlist

    # penelope purpurascens: caso real que motivou a task — geofence embutido
    # do Google marca como permitido no BR, GBIF não tem registro de ocorrência.
    PENELOPE = "uuid;aves;galliformes;cracidae;penelope;purpurascens;crested guan"

    def test_species_absent_from_allowlist_gets_flagged(self, tmp_path):
        """Espécie nunca sincronizada (ausente do cache) — default seguro é flag=True."""
        result, _ = self._run(self.PENELOPE, 0.9, "BRA", allowlist={}, tmp_path=tmp_path)
        assert result[0].species == "penelope purpurascens"
        assert result[0].geo_review_flag is True

    def test_species_with_no_br_occurrence_gets_flagged(self, tmp_path):
        allowlist = {"penelope purpurascens": {"ocorre_br": False, "n_registros_gbif": 0}}
        result, _ = self._run(self.PENELOPE, 0.9, "BRA", allowlist=allowlist, tmp_path=tmp_path)
        assert result[0].geo_review_flag is True

    def test_species_with_br_occurrence_not_flagged(self, tmp_path):
        allowlist = {"penelope purpurascens": {"ocorre_br": True, "n_registros_gbif": 500}}
        result, _ = self._run(self.PENELOPE, 0.9, "BRA", allowlist=allowlist, tmp_path=tmp_path)
        assert result[0].geo_review_flag is False

    def test_species_with_br_occurrence_but_too_few_records_still_flagged(self, tmp_path):
        """Caso real (28/07): penelope purpurascens tinha ocorre_br=true no sync
        de produção, mas só 3 registros (espécimes de museu, provável erro de
        localidade) — booleano puro deixava passar o caso que motivou a task
        inteira. Limiar (GBIF_MIN_OCCURRENCE_RECORDS=10) precisa flagar mesmo
        com ocorre_br=true."""
        allowlist = {"penelope purpurascens": {"ocorre_br": True, "n_registros_gbif": 3}}
        result, _ = self._run(self.PENELOPE, 0.9, "BRA", allowlist=allowlist, tmp_path=tmp_path)
        assert result[0].geo_review_flag is True

    def test_species_with_br_occurrence_above_threshold_not_flagged(self, tmp_path):
        """Caso real (28/07): nasua nasua, 4602 registros no sync de produção —
        continua não sinalizado."""
        allowlist = {"penelope purpurascens": {"ocorre_br": True, "n_registros_gbif": 4602}}
        result, _ = self._run(self.PENELOPE, 0.9, "BRA", allowlist=allowlist, tmp_path=tmp_path)
        assert result[0].geo_review_flag is False

    def test_non_species_rollup_never_flagged(self, tmp_path):
        """Rollup pra gênero/família (já resolvido pelo geofence embutido) não
        passa pela checagem GBIF — level != "species"."""
        family_rollup = "uuid;aves;galliformes;cracidae;;;guans"
        result, get_allowlist = self._run(family_rollup, 0.9, "BRA", allowlist={}, tmp_path=tmp_path)
        assert result[0].taxonomic_level == "family"
        assert result[0].geo_review_flag is False
        get_allowlist.assert_not_called()

    def test_no_country_skips_gbif_check_entirely(self, tmp_path):
        result, get_allowlist = self._run(self.PENELOPE, 0.9, None, allowlist={}, tmp_path=tmp_path)
        assert result[0].geo_review_flag is False
        get_allowlist.assert_not_called()


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


# ── _write_frame_annotations ────────────────────────────────────────────────────


class _FakeFrameAnnotationsTable:
    """Fake mínima de siab-frame-annotations que só implementa update_item,
    reproduzindo a semântica real do DynamoDB: um SET só sobrescreve os
    atributos citados na UpdateExpression, o resto do item existente
    permanece intacto. Não usa moto (não é dependência do projeto) — só
    o suficiente pra provar que _write_frame_annotations não apaga campos
    que não está tentando atualizar.
    """

    def __init__(self):
        self.items: dict[tuple, dict] = {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues):
        pk = (Key["tenant_id"], Key["video_id#frame_idx"])
        item = self.items.setdefault(pk, dict(Key))
        assert UpdateExpression.strip().startswith("SET "), UpdateExpression
        for assignment in UpdateExpression[len("SET "):].split(","):
            attr, placeholder = (s.strip() for s in assignment.split("="))
            item[attr] = ExpressionAttributeValues[placeholder]


def make_frame_cls(species="didelphidae", score=0.99, level="family", tenant="t1", video="v1", frame_num=1, geo_review_flag=False):
    return Classification(
        appearance_id=str(uuid.uuid4()),
        frame_s3_key=f"{tenant}/frames/{video}/frame_{frame_num:05d}.jpg",
        species=species,
        species_score=score,
        taxonomic_level=level,
        taxonomic_path="mammalia;didelphimorphia;didelphidae",
        camera_id=None,
        bbox=(0.1, 0.2, 0.3, 0.4),
        model_version="speciesnet-v5.0.5",
        geo_review_flag=geo_review_flag,
    )


class TestWriteFrameAnnotations:
    """Regressão do incidente SIAB-187: reprocessar um vídeo já revisado
    (geofencing corrigido depois de um review humano) não pode apagar
    annotated_species/annotation_source/annotated_at."""

    def test_preserves_human_annotation_on_reprocess(self):
        fake_table = _FakeFrameAnnotationsTable()
        pk = ("t1", "v1#00001")
        fake_table.items[pk] = {
            "tenant_id":           "t1",
            "video_id#frame_idx":  "v1#00001",
            "video_id":            "v1",
            "frame_idx":           1,
            "frame_s3_key":        "t1/frames/v1/frame_00001.jpg",
            "ai_species":          "didelphis virginiana",  # valor errado, pré-fix de geofencing
            "ai_score":            Decimal("0.95"),
            "bbox":                [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")],
            "taxonomic_level":     "species",
            "annotated_species":   "didelphis virginiana",
            "annotation_source":   "auto",
            "annotated_at":        "2026-07-24T20:56:04+00:00",
        }

        cls = make_frame_cls(species="didelphidae", score=0.99, level="family", frame_num=1)
        with patch("pipeline.speciesnet_handler._frame_anns", fake_table):
            _write_frame_annotations([cls], tenant_id="t1", video_id="v1")

        item = fake_table.items[pk]
        # campos humanos sobrevivem intactos
        assert item["annotated_species"] == "didelphis virginiana"
        assert item["annotation_source"] == "auto"
        assert item["annotated_at"] == "2026-07-24T20:56:04+00:00"
        # campos de IA foram corrigidos pelo reprocessamento
        assert item["ai_species"] == "didelphidae"
        assert item["taxonomic_level"] == "family"
        assert item["ai_score"] == Decimal("0.99")

    def test_frame_without_prior_human_annotation_still_gets_ai_fields(self):
        """Frame novo (nunca revisado) continua recebendo os campos normalmente."""
        fake_table = _FakeFrameAnnotationsTable()
        cls = make_frame_cls(species="dasyprocta leporina", score=0.87, level="species", frame_num=2)

        with patch("pipeline.speciesnet_handler._frame_anns", fake_table):
            _write_frame_annotations([cls], tenant_id="t1", video_id="v1")

        item = fake_table.items[("t1", "v1#00002")]
        assert item["ai_species"] == "dasyprocta leporina"
        assert item["taxonomic_level"] == "species"
        assert "annotated_species" not in item

    def test_uses_update_item_not_put_item(self):
        """put_item substituiria o item inteiro — a fake nem implementa
        put_item, então qualquer regressão pra put_item quebra este teste
        com AttributeError."""
        fake_table = _FakeFrameAnnotationsTable()
        cls = make_frame_cls(frame_num=3)
        with patch("pipeline.speciesnet_handler._frame_anns", fake_table):
            _write_frame_annotations([cls], tenant_id="t1", video_id="v1")
        assert ("t1", "v1#00003") in fake_table.items

    def test_geo_review_flag_is_persisted(self):
        """Entrega (b) do geofencing (SIAB-187): geo_review_flag grava junto
        dos outros campos de IA, sem tocar nos campos humanos (mesma garantia
        de update_item já coberta acima)."""
        fake_table = _FakeFrameAnnotationsTable()
        cls = make_frame_cls(species="penelope purpurascens", level="species", frame_num=4, geo_review_flag=True)
        with patch("pipeline.speciesnet_handler._frame_anns", fake_table):
            _write_frame_annotations([cls], tenant_id="t1", video_id="v1")
        item = fake_table.items[("t1", "v1#00004")]
        assert item["geo_review_flag"] is True
