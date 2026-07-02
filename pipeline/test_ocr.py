"""
pipeline/test_ocr.py — Testes do módulo de extração de metadados OCR.
"""

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.ocr import (
    VideoMetadata,
    _extract_overlay_bar,
    _ocr_pytesseract,
    _parse_overlay_text,
    _parse_iso_loose,
    _probe_metadata,
    extract_video_metadata,
)

# Caminho do vídeo real (skip se não existir)
REAL_VIDEO = "/Users/pedromcamarote/Downloads/DSCF0007.AVI"


class TestParseIsoLoose(unittest.TestCase):
    def test_iso_format(self):
        assert _parse_iso_loose("2025-01-11T08:14:30") == "2025-01-11T08:14:30"

    def test_iso_with_space(self):
        assert _parse_iso_loose("2025-01-11 08:14:30") == "2025-01-11T08:14:30"

    def test_iso_with_microseconds(self):
        assert _parse_iso_loose("2025-01-11T08:14:30.000000Z") == "2025-01-11T08:14:30"

    def test_ddmmyyyy_format(self):
        assert _parse_iso_loose("11/01/2025 08:14:30") == "2025-01-11T08:14:30"

    def test_invalid_returns_none(self):
        assert _parse_iso_loose("nada aqui") is None


class TestParseOverlayText(unittest.TestCase):
    """Testa parsing do texto OCR bruto do overlay Bushnell."""

    PYTESSERACT_OUTPUT = "0004  @ B 19°C GE 11/01/2025 08:14:30 0007"
    EASYOCR_OUTPUT     = "0004 19 % 66 % 11/0 1/2025 08 : 14:30 0007"

    def _assert_fields(self, meta: VideoMetadata):
        self.assertEqual(meta.camera_id, "0004")
        self.assertEqual(meta.captured_at, "2025-01-11T08:14:30")
        self.assertEqual(meta.temperature_c, 19.0)
        self.assertEqual(meta.location_source, "ocr")

    def test_pytesseract_output(self):
        meta = _parse_overlay_text(self.PYTESSERACT_OUTPUT)
        self._assert_fields(meta)

    def test_easyocr_output(self):
        meta = _parse_overlay_text(self.EASYOCR_OUTPUT)
        self.assertEqual(meta.camera_id, "0004")
        self.assertEqual(meta.captured_at, "2025-01-11T08:14:30")
        self.assertAlmostEqual(meta.temperature_c, 19.0)

    def test_empty_text_returns_none(self):
        self.assertIsNone(_parse_overlay_text("sem dados relevantes"))

    def test_partial_text_no_date(self):
        # Só camera_id e temperatura, sem data: deve retornar sem captured_at
        meta = _parse_overlay_text("0004 19°C")
        self.assertIsNotNone(meta)
        self.assertEqual(meta.camera_id, "0004")
        self.assertIsNone(meta.captured_at)

    def test_temperature_variants(self):
        # Diferentes formas que o ° pode aparecer após OCR
        for text in ["0004 19°C 11/01/2025 08:14:30", "0004 19%C 11/01/2025 08:14:30"]:
            meta = _parse_overlay_text(text)
            self.assertIsNotNone(meta, f"Falhou para: {text!r}")
            self.assertAlmostEqual(meta.temperature_c, 19.0)


class TestExtractOverlayBar(unittest.TestCase):
    """Testa extracção da barra do overlay."""

    def test_no_overlay_returns_none(self):
        # Frame completamente verde (vegetação, sem barra preta)
        with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as f:
            path = f.name
        try:
            # Cria AVI sintético sem overlay (frame verde)
            out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 1, (320, 240))
            frame = np.full((240, 320, 3), (0, 180, 0), dtype=np.uint8)
            out.write(frame)
            out.release()
            result = _extract_overlay_bar(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_overlay_detected(self):
        # Frame com barra preta inferior (simulando overlay real)
        with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as f:
            path = f.name
        try:
            out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 1, (320, 240))
            frame = np.full((240, 320, 3), (100, 150, 80), dtype=np.uint8)  # vegetação
            # Barra preta nos últimos 12%
            frame[int(240 * 0.88):, :] = (5, 5, 5)
            out.write(frame)
            out.release()
            result = _extract_overlay_bar(path)
            self.assertIsNotNone(result)
        finally:
            os.unlink(path)


class TestProbeMetadata(unittest.TestCase):
    """Testa Stage 1 — metadados do arquivo."""

    def test_metadata_with_creation_time(self):
        # Simula ffprobe retornando creation_time
        fake_output = '{"format": {"tags": {"creation_time": "2025-01-11T08:14:30.000000Z"}}}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            with tempfile.NamedTemporaryFile(suffix=".avi") as f:
                meta = _probe_metadata(f.name)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.captured_at, "2025-01-11T08:14:30")
        self.assertEqual(meta.location_source, "metadata")

    def test_metadata_empty_tags(self):
        # AVI Bushnell sem tags (caso real)
        fake_output = '{"format": {"tags": {}}}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            with tempfile.NamedTemporaryFile(suffix=".avi") as f:
                meta = _probe_metadata(f.name)
        self.assertIsNone(meta)

    def test_ffprobe_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with tempfile.NamedTemporaryFile(suffix=".avi") as f:
                meta = _probe_metadata(f.name)
        self.assertIsNone(meta)


class TestExtractVideoMetadataManualFallback(unittest.TestCase):
    """Testa fallback para location_source="manual"."""

    def test_synthetic_video_no_overlay_returns_manual(self):
        # Vídeo completamente verde: Stage 1 falha (sem tags), Stage 2 falha (sem overlay)
        with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as f:
            path = f.name
        try:
            out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 1, (320, 240))
            frame = np.full((240, 320, 3), (0, 180, 0), dtype=np.uint8)
            out.write(frame)
            out.release()
            # Patch ffprobe para não encontrar tags
            fake_ffprobe = '{"format": {"tags": {}}}'
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=fake_ffprobe)
                meta = extract_video_metadata(path)
            self.assertEqual(meta.location_source, "manual")
            self.assertIsNone(meta.camera_id)
            self.assertIsNone(meta.captured_at)
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            extract_video_metadata("/inexistente/video.avi")


@unittest.skipUnless(os.path.isfile(REAL_VIDEO), f"Vídeo real não encontrado: {REAL_VIDEO}")
class TestRealVideo(unittest.TestCase):
    """Testa com o vídeo real DSCF0007.AVI."""

    def test_extract_full_pipeline(self):
        meta = extract_video_metadata(REAL_VIDEO)
        print(f"\n[Real] location_source={meta.location_source}")
        print(f"       camera_id={meta.camera_id}")
        print(f"       captured_at={meta.captured_at}")
        print(f"       temperature_c={meta.temperature_c}")

        self.assertEqual(meta.location_source, "ocr")
        self.assertEqual(meta.camera_id, "0004")
        self.assertEqual(meta.captured_at, "2025-01-11T08:14:30")
        self.assertAlmostEqual(meta.temperature_c, 19.0)

    def test_overlay_bar_extracted(self):
        bar = _extract_overlay_bar(REAL_VIDEO)
        self.assertIsNotNone(bar)
        h, w = bar.shape[:2]
        self.assertGreater(w, 100)
        self.assertGreater(h, 10)

    def test_pytesseract_ocr(self):
        bar = _extract_overlay_bar(REAL_VIDEO)
        self.assertIsNotNone(bar)
        text = _ocr_pytesseract(bar)
        self.assertIsNotNone(text)
        self.assertIn("0004", text)
        self.assertIn("2025", text)
        print(f"\n[OCR raw] {text!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
