# utils_catalogo.py
import os
import re
import csv
import cv2
import unicodedata
from datetime import datetime, timedelta
from ultralytics import YOLO

# ---------------------------------------
# Configurações padrão (podem ser trocadas no main)
# ---------------------------------------
DEFAULT_MODEL_PATH = "yolov8n.pt"
VALID_EXTS = (".avi", ".mp4", ".mov", ".mkv")
MIN_CONF_DEFAULT = 0.25     # confiança mínima
FRAME_STRIDE_DEFAULT = 1    # 1=todos os frames; 5=1 a cada 5, etc.
SAVE_PER_SPECIES = True     # salva frames em subpastas por espécie


# ---------------------------------------
# Utilidades
# ---------------------------------------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def slugify(texto: str) -> str:
    """
    Remove acentos e caracteres problemáticos.
    Mantém [a-z0-9_.-], troca o resto por '_'.
    """
    nfkd = unicodedata.normalize("NFKD", texto)
    s = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9_\-\.]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def list_videos(videos_dir: str):
    if not os.path.isdir(videos_dir):
        return []
    files = []
    for f in os.listdir(videos_dir):
        if f.lower().endswith(VALID_EXTS):
            files.append(os.path.join(videos_dir, f))
    return sorted(files)

def load_model(model_path: str = DEFAULT_MODEL_PATH) -> YOLO:
    return YOLO(model_path)

def parse_time_from_filename(name: str):
    """
    Procura um bloco HHMMSS no nome (ex.: ..._061530_...).
    Retorna (H, M, S) ou None.
    """
    base = os.path.basename(name)
    parts = re.split(r"[_\-\. ]", base)
    for p in parts:
        if len(p) == 6 and p.isdigit():
            hh, mm, ss = int(p[:2]), int(p[2:4]), int(p[4:6])
            if 0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60:
                return (hh, mm, ss)
    return None

def guess_datetime_for_frame(video_path: str, frame_idx: int, fps: float):
    """
    Baseia a data/hora no ctime do arquivo.
    Se o nome tiver HHMMSS, usamos essa hora (data = ctime).
    Soma (frame_idx / fps) para o offset.
    """
    stat = os.stat(video_path)
    base_dt = datetime.fromtimestamp(stat.st_ctime)
    hhmmss = parse_time_from_filename(video_path)
    if hhmmss:
        base_dt = base_dt.replace(hour=hhmmss[0], minute=hhmmss[1], second=hhmmss[2], microsecond=0)

    sec_offset = 0.0 if fps <= 0 else frame_idx / float(fps)
    dt = base_dt + timedelta(seconds=sec_offset)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")

def save_frame(image_bgr, out_dir: str, base_name: str, frame_idx: int, species: str | None = None):
    """
    Salva frame .jpg. Se species e SAVE_PER_SPECIES=True, salva em subpasta da espécie.
    Retorna caminho absoluto salvo.
    """
    ensure_dir(out_dir)
    base_clean = slugify(base_name)
    species_clean = slugify(species) if species else None
    fname = f"{base_clean}_frame_{frame_idx:04d}.jpg"

    target_dir = out_dir
    if SAVE_PER_SPECIES and species_clean:
        target_dir = os.path.join(out_dir, species_clean)
        ensure_dir(target_dir)

    out_path = os.path.join(target_dir, fname)
    cv2.imwrite(out_path, image_bgr)
    return out_path

def detect_on_frame(model: YOLO, image_bgr, min_conf: float):
    """
    Roda YOLO direto no frame (numpy BGR).
    Retorna lista de (classe_str, conf_float, [x1,y1,x2,y2], (W,H)).
    """
    result = model.predict(image_bgr, verbose=False)[0]
    dets = []
    if result.boxes is None:
        return dets

    H, W = image_bgr.shape[:2]
    names = result.names
    for box in result.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        if conf < min_conf:
            continue
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
        dets.append((names[cls_id], conf, [x1, y1, x2, y2], (W, H)))
    return dets

def xyxy_to_yolo(x1, y1, x2, y2, img_w, img_h):
    """
    Converte XYXY para YOLO (normalizado): x_center y_center width height
    """
    w = max(x2 - x1, 1e-6)
    h = max(y2 - y1, 1e-6)
    cx = x1 + w / 2.0
    cy = y1 + h / 2.0
    return (cx / img_w, cy / img_h, w / img_w, h / img_h)


# ---------------------------------------
# Pipeline principal
# ---------------------------------------
def process_videos(
    videos_dir: str,
    frames_dir: str,
    results_csv_path: str,
    model_path: str = DEFAULT_MODEL_PATH,
    min_conf: float = MIN_CONF_DEFAULT,
    frame_stride: int = FRAME_STRIDE_DEFAULT
):
    """
    Varre vídeos e salva:
      - frames com detecção em frames/<especie>/...
      - CSV com: video, frame, timestamp (frame), data, hora, especie, confianca
    """
    ensure_dir(frames_dir)
    ensure_dir(os.path.dirname(results_csv_path) or ".")

    model = load_model(model_path)
    videos = list_videos(videos_dir)
    if not videos:
        print("❌ Nenhum vídeo encontrado em", videos_dir)
        return

    total_rows = 0
    with open(results_csv_path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["video", "frame", "timestamp (frame)", "data", "hora", "especie", "confianca"])

        for vpath in videos:
            base = os.path.splitext(os.path.basename(vpath))[0]
            print(f"📹 Processando: {os.path.basename(vpath)}")
            cap = cv2.VideoCapture(vpath)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_idx = 0

            ok, frame = cap.read()
            while ok:
                if frame_stride <= 1 or (frame_idx % frame_stride == 0):
                    dets = detect_on_frame(model, frame, min_conf=min_conf)

                    if dets:
                        # salvamos UMA cópia do frame por espécie/detecção (para inspeção futura)
                        for (species, conf, xyxy, (W, H)) in dets:
                            out_path = save_frame(
                                frame, frames_dir, base_name=base, frame_idx=frame_idx, species=species
                            )
                            data_str, hora_str = guess_datetime_for_frame(vpath, frame_idx, fps)
                            # frame no CSV fica relativo à pasta frames (mais legível)
                            wr.writerow([
                                base,
                                os.path.relpath(out_path, frames_dir),
                                frame_idx,
                                data_str, hora_str,
                                species, round(conf, 2)
                            ])
                            total_rows += 1

                ok, frame = cap.read()
                frame_idx += 1

            cap.release()

    print(f"\n✅ Processamento finalizado. Linhas no CSV: {total_rows}")
    print(f"🗂️  CSV salvo em: {results_csv_path}")
