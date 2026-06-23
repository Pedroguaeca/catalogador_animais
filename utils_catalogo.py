# utils_catalogo.py — pipeline de dois estágios: MegaDetector + AI4GAmazonRainforest
import os
import re
import csv
import cv2
import unicodedata
from datetime import datetime, timedelta

import numpy as np
from PytorchWildlife.models import detection as pw_det
from PytorchWildlife.models import classification as pw_cls

# ---------------------------
# Versão dos modelos (obrigatório para auditabilidade — ver CLAUDE.md)
# ---------------------------
MODEL_VERSION = "MegaDetectorV6-MDV6-yolov9-c+AI4GAmazonRainforest-v2"

VALID_EXTS = (".avi", ".mp4", ".mov", ".mkv")
DET_CONF_DEFAULT = 0.2     # limiar do MegaDetector (estágio 1)
CLS_CONF_DEFAULT = 0.3     # limiar do AI4G (estágio 2); abaixo disso → "Unknown"
FRAME_STRIDE_DEFAULT = 1   # 1 = todo frame; 10 = um a cada 10
SAVE_PER_GENUS = True      # organiza frames em subpastas por gênero


# ---------------------------
# Utilidades (sem mudança)
# ---------------------------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def slugify(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    s = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9_\-\.]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def list_videos(videos_dir: str) -> list[str]:
    if not os.path.isdir(videos_dir):
        return []
    return sorted(
        os.path.join(videos_dir, f)
        for f in os.listdir(videos_dir)
        if f.lower().endswith(VALID_EXTS)
    )


def parse_time_from_filename(name: str):
    base = os.path.basename(name)
    for p in re.split(r"[_\-\.]", base):
        if len(p) == 6 and p.isdigit():
            hh, mm, ss = int(p[:2]), int(p[2:4]), int(p[4:6])
            if 0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60:
                return (hh, mm, ss)
    return None


def guess_datetime_for_frame(video_path: str, frame_idx: int, fps: float):
    stat = os.stat(video_path)
    base_dt = datetime.fromtimestamp(stat.st_ctime)
    hhmmss = parse_time_from_filename(video_path)
    if hhmmss:
        base_dt = base_dt.replace(hour=hhmmss[0], minute=hhmmss[1], second=hhmmss[2], microsecond=0)
    sec_offset = 0.0 if fps <= 0 else frame_idx / float(fps)
    dt = base_dt + timedelta(seconds=sec_offset)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")


def save_frame(image_bgr: np.ndarray, out_dir: str, base_name: str, frame_idx: int, genus: str | None = None) -> str:
    ensure_dir(out_dir)
    base_clean = slugify(base_name)
    fname = f"{base_clean}_frame_{frame_idx:04d}.jpg"
    if SAVE_PER_GENUS and genus:
        out_dir = os.path.join(out_dir, slugify(genus))
        ensure_dir(out_dir)
    out_path = os.path.join(out_dir, fname)
    cv2.imwrite(out_path, image_bgr)
    return out_path


def save_crop(image_bgr: np.ndarray, frames_dir: str, base_name: str, frame_idx: int, genus: str) -> str:
    genus_clean = slugify(genus)
    crop_dir = os.path.join(frames_dir, genus_clean, "crops")
    ensure_dir(crop_dir)
    fname = f"{slugify(base_name)}_frame_{frame_idx:04d}_crop.jpg"
    out_path = os.path.join(crop_dir, fname)
    cv2.imwrite(out_path, image_bgr)
    return out_path


def xyxy_to_yolo(x1: float, y1: float, x2: float, y2: float, img_w: int, img_h: int) -> tuple:
    w = max(x2 - x1, 1e-6)
    h = max(y2 - y1, 1e-6)
    cx = x1 + w / 2.0
    cy = y1 + h / 2.0
    return (cx / img_w, cy / img_h, w / img_w, h / img_h)


# ---------------------------
# Carregamento de modelos
# ---------------------------
def load_detector(device: str = "cpu") -> pw_det.MegaDetectorV6:
    print("  → Carregando MegaDetector V6...")
    return pw_det.MegaDetectorV6(device=device, pretrained=True, version="MDV6-yolov9-c")


def load_classifier(device: str = "cpu") -> pw_cls.AI4GAmazonRainforest:
    print("  → Carregando AI4G Amazon Rainforest v2...")
    return pw_cls.AI4GAmazonRainforest(device=device, pretrained=True)


# ---------------------------
# Pipeline de detecção + classificação
# ---------------------------
def detect_and_classify(
    detector: pw_det.MegaDetectorV6,
    classifier: pw_cls.AI4GAmazonRainforest,
    frame_bgr: np.ndarray,
    det_conf_thres: float = DET_CONF_DEFAULT,
    cls_conf_thres: float = CLS_CONF_DEFAULT,
) -> list[tuple]:
    """
    Estágio 1 — MegaDetector: localiza animais no frame e descarta frames vazios.
    Estágio 2 — AI4G: classifica o gênero de cada recorte detectado.

    Retorna lista de (genus, det_conf, cls_conf, [x1, y1, x2, y2]).
    Se cls_conf < cls_conf_thres, genus = "Unknown" (frame ainda é salvo para revisão).
    """
    # OpenCV usa BGR; PytorchWildlife espera RGB
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = frame_bgr.shape[:2]

    # Estágio 1
    det = detector.single_image_detection(frame_rgb, det_conf_thres=det_conf_thres)
    detections = det["detections"]

    if len(detections) == 0:
        return []

    results = []
    for i in range(len(detections.xyxy)):
        if int(detections.class_id[i]) != 0:  # 0=animal; ignora pessoas e veículos
            continue

        det_conf = float(detections.confidence[i])
        x1, y1, x2, y2 = [int(v) for v in detections.xyxy[i]]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            continue

        # Estágio 2 — recorta e classifica
        crop_rgb = frame_rgb[y1:y2, x1:x2]
        cls = classifier.single_image_classification(crop_rgb)
        cls_conf = float(cls["confidence"])
        genus = cls["prediction"] if cls_conf >= cls_conf_thres else "Unknown"

        results.append((genus, det_conf, cls_conf, [x1, y1, x2, y2]))

    return results


# ---------------------------
# Pipeline principal
# ---------------------------
def process_videos(
    videos_dir: str,
    frames_dir: str,
    results_csv_path: str,
    det_conf: float = DET_CONF_DEFAULT,
    cls_conf_thres: float = CLS_CONF_DEFAULT,
    frame_stride: int = FRAME_STRIDE_DEFAULT,
    device: str = "cpu",
):
    """
    Lê todos os vídeos em videos_dir e para cada frame amostrado:
      1. Roda MegaDetector — filtra frames sem animal.
      2. Roda AI4GAmazonRainforest em cada recorte — classifica o gênero.
      3. Salva frame completo e recorte em frames_dir.
      4. Grava linha no CSV com: video, frame, crop, timestamp, data, hora,
         genero, det_conf, cls_conf, model_version.
    """
    ensure_dir(frames_dir)
    ensure_dir(os.path.dirname(results_csv_path) or ".")

    print("⏳ Carregando modelos (pode baixar pesos na primeira vez)...")
    detector = load_detector(device=device)
    classifier = load_classifier(device=device)
    print(f"✅ Modelos prontos. Versão registrada: {MODEL_VERSION}\n")

    videos = list_videos(videos_dir)
    if not videos:
        print("❌ Nenhum vídeo encontrado em", videos_dir)
        return

    total_rows = 0
    with open(results_csv_path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow([
            "video", "frame", "crop", "timestamp (frame)",
            "data", "hora", "genero", "det_conf", "cls_conf", "model_version",
        ])

        for vpath in videos:
            base = os.path.splitext(os.path.basename(vpath))[0]
            print(f"📹 Processando: {os.path.basename(vpath)}")
            cap = cv2.VideoCapture(vpath)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_idx = 0
            frames_com_animal = 0

            ok, frame = cap.read()
            while ok:
                if frame_stride <= 1 or (frame_idx % frame_stride == 0):
                    dets = detect_and_classify(
                        detector, classifier, frame,
                        det_conf_thres=det_conf,
                        cls_conf_thres=cls_conf_thres,
                    )

                    for (genus, d_conf, c_conf, xyxy) in dets:
                        frame_path = save_frame(frame, frames_dir, base, frame_idx, genus=genus)

                        x1, y1, x2, y2 = xyxy
                        crop_bgr = frame[y1:y2, x1:x2]
                        crop_path = save_crop(crop_bgr, frames_dir, base, frame_idx, genus=genus)

                        data_str, hora_str = guess_datetime_for_frame(vpath, frame_idx, fps)

                        wr.writerow([
                            base,
                            os.path.relpath(frame_path, frames_dir),
                            os.path.relpath(crop_path, frames_dir),
                            frame_idx,
                            data_str, hora_str,
                            genus,
                            round(d_conf, 3),
                            round(c_conf, 3),
                            MODEL_VERSION,
                        ])
                        total_rows += 1
                        frames_com_animal += 1

                ok, frame = cap.read()
                frame_idx += 1

            cap.release()
            print(f"   {frame_idx} frames lidos | {frames_com_animal} detecções salvas")

    print(f"\n✅ Processamento finalizado. Linhas no CSV: {total_rows}")
    print(f"🗂️  CSV salvo em: {results_csv_path}")
