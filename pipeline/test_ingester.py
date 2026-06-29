"""
Testes do módulo pipeline/ingester.py.

Estratégia:
- Gera um vídeo sintético com cv2 (sem precisar de arquivo real).
- Substitui o cliente S3 por um mock (unittest.mock) para não fazer chamadas reais.
- Testa o caminho feliz, vídeo inexistente e falha de upload no S3.
"""

import io
import os
import tempfile
from unittest.mock import MagicMock, patch, call

import cv2
import numpy as np
import pytest

from pipeline.ingester import ingest_video, IngestResult, _s3_key


# ── Fixture: vídeo sintético ──────────────────────────────────────────────────

def make_synthetic_video(path: str, fps: int = 5, seconds: int = 3) -> None:
    """Cria um vídeo MP4 sintético com frames coloridos aleatórios."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (320, 240))
    rng = np.random.default_rng(42)
    for _ in range(fps * seconds):
        frame = rng.integers(0, 255, (240, 320, 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()


@pytest.fixture(scope="module")
def synthetic_video_path():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        path = f.name
    make_synthetic_video(path, fps=5, seconds=3)
    yield path
    os.unlink(path)


@pytest.fixture()
def mock_s3():
    """Cliente S3 falso que aceita put_object sem fazer chamadas reais."""
    client = MagicMock()
    client.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    return client


# ── Testes ────────────────────────────────────────────────────────────────────

def test_ingest_retorna_resultado_tipado(synthetic_video_path, mock_s3):
    """ingest_video deve retornar um IngestResult com campos preenchidos."""
    result = ingest_video(
        video_path=synthetic_video_path,
        tenant_id="tenant-abc",
        project_id="proj-001",
        video_id="vid-001",
        bucket="siab-media-dev",
        s3_client=mock_s3,
    )
    assert isinstance(result, IngestResult)
    assert result.tenant_id == "tenant-abc"
    assert result.video_id  == "vid-001"
    assert result.fps       == pytest.approx(5.0, abs=0.5)
    assert result.duration_seconds > 0
    assert result.width  == 320
    assert result.height == 240


def test_ingest_extrai_1_frame_por_segundo(synthetic_video_path, mock_s3):
    """Vídeo de 3 s a 5 fps deve gerar exatamente 3 frames (1/segundo)."""
    result = ingest_video(
        video_path=synthetic_video_path,
        tenant_id="tenant-abc",
        project_id="proj-001",
        video_id="vid-001",
        bucket="siab-media-dev",
        s3_client=mock_s3,
    )
    assert result.total_frames == 3
    assert len(result.s3_keys) == 3


def test_s3_keys_formato_correto(synthetic_video_path, mock_s3):
    """As chaves S3 devem seguir o padrão {tenant_id}/frames/{video_id}/frame_NNNNN.jpg."""
    result = ingest_video(
        video_path=synthetic_video_path,
        tenant_id="tenant-xyz",
        project_id="proj-999",
        video_id="vid-007",
        bucket="siab-media-dev",
        s3_client=mock_s3,
    )
    for i, key in enumerate(result.s3_keys):
        expected = _s3_key("tenant-xyz", "vid-007", i)
        assert key == expected, f"Frame {i}: esperado {expected}, obtido {key}"


def test_put_object_chamado_para_cada_frame(synthetic_video_path, mock_s3):
    """put_object deve ser chamado uma vez por frame salvo."""
    result = ingest_video(
        video_path=synthetic_video_path,
        tenant_id="t1",
        project_id="p1",
        video_id="v1",
        bucket="siab-media-dev",
        s3_client=mock_s3,
    )
    assert mock_s3.put_object.call_count == result.total_frames


def test_video_nao_encontrado():
    """FileNotFoundError deve ser levantado para caminho inexistente."""
    with pytest.raises(FileNotFoundError, match="não encontrado"):
        ingest_video(
            video_path="/tmp/inexistente_siab_test.mp4",
            tenant_id="t1",
            project_id="p1",
            video_id="v1",
        )


def test_video_corrompido():
    """ValueError deve ser levantado para arquivo que não é vídeo válido."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"isto nao e um video")
        path = f.name
    try:
        with pytest.raises(ValueError, match="corrompido"):
            ingest_video(
                video_path=path,
                tenant_id="t1",
                project_id="p1",
                video_id="v1",
            )
    finally:
        os.unlink(path)


def test_falha_s3_propaga_excecao(synthetic_video_path):
    """ClientError do S3 deve ser propagada e não silenciada."""
    from botocore.exceptions import ClientError

    broken_s3 = MagicMock()
    broken_s3.put_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucket", "Message": "bucket not found"}},
        "PutObject",
    )
    with pytest.raises(ClientError):
        ingest_video(
            video_path=synthetic_video_path,
            tenant_id="t1",
            project_id="p1",
            video_id="v1",
            bucket="bucket-inexistente",
            s3_client=broken_s3,
        )
