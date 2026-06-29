"""
Testes do módulo pipeline/megadetector.py.

Estratégia:
- Modelo mockado: nenhuma GPU/arquivo .pt necessário.
- S3 mockado: frames sintéticos em memória, sem chamadas reais.
- Testa: detecção retornada, threshold, frame corrompido, falha de S3.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch, call

import cv2
import numpy as np
import pytest

from pipeline.megadetector import (
    Detection,
    _parse_detections,
    detect_animals,
    download_model,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jpeg_bytes(color: tuple[int, int, int] = (100, 150, 200)) -> bytes:
    """Gera um JPEG sintético 64×64 com a cor dada (BGR)."""
    frame = np.full((64, 64, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


def _s3_get_object(jpeg_bytes: bytes):
    """Simula a resposta de s3.get_object com bytes em memória."""
    mock_resp = MagicMock()
    mock_resp.__getitem__ = lambda self, k: io.BytesIO(jpeg_bytes) if k == "Body" else None
    return mock_resp


def _make_raw_detection(conf: float, category: str = "1") -> dict:
    return {"category": category, "conf": conf, "bbox": [0.1, 0.2, 0.3, 0.4]}


def _make_detector_result(detections: list[dict]) -> dict:
    return {
        "max_detection_conf": max((d["conf"] for d in detections), default=0.0),
        "detections": detections,
    }


# ── Fixture: detector mockado ─────────────────────────────────────────────────

@pytest.fixture()
def mock_detector():
    """Retorna um detector falso cujo generate_detections_one_image é controlável."""
    det = MagicMock()
    det.generate_detections_one_image.return_value = _make_detector_result(
        [_make_raw_detection(conf=0.92, category="1")]
    )
    return det


@pytest.fixture()
def mock_s3_with_frame():
    """Cliente S3 que devolve um JPEG válido para qualquer get_object."""
    client = MagicMock()
    jpeg = _make_jpeg_bytes()
    body  = MagicMock()
    body.read.return_value = jpeg
    client.get_object.return_value = {"Body": body}
    return client


# ── Testes: _parse_detections ─────────────────────────────────────────────────

def test_parse_detections_retorna_detection_tipada():
    raw = _make_detector_result([_make_raw_detection(0.85)])
    result = _parse_detections(raw, "tenant/frames/v1/frame_00001.jpg", threshold=0.1)
    assert len(result) == 1
    d = result[0]
    assert isinstance(d, Detection)
    assert d.confidence == pytest.approx(0.85)
    assert d.category == "animal"
    assert d.bbox == (0.1, 0.2, 0.3, 0.4)


def test_parse_detections_filtra_abaixo_do_threshold():
    raw = _make_detector_result([
        _make_raw_detection(0.05),  # abaixo
        _make_raw_detection(0.80),  # acima
    ])
    result = _parse_detections(raw, "key", threshold=0.1)
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.80)


def test_parse_detections_mapeia_categorias():
    raw = _make_detector_result([
        _make_raw_detection(0.9, category="1"),
        _make_raw_detection(0.8, category="2"),
        _make_raw_detection(0.7, category="3"),
    ])
    result = _parse_detections(raw, "key", threshold=0.1)
    assert {d.category for d in result} == {"animal", "person", "vehicle"}


def test_parse_detections_lista_vazia():
    raw = {"detections": []}
    assert _parse_detections(raw, "key", threshold=0.1) == []


# ── Testes: detect_animals ────────────────────────────────────────────────────

def test_detect_animals_retorna_detection(mock_s3_with_frame, mock_detector):
    with patch("pipeline.megadetector._get_detector", return_value=mock_detector):
        result = detect_animals(
            s3_keys=["tenant/frames/v1/frame_00001.jpg"],
            tenant_id="tenant-abc",
            model_path="/tmp/models/md_v5a.0.0.pt",
            threshold=0.1,
            bucket="siab-media-dev",
            s3_client=mock_s3_with_frame,
        )
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.92)
    assert result[0].category == "animal"
    assert result[0].frame_s3_key == "tenant/frames/v1/frame_00001.jpg"


def test_detect_animals_descarta_abaixo_do_threshold(mock_s3_with_frame):
    detector = MagicMock()
    detector.generate_detections_one_image.return_value = _make_detector_result(
        [_make_raw_detection(conf=0.05)]  # abaixo do threshold padrão 0.1
    )
    with patch("pipeline.megadetector._get_detector", return_value=detector):
        result = detect_animals(
            s3_keys=["tenant/frames/v1/frame_00001.jpg"],
            tenant_id="tenant-abc",
            model_path="/tmp/models/md_v5a.0.0.pt",
            threshold=0.1,
            bucket="siab-media-dev",
            s3_client=mock_s3_with_frame,
        )
    assert result == []


def test_detect_animals_frame_corrompido_nao_quebra_batch(mock_detector):
    """Frame corrompido é ignorado; frames válidos do mesmo batch continuam."""
    jpeg_ok  = _make_jpeg_bytes()
    body_ok  = MagicMock(); body_ok.read.return_value = jpeg_ok
    body_bad = MagicMock(); body_bad.read.return_value = b"nao_e_jpeg"

    s3 = MagicMock()
    s3.get_object.side_effect = [
        {"Body": body_bad},  # frame 1: corrompido
        {"Body": body_ok},   # frame 2: válido
    ]

    with patch("pipeline.megadetector._get_detector", return_value=mock_detector):
        result = detect_animals(
            s3_keys=["bad_frame.jpg", "good_frame.jpg"],
            tenant_id="tenant-abc",
            model_path="/tmp/models/md_v5a.0.0.pt",
            threshold=0.1,
            bucket="siab-media-dev",
            s3_client=s3,
        )

    # Só o frame válido gera detecção
    assert len(result) == 1
    assert result[0].frame_s3_key == "good_frame.jpg"


def test_detect_animals_falha_s3_ignora_frame(mock_detector):
    """Erro de S3 em um frame não interrompe o processamento dos demais."""
    from botocore.exceptions import ClientError

    jpeg_ok = _make_jpeg_bytes()
    body_ok = MagicMock(); body_ok.read.return_value = jpeg_ok

    s3 = MagicMock()
    s3.get_object.side_effect = [
        ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"),
        {"Body": body_ok},
    ]

    with patch("pipeline.megadetector._get_detector", return_value=mock_detector):
        result = detect_animals(
            s3_keys=["missing.jpg", "good.jpg"],
            tenant_id="tenant-abc",
            model_path="/tmp/models/md_v5a.0.0.pt",
            threshold=0.1,
            bucket="siab-media-dev",
            s3_client=s3,
        )

    assert len(result) == 1
    assert result[0].frame_s3_key == "good.jpg"


def test_detect_animals_multiplas_deteccoes_por_frame(mock_s3_with_frame):
    """Um frame com dois animais deve gerar duas Detection."""
    detector = MagicMock()
    detector.generate_detections_one_image.return_value = _make_detector_result([
        _make_raw_detection(0.95, "1"),
        _make_raw_detection(0.80, "1"),
    ])
    with patch("pipeline.megadetector._get_detector", return_value=detector):
        result = detect_animals(
            s3_keys=["frame.jpg"],
            tenant_id="t1",
            model_path="/tmp/models/md_v5a.0.0.pt",
            threshold=0.1,
            bucket="siab-media-dev",
            s3_client=mock_s3_with_frame,
        )
    assert len(result) == 2


# ── Testes: download_model ────────────────────────────────────────────────────

def test_download_model_usa_cache_se_existir(tmp_path):
    """Se o arquivo já existe localmente, não chama o S3."""
    model_file = tmp_path / "md_v5a.0.0.pt"
    model_file.write_bytes(b"fake_model")

    s3 = MagicMock()
    path = download_model("bucket", "models/md_v5a.0.0.pt", str(model_file), s3_client=s3)

    s3.download_file.assert_not_called()
    assert path == str(model_file)


def test_download_model_baixa_se_ausente(tmp_path):
    """Se o arquivo não existe, faz download_file do S3."""
    model_file = tmp_path / "md_v5a.0.0.pt"
    s3 = MagicMock()
    s3.download_file.side_effect = lambda bucket, key, dest: open(dest, "wb").write(b"model")

    path = download_model("siab-media-dev", "models/md_v5a.0.0.pt", str(model_file), s3_client=s3)

    s3.download_file.assert_called_once_with("siab-media-dev", "models/md_v5a.0.0.pt", str(model_file))
    assert path == str(model_file)
