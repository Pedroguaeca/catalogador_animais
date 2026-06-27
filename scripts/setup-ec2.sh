#!/bin/bash
# setup-ec2.sh — Provisiona uma EC2 Amazon Linux 2023 para o SIAB
# Execute uma vez em cada instância (staging e prod) via SSH:
#   ssh ec2-user@<IP> 'bash -s' < scripts/setup-ec2.sh
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REGISTRY="${ECR_REGISTRY:?Defina ECR_REGISTRY=<account>.dkr.ecr.<region>.amazonaws.com}"

echo "==> Atualizando sistema..."
sudo dnf update -y

echo "==> Instalando Docker..."
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

echo "==> Instalando Docker Compose plugin..."
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL \
  "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

echo "==> Instalando AWS CLI..."
sudo dnf install -y aws-cli

echo "==> Criando diretório do projeto..."
sudo mkdir -p /opt/siab/{videos,frames,resultados}
sudo chown -R ec2-user:ec2-user /opt/siab

echo "==> Configurando ECR login automático no boot..."
cat <<EOF | sudo tee /etc/cron.d/ecr-login
0 */6 * * * ec2-user aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
EOF

echo "==> Copiando arquivos de configuração..."
# docker-compose.yml, nginx/, genus_map.json precisam ser copiados manualmente
# ou via git clone (se o repo for privado, configure SSH key antes)
echo ""
echo "PRÓXIMOS PASSOS MANUAIS:"
echo "  1. Copie docker-compose.yml para /opt/siab/"
echo "  2. Copie nginx/ para /opt/siab/nginx/"
echo "  3. Copie genus_map.json para /opt/siab/"
echo "  4. cd /opt/siab && docker compose up -d"
echo ""
echo "==> Setup concluído! Reconecte ao SSH para aplicar permissões de grupo."
