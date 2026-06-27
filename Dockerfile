FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema (OpenCV + ffmpeg para processar vídeo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# PyTorch CPU-only (imagem muito menor que a versão com CUDA)
RUN pip install --no-cache-dir \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Demais dependências do pipeline
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código do pipeline
COPY main.py utils_catalogo.py pipeline_server.py genus_map.json ./

# Pastas que serão sobrescritas por volumes em produção
RUN mkdir -p videos frames resultados

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "pipeline_server:app", "--host", "0.0.0.0", "--port", "8000"]
