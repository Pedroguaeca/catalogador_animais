# SIAB — Catalogador de Fauna em Câmeras-Trap

Plataforma de monitoramento de fauna para compliance ambiental.
Vídeos de câmeras-trap → detecção de animais → classificação de espécie → aparições → revisão humana → laudos.

> Lido pelo Claude Code em toda sessão. Mantenha abaixo de 200 linhas.

---

## Stack real (produção, 2026-07)

| Camada | Tecnologia |
|---|---|
| Cloud | AWS (us-east-1) · Account 617371012344 |
| IaC | AWS CDK Python — `infra/` |
| Backend API | FastAPI + Mangum · Lambda Container ARM64 · `siab-api` |
| Frontend | Next.js 14 + NextAuth v5 · Vercel (`frontend-siab.vercel.app`) |
| Auth | Cognito `us-east-1_muBMGRYkB` · Google OAuth · JWT RS256 |
| Pipeline | Lambda Container ARM64 · ECR repo `cdk-hnb659fds-container-assets-…` |
| Infra de dados | DynamoDB PAY_PER_REQUEST · S3 `siab-media-dev` |

---

## Pipeline (fluxo completo)

```
Upload vídeo (PUT S3 presigned) → POST /confirm → SQS siab-videos
  → siab-ingester     (extrai frames, OCR câmera/timestamp) → SQS siab-frames
  → siab-megadetector (detecta animais, filtra frames)       → SQS siab-detections
  → siab-speciesnet   (classifica espécie, escreve por frame + por aparição)
  → siab-consolidator (merge cross-video a cada 15 min, EventBridge)
```

---

## Tabelas DynamoDB — chaves

| Tabela | PK | SK |
|---|---|---|
| siab-videos | tenant_id | project_id#video_id |
| siab-appearances | tenant_id | video_id#appearance_id |
| siab-frame-annotations | tenant_id | video_id#frame_idx (zero-pad 5 dígitos) |
| siab-reviews | tenant_id | appearance_id#reviewed_at |
| siab-cameras | tenant_id | project_id#camera_id |
| siab-invites | tenant_id | email |
| siab-species | species_id | — |

`siab-appearances` tem dois GSIs: `by-species` (PK=`tenant_id#project_id`) e `by-review-status` (PK=`tenant_id#review_status`).

---

## Schema siab-frame-annotations (Fase 1, 2026-07-11)

Campos escritos pelo pipeline (`siab-speciesnet`):
`tenant_id`, `video_id#frame_idx`, `video_id`, `frame_idx`, `frame_s3_key`, `ai_species`, `ai_score` (Decimal), `bbox` (list[Decimal] × 4).

Campo adicionado por revisão humana: `annotated_species`, `annotation_source`, `annotated_at`.

**Não existe** campo `appearance_id` no SK — a ligação a aparições é por `video_id` + range de `frame_idx`.

---

## Endpoints relevantes

```
GET  /projects/{pid}/appearances            — lista aparições (filtros review_status, species)
GET  /projects/{pid}/appearances/{id}/frames — frames da aparição com presigned URLs
GET  /projects/{pid}/videos                 — lista vídeos + display_status
GET  /projects/{pid}/videos/{vid}/frames    — frame-annotations do vídeo (AI + humanas)
POST /projects/{pid}/videos/{vid}/confirm-all — confirma todos os frames sem anotação humana
PATCH /frames/annotation                    — anota 1 frame (video_id + frame_path + species)
GET  /appearances/{id}/frame-annotations    — anotações humanas de uma aparição
PATCH /appearances/{id}/review              — confirmar/rejeitar/corrigir aparição
GET  /projects/{pid}/stats                  — dashboard (só aparições confirmed)
```

`display_status` de um vídeo deriva de `siab-frame-annotations`:
- Sem frames → "Processando"
- Todos com `annotated_species` → "Revisado"
- Parcial → "Aguardando revisão"

---

## Build e deploy

### Validar TypeScript (frontend)
```bash
cd frontend && npx tsc --noEmit
```

### Deploy CDK (schema DynamoDB, IAM, event sources)
```bash
cd infra && cdk deploy --require-approval never
```
⚠ CDK synthesis leva ~8 min e rebuilda imagens Docker. Prefira deploy manual para mudanças só de código.

### Deploy manual — API Lambda
```bash
cd catalogador_animais   # raiz do projecto
ECR="617371012344.dkr.ecr.us-east-1.amazonaws.com/cdk-hnb659fds-container-assets-617371012344-us-east-1"
TAG="siab-api-$(date +%Y%m%d-%H%M%S)"
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR"
docker buildx build --provenance=false --platform linux/arm64 -f backend/Dockerfile -t "${ECR}:${TAG}" --push .
aws lambda update-function-code --function-name siab-api --image-uri "${ECR}:${TAG}" --region us-east-1
```

### Deploy manual — pipeline Lambdas (speciesnet / megadetector)
```bash
# build context é pipeline/ (NÃO a raiz)
TAG="siab-pipeline-$(date +%Y%m%d-%H%M%S)"
docker buildx build --provenance=false --platform linux/arm64 -f pipeline/Dockerfile -t "${ECR}:${TAG}" --push pipeline/
aws lambda update-function-code --function-name siab-speciesnet --image-uri "${ECR}:${TAG}" --region us-east-1
# siab-megadetector usa a mesma imagem
```

### Deploy frontend
⚠ Rodar da **raiz do repositório**, não de dentro de `frontend/` — o Root
Directory do projeto já está configurado como `frontend` nas settings da
Vercel, então `cd frontend && vercel --prod` duplica o path
(`~/frontend/frontend`) e falha com "provided path does not exist"
(achado 06-07/08/2026).
```bash
vercel --prod
```

---

## Convenções estabelecidas

1. **Validar sempre com dados reais.** Antes de considerar qualquer mudança pronta: fazer upload de um vídeo real, confirmar que o pipeline escreveu os dados esperados, e testar os endpoints com cURL ou Lambda invoke. "Sem erro de sintaxe" não é validação.

2. **Multi-tenant obrigatório.** Toda query DynamoDB filtra por `tenant_id`. Tenant padrão dev: `consultoria-teste`.

3. **Sem JWT em dev** — `SIAB_JWT_VALIDATION=off` na env do Lambda usa `tenant_id=consultoria-teste` sem verificar assinatura. Restaurar para `on` imediatamente após testes.

4. **Pipeline idempotente.** `_claim_video_for_processing()` usa conditional update `status=uploaded → processing` para evitar re-processamento. Se o registo do vídeo for apagado antes da re-entrega SQS, o vídeo re-processa (edge case conhecido, sem workaround).

5. **ECR: sempre `--provenance=false` e `--platform linux/arm64`.** Sem isso o Lambda ARM64 falha ao iniciar.

6. **Dockerfile da API: COPY requirements.txt antes de RUN pip install.** Assim mudanças de código não invalidam o cache do pip (corrigido em 2026-07-11).

7. **`cdk deploy` lê `infra/lambda/*` direto do disco, sem checar git.** Já aconteceu de handlers (Cognito triggers, consolidator) rodarem em produção sem nenhum commit (corrigido em 2026-07-25). Commitar `infra/lambda/` **antes** de rodar `cdk deploy` — mesma regra do deploy manual de Lambda/Vercel.

8. **NUNCA aplicar mudança de schema DynamoDB (GSI, atributo, etc.) via `aws dynamodb update-table`/CLI direto — sempre via `cdk deploy`.** Aconteceu em 24-25/07: um GSI criado manualmente em `siab-species` pra desbloquear uma task ficou invisível pro CloudFormation, e — junto de uma tabela (`siab-frame-annotations`) que já tinha o mesmo problema por outro motivo — quase causou um `cdk deploy` tentar recriar (delete+create) uma tabela de produção com 576 itens reais. Reconciliado via backup + `cdk import`, mas o processo levou uma sessão inteira e exigiu contornar 3 restrições da AWS pra changeset de import (limite de template inline, não pode mexer em Outputs, não pode mexer em nenhum outro recurso na mesma changeset). Se uma mudança de infra for urgente demais pra esperar `cdk deploy`, trate como incidente — não como atalho — e reconcilie o código **imediatamente depois**, na mesma sessão.

---

## Restrições de segurança (permanentes)

- **NÃO** apagar o utilizador `Google_100439318177594446487` (siabnature@gmail.com) nem o seu invite em `siab-invites`.
- **NÃO** apagar dados de `siab-species`.
- **NÃO** apagar o prefixo `models/` no S3 (modelos SpeciesNet em cache).

---

## Estado da Fase 1 (redesenho /review) — CONCLUÍDO 2026-07-11

`siab-frame-annotations` agora guarda classificação AI por frame (SK=`video_id#frame_idx`).
O pipeline escreve antes do `gap_track()`. Dois novos endpoints (GET /frames, POST /confirm-all).
Validado com vídeo real: 15 frame-annotations escritas, display_status correto.

## Próximo: Fase 2 — redesenho do frontend /review

Navegação por vídeo (não por aparição). Ver handover da sessão de 2026-07-11.

---

## Specs de produto no Notion

**Antes de propor qualquer mudança de arquitectura, endpoints, modelo de dados ou UX em `/review`, anotação, ou pipeline de ML: verificar se já existe decisão registrada nestas specs — não redescobrir o que já foi decidido.** (Já aconteceu: o redesenho de `/review` de 11/07 foi, na prática, redescoberta de uma decisão já tomada em 03/07 e nunca totalmente implementada — ver "Achado 11/07" na task do Notion abaixo.)

| Spec | Link | Conteúdo |
|---|---|---|
| Índice de documentação (Notion) | https://app.notion.com/p/393637bdb7198157af5bd8e2f8492d11 | Ponto de entrada — lista todas as specs de produto/UX e agora também os 9 docs técnicos abaixo |
| UX Spec — Ajustes de Implementação: Anotação e Revisão (v1.1) | https://app.notion.com/p/392637bdb71981d4ab3bf72d6961c61b | Decisão de arquitetura "Persistência por frame + regra de discrepância" (03/07) — origem da Fase 1/2 atual |
| Spec — MLOps: Evals, Versionamento e Loop de Treinamento | https://app.notion.com/p/390637bdb71981f2894bcdf7e04753ef | Como as confirmações humanas viram dataset de fine-tuning |
| Task "Evoluir /review" (histórico completo da decisão de Fase 1/2) | https://app.notion.com/p/399637bdb71981d7ba40f1cfd3e0afed | Log completo: correção de rumo 11/07, achado "já decidido em 03/07", handoff da sessão 5323d1d4 |

### Docs técnicos do repo, espelhados no Notion (11/07)

⚠ **O repo (`docs/`) é a fonte de verdade** — o espelho no Notion serve para consulta/onboarding, não para editar. Além disso, PRD/architecture/data-model/pipeline descrevem uma arquitetura antiga (ECS Fargate + Terraform, "Aparição" como unidade central) que diverge da stack real (Lambda + CDK) e da direção pós-Fase 1/2 (frame como unidade central) — cada página do Notion tem essa divergência anotada inline.

| Doc | Link Notion |
|---|---|
| PRD.md | https://app.notion.com/p/39b637bdb719812eb674cc301a3ffae2 |
| architecture.md | https://app.notion.com/p/39b637bdb719812aa967eec05811b470 |
| data-model.md | https://app.notion.com/p/39b637bdb71981369321f339a748e54f |
| pipeline.md | https://app.notion.com/p/39b637bdb71981e9ae50df280686cbac |
| ADR-0001 — Pipeline de dois estágios | https://app.notion.com/p/39b637bdb71981fa892ff9aa64bcecf4 |
| ADR-0002 — Aparição: gap temporal | https://app.notion.com/p/39b637bdb71981cfa97efd39eb9b7d32 |
| ADR-0003 — Multi-table DynamoDB | https://app.notion.com/p/39b637bdb719813681f2c7a0c2143156 |
| ADR-0004 — Multitenancy | https://app.notion.com/p/39b637bdb719817c9938ed2a6e0320d1 |
| ADR-0005 — Timestamp/OCR | https://app.notion.com/p/39b637bdb7198182a52afb60e394387c |

Novas specs devem ser adicionadas a esta tabela quando criadas.
