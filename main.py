# main.py
from utils_catalogo import process_videos

# Ajuste estes caminhos conforme seu projeto (estamos no iCloud/Documents/catalogador_animais)
VIDEOS_DIR = "videos"
FRAMES_DIR = "frames"
RESULTS_CSV = "resultados/catalogo_animais.csv"

# Parâmetros de execução
MODEL_PATH = "yolov8n.pt"   # troque pelo seu modelo custom depois
MIN_CONF = 0.20             # mais baixo = acha mais, mas erra mais
FRAME_STRIDE = 1            # 1=todos os frames; 5=um a cada 5; 10=um a cada 10

if __name__ == "__main__":
    process_videos(
        videos_dir=VIDEOS_DIR,
        frames_dir=FRAMES_DIR,
        results_csv_path=RESULTS_CSV,
        model_path=MODEL_PATH,
        min_conf=MIN_CONF,
        frame_stride=FRAME_STRIDE
    )
