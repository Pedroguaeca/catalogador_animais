FROM public.ecr.aws/lambda/python:3.12

# Instala dependências antes de copiar o código para aproveitar cache Docker
COPY backend/requirements.txt /var/task/backend/
RUN pip install --no-cache-dir -r /var/task/backend/requirements.txt

COPY backend/ /var/task/backend/
COPY pipeline/ /var/task/pipeline/

CMD ["backend.lambda_handler.handler"]
