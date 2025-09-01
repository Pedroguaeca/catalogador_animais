import os
import cv2
import glob
import csv
from datetime import datetime
from ultralytics import YOLO

# Caminhos base
VIDEOS_DIR = "videos"
FRAMES_DIR = "frames"
RESULTS_DIR = "resultados"
CSV_PATH = os.path.join(RESULTS_DIR, "catalogo_animais.csv")

# Carrega modelo YOLO
modelo = YOLO("yolov8n.pt")

# Função: converte vídeo para .mp4 se necessário
def converter_para_mp4(caminho_video):
    if caminho_video.endswith(".mp4"):
        return caminho_video
    caminho_mp4 = caminho_video.rsplit(".", 1)[0] + ".mp4"
    if not os.path.exists(caminho_mp4):
        print(f"Convertendo {caminho_video} para {caminho_mp4}...")
        os.system(f"ffmpeg -i \"{caminho_video}\" \"{caminho_mp4}\"")
    return caminho_mp4

# Função: extrai frames de um vídeo
def extrair_frames(caminho_video, nome_video):
    cap = cv2.VideoCapture(caminho_video)
    frame_count = 0
    saved_frames = []

    while True:
        sucesso, frame = cap.read()
        if not sucesso:
            break
        frame_nome = f"{nome_video}_frame_{frame_count:04d}.jpg"
        caminho_frame = os.path.join(FRAMES_DIR, frame_nome)
        cv2.imwrite(caminho_frame, frame)
        saved_frames.append((caminho_frame, frame_count))
        frame_count += 1

    cap.release()
    print(f"Extraídos {frame_count} frames de {nome_video}")
    return saved_frames

# Função: detecta animais em um frame
def detectar_animais(caminho_frame):
    if not os.path.exists(caminho_frame):
        print(f"[AVISO] Frame não encontrado: {caminho_frame}")
        return []

    try:
        resultados = modelo(caminho_frame)
    except Exception as e:
        print(f"[ERRO] Não foi possível processar {caminho_frame}: {e}")
        return []

    deteccoes = []
    for resultado in resultados:
        for caixa in resultado.boxes:
            classe_id = int(caixa.cls[0])
            confianca = float(caixa.conf[0])
            nome_classe = modelo.names[classe_id]
            deteccoes.append((nome_classe, confianca))

    return deteccoes


# Garante que as pastas existem
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Prepara CSV
csv_file = open(CSV_PATH, mode="w", newline="")
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["video", "frame", "timestamp (frame)", "especie", "confianca"])

# Processo principal
videos = glob.glob(os.path.join(VIDEOS_DIR, "*"))
print(f"Encontrados {len(videos)} vídeos na pasta '{VIDEOS_DIR}'")

for caminho_video in videos:
    caminho_video = converter_para_mp4(caminho_video)
    nome_video = os.path.splitext(os.path.basename(caminho_video))[0]
    frames = extrair_frames(caminho_video, nome_video)

    for caminho_frame, frame_num in frames:
        animais_detectados = detectar_animais(caminho_frame)
        for especie, confianca in animais_detectados:
            csv_writer.writerow([nome_video, os.path.basename(caminho_frame), frame_num, especie, round(confianca, 2)])

csv_file.close()
print(f"\n✅ Processamento finalizado. Resultados salvos em: {CSV_PATH}")
