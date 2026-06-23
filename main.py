# main.py — ponto de entrada do pipeline SIAB
from utils_catalogo import process_videos

VIDEOS_DIR   = "videos"
FRAMES_DIR   = "frames"
RESULTS_CSV  = "resultados/catalogo_animais.csv"

# Estágio 1 — MegaDetector: confiança mínima para considerar que há um animal no frame
DET_CONF     = 0.2

# Estágio 2 — AI4G: confiança mínima para aceitar o gênero; abaixo disso grava "Unknown"
CLS_CONF     = 0.3

# Amostragem de frames: 1 = todo frame; 5 = um a cada 5; 10 = um a cada 10
FRAME_STRIDE = 1

# Dispositivo de inferência: "cpu" ou "cuda" (se houver GPU disponível)
DEVICE       = "cpu"

if __name__ == "__main__":
    process_videos(
        videos_dir=VIDEOS_DIR,
        frames_dir=FRAMES_DIR,
        results_csv_path=RESULTS_CSV,
        det_conf=DET_CONF,
        cls_conf_thres=CLS_CONF,
        frame_stride=FRAME_STRIDE,
        device=DEVICE,
    )
