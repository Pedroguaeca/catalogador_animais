# ── Estágio ML (MegaDetector + SpeciesNet) ───────────────────────────────────
# Build context: raiz do projeto (catalogador_animais/)
# CDK: DockerImageCode.from_image_asset("..", file="pipeline/Dockerfile")
#
# STAGE env var seleciona o estágio:
#   STAGE=megadetector  →  pipeline.megadetector_handler.lambda_handler
#   STAGE=speciesnet    →  pipeline.speciesnet_handler.lambda_handler

FROM public.ecr.aws/lambda/python:3.11

# Dependências de sistema necessárias para opencv e ffmpeg
RUN dnf install -y mesa-libGL libSM libXext libXrender && dnf clean all

# PyTorch CPU primeiro — camada separada para melhor cache Docker
# Usar wheel CPU reduz de ~750 MB para ~250 MB instalados
RUN pip install --no-cache-dir \
    torch==2.7.1 \
    torchvision==0.22.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Demais dependências ML
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código do pipeline
COPY pipeline/ ${LAMBDA_TASK_ROOT}/pipeline/

# Garante que /tmp/models existe para cache de modelos entre warm starts
RUN mkdir -p /tmp/models

# Handler genérico — o STAGE env var escolhe o estágio real em runtime
CMD ["pipeline.handler.handler"]
