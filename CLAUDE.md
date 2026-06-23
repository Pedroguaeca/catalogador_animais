# SIAB — Sistema de Inteligência Ambiental e Biodiversidade

Plataforma de inteligência ambiental e compliance de biodiversidade. O MVP foca em
monitoramento de fauna a partir de vídeos de câmeras-trap: detecta animais, identifica
a espécie, consolida aparições únicas e gera evidências auditáveis para laudos ambientais.

> Este arquivo é lido pelo Claude Code em toda sessão. Mantenha-o curto e atualizado.
> Detalhes completos estão em `docs/`.

## Como navegar a documentação
- `docs/PRD.md` — visão de produto, JTBD, funcionalidades, roadmap (fonte original).
- `docs/architecture.md` — arquitetura técnica e decisões de stack.
- `docs/data-model.md` — modelo de dados (DynamoDB), entidades e access patterns.
- `docs/pipeline.md` — pipeline de processamento de vídeo (detecção → classificação → aparição).
- `docs/decisions/` — ADRs: registros das decisões de arquitetura e seus porquês.

## Abordagem central de IA (NÃO usar YOLO genérico para espécie)
Pipeline de dois estágios, padrão de câmera-trap:
1. **Detecção** — MegaDetector (localiza animais, filtra frames vazios).
2. **Classificação** — SpeciesNet + AI4G Amazon Rainforest (espécie + taxonomia hierárquica).

API de LLM (GPT) NÃO é usada como classificador de produção (custo, alucinação, falta de
rastreabilidade). Ver ADR-0001.

## Conceito-chave: Aparição
A unidade de registro NÃO é o frame nem a detecção individual. É a **Aparição**: um
indivíduo entra em cena, permanece por N frames, sai = 1 registro. No MVP, aparições são
separadas por **gap temporal**; tracking entra na V1. Ver ADR-0002 e `docs/data-model.md`.

## Stack
- Detecção/Classificação: MegaDetector + SpeciesNet + AI4G (via PyTorch-Wildlife)
- Backend: FastAPI (Python 3.11)
- Frontend: Streamlit (MVP) → React/Next.js
- Cloud (AWS): S3, ECS Fargate, SQS, EventBridge, DynamoDB, CloudWatch
- IaC: Terraform
- Taxonomia de referência: Catalogue of Life

## Princípios inegociáveis (compliance)
- Toda classificação registra a **versão do modelo** que a gerou (auditabilidade).
- Toda revisão humana é persistida em **formato pronto para treino** (recorte + label +
  score original + nível taxonômico + revisor + timestamp).
- Quando a confiança na espécie é baixa, reportar o **nível taxonômico superior** em vez
  de chutar (ex.: "família Dasyproctidae").
- Imagens/vídeos/recortes vivem no **S3**; DynamoDB guarda metadados + ponteiros S3.

## Convenções de código
- Python com type hints obrigatórios.
- Nunca commitar credenciais; usar variáveis de ambiente / secrets manager.
- Uma feature por branch.
- Cada decisão estrutural vira uma ADR em `docs/decisions/`.

## Estado atual
- MVP de detecção já existe (YOLO genérico) — será substituído pelo pipeline de 2 estágios.
- Próximo passo: fatia vertical (MegaDetector → SpeciesNet → persistência → Human Review).
