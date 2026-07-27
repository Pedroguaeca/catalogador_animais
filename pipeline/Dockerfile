# ── Estágio ML (MegaDetector + SpeciesNet) ───────────────────────────────────
# Build context: catalogador_animais/pipeline/
# CDK: DockerImageCode.from_image_asset("../pipeline", file="Dockerfile")
#
# STAGE env var seleciona o estágio:
#   STAGE=megadetector  →  pipeline.megadetector_handler.lambda_handler
#   STAGE=speciesnet    →  pipeline.speciesnet_handler.lambda_handler

FROM public.ecr.aws/lambda/python:3.12

# Dependências de sistema necessárias para opencv e ffmpeg (AL2023: dnf, mesmos nomes de pacote do AL2)
RUN dnf install -y mesa-libGL libSM libXext libXrender gcc gcc-c++ python3-devel make && dnf clean all

# numpy pré-compilado do PyPI antes do torch — evita build de fonte no aarch64
# (torchvision depende de numpy, e o --index-url abaixo não tem wheel dele)
RUN pip install --no-cache-dir numpy==2.2.6

# PyTorch CPU primeiro — camada separada para melhor cache Docker
# Usar wheel CPU reduz de ~750 MB para ~250 MB instalados
RUN pip install --no-cache-dir \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Demais dependências ML
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# megadetector instalado sem deps para evitar mkl==2024.0 (Intel-only, não existe em aarch64).
# A inferência é feita pelo PyTorch — MKL é apenas otimização de CPU Intel.
RUN pip install --no-cache-dir --no-deps megadetector==10.0.23

# Código do pipeline (contexto já é pipeline/, então "." é o pacote inteiro)
COPY . ${LAMBDA_TASK_ROOT}/pipeline/

# Garante que /tmp/models existe para cache de modelos entre warm starts
RUN mkdir -p /tmp/models

# Handler genérico — o STAGE env var escolhe o estágio real em runtime
CMD ["pipeline.handler.handler"]
