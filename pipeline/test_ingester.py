"""
Testes do módulo pipeline/ingester.py.

Estratégia:
- Gera um vídeo sintético com cv2 (sem precisar de arquivo real).
- Substitui o cliente S3 por um mock (unittest.mock) para não fazer chamadas reais.
- Testa o caminho feliz, vídeo inexistente e falha de upload no S3.
"""

import io
import json
import logging
import os
import tempfile
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import cv2
import numpy as np
import pytest

from pipeline.ingester import ingest_video, IngestResult, _s3_key, lambda_handler, _update_video_status


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


# ── Helpers para testes do lambda_handler ─────────────────────────────────────

def _make_sqs_event(
    video_s3_key: str = "tenant-abc/videos/vid-001.avi",
    tenant_id: str = "tenant-abc",
    project_id: str = "proj-001",
    video_id: str = "vid-001",
) -> dict:
    return {
        "Records": [{
            "body": json.dumps({
                "video_s3_key": video_s3_key,
                "tenant_id":    tenant_id,
                "project_id":   project_id,
                "video_id":     video_id,
            })
        }]
    }


def _make_boto3_mocks():
    """Devolve (mock_client_fn, mock_s3, mock_sqs, mock_ddb, cameras_table, videos_table).

    Usa side_effect em ddb.Table para que siab-cameras e siab-videos
    devolvam mocks independentes — evita confundir chamadas de _ensure_camera
    com as de _update_video_status no mesmo assert.
    """
    mock_s3  = MagicMock()
    mock_sqs = MagicMock()
    mock_ddb = MagicMock()
    cameras_table = MagicMock()
    videos_table  = MagicMock()

    def _table(name):
        return cameras_table if "cameras" in name else videos_table

    mock_ddb.Table.side_effect = _table

    def _client(service, **kw):
        return mock_s3 if service == "s3" else mock_sqs

    return _client, mock_s3, mock_sqs, mock_ddb, cameras_table, videos_table


# ── Testes do lambda_handler: update_item em siab-videos ─────────────────────

class TestLambdaHandlerUpdateVideoStatus:

    def _run_handler(self, event, mock_ocr_meta, *, ocr_raises=False):
        """Executa lambda_handler com todos os side-effects mockados.

        Devolve (response, videos_table_mock) — o mock da tabela siab-videos
        é separado do da siab-cameras para que os asserts sejam unívocos.
        """
        client_fn, mock_s3, mock_sqs, mock_ddb, _, videos_table = _make_boto3_mocks()

        mock_ingest_result = IngestResult(
            tenant_id="tenant-abc", project_id="proj-001", video_id="vid-001",
            s3_keys=["tenant-abc/frames/vid-001/frame_00000.jpg"],
            total_frames=1, fps=5.0, duration_seconds=1.0,
        )

        with (
            patch("pipeline.ingester.boto3.client", side_effect=client_fn),
            patch("pipeline.ingester.boto3.resource", return_value=mock_ddb),
            patch("pipeline.ocr.extract_video_metadata",
                  side_effect=RuntimeError("sem overlay") if ocr_raises else None,
                  return_value=mock_ocr_meta),
            patch("pipeline.ingester.ingest_video", return_value=mock_ingest_result),
            patch("os.path.exists", return_value=False),
            patch.dict(os.environ, {"FRAMES_QUEUE_URL": "https://sqs.amazonaws.com/123/siab-frames"}),
        ):
            resp = lambda_handler(event, {})

        return resp, videos_table

    def test_update_item_chamado_com_key_correto(self):
        """update_item deve usar tenant_id e project_id#video_id como chave."""
        from pipeline.ocr import VideoMetadata
        meta = VideoMetadata(camera_id="0004", captured_at="2025-01-11T08:14:30",
                             temperature_c=19.0, location_source="ocr")
        event = _make_sqs_event()
        _, mock_table = self._run_handler(event, meta)

        mock_table.update_item.assert_called_once()
        kw = mock_table.update_item.call_args.kwargs
        assert kw["Key"] == {
            "tenant_id":           "tenant-abc",
            "project_id#video_id": "proj-001#vid-001",
        }

    def test_update_item_contem_4_campos_e_status_processing(self):
        """UpdateExpression deve conter os 4 campos; status deve ser 'processing'."""
        from pipeline.ocr import VideoMetadata
        meta = VideoMetadata(camera_id="0004", captured_at="2025-01-11T08:14:30",
                             temperature_c=19.0, location_source="ocr")
        event = _make_sqs_event()
        _, mock_table = self._run_handler(event, meta)

        kw = mock_table.update_item.call_args.kwargs
        assert kw["ExpressionAttributeNames"] == {"#status": "status"}

        vals = kw["ExpressionAttributeValues"]
        assert vals[":status"]      == "processing"
        assert vals[":camera_id"]   == "0004"
        assert vals[":captured_at"] == "2025-01-11T08:14:30"
        assert vals[":temperature_c"] == Decimal("19.0")

    def test_status_avanca_para_processing_mesmo_com_ocr_total_failure(self, caplog):
        """OCR que falha completamente não deve travar o vídeo em 'uploaded'."""
        event = _make_sqs_event()

        with caplog.at_level(logging.WARNING, logger="pipeline.ingester"):
            resp, mock_table = self._run_handler(event, mock_ocr_meta=None, ocr_raises=True)

        assert resp == {"statusCode": 200}
        mock_table.update_item.assert_called_once()
        vals = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        assert vals[":status"]        == "processing"
        assert vals[":camera_id"]     is None
        assert vals[":captured_at"]   is None
        assert vals[":temperature_c"] is None
        assert any("OCR falhou" in r.message for r in caplog.records)


# ── Teste direto de _update_video_status ─────────────────────────────────────

def test_update_video_status_usa_expression_attribute_names():
    """'status' é palavra reservada: ExpressionAttributeNames obrigatório."""
    mock_ddb = MagicMock()
    mock_table = MagicMock()
    mock_ddb.Table.return_value = mock_table

    _update_video_status(mock_ddb, "t1", "p1", "v1", "0004", "2025-01-11T08:14:30", 19.0)

    kw = mock_table.update_item.call_args.kwargs
    assert "#status" in kw["ExpressionAttributeNames"]
    assert kw["ExpressionAttributeNames"]["#status"] == "status"
    assert "#status" in kw["UpdateExpression"]


def test_update_video_status_nao_propaga_excecao_dynamo(caplog):
    """Falha no DynamoDB não deve derrubar o pipeline."""
    from botocore.exceptions import ClientError
    mock_ddb = MagicMock()
    mock_table = MagicMock()
    mock_table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "table not found"}},
        "UpdateItem",
    )
    mock_ddb.Table.return_value = mock_table

    with caplog.at_level(logging.WARNING, logger="pipeline.ingester"):
        _update_video_status(mock_ddb, "t1", "p1", "v1", None, None, None)

    assert any("_update_video_status falhou" in r.message for r in caplog.records)
