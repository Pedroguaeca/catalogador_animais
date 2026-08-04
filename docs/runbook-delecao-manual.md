# Runbook — Deleção manual de vídeo/aparição/frame-annotation

> Só pra founders/quem tem acesso direto à AWS. Não existe mais nenhuma forma de apagar
> vídeo pela interface do SIAB — foi removida deliberadamente (ver contexto abaixo).

## Por quê isso existe

SIAB-149 (auditoria de segurança) encontrou `DELETE /projects/{pid}/videos/{vid}`
apagando em cascata `siab-appearances` + **todos os `siab-frame-annotations` do vídeo,
incluindo os já revisados por humano** — sem aviso específico sobre isso, e sem PITR
nem versionamento S3 como rede de segurança. Decisão (com apoio do Conselho INTI): em
vez de corrigir a UI de confirmação, remover a capacidade de apagar vídeo do app
inteiramente — nenhum usuário, de nenhum tenant ou papel, deve conseguir apagar vídeo
pela interface. Ver `backend/api.py` (comentário no lugar onde o endpoint existia) e
`infra_stack.py` (rota DELETE removida do API Gateway).

Isso não elimina a necessidade real, ocasional, de remover um vídeo (upload errado,
pedido de LGPD, teste que foi parar em produção). Este runbook é o caminho pra isso —
deliberadamente manual, deliberadamente com fricção.

## Antes de qualquer coisa: checar lock

Antes de tocar em qualquer registro, confirme que ele **não** tem `locked_reason` /
`locked_at` setado — esse campo marca vídeo/frame-annotation já referenciado num laudo
entregue a cliente. Se estiver setado, **pare**. Remover o lock exige decisão explícita
de quem entregou o laudo (não documentado aqui de propósito — não é uma checagem
automática nesta fase, é uma trava humana).

```bash
aws dynamodb get-item --table-name siab-videos --region us-east-1 \
  --key '{"tenant_id":{"S":"<TENANT>"},"project_id#video_id":{"S":"<PROJECT>#<VIDEO_ID>"}}' \
  --query 'Item.{locked_reason:locked_reason,locked_at:locked_at}'
```

Repita a checagem pra `siab-frame-annotations` (por frame) e `siab-appearances` se for
apagar algo mais granular que o vídeo inteiro.

## Passo 1 — prefira sempre soft delete

Regra geral: **nunca** `delete-item`. Marque `deleted_at` (timestamp ISO 8601) no
registro em `siab-videos`. O backend já filtra qualquer vídeo com `deleted_at` setado
de `/videos`, `/stats`, `/export` e `/appearances` (`_confirmed_appearance_groups`,
`list_videos` em `backend/api.py`) — o vídeo simplesmente some da aplicação sem que o
dado (nem o de `siab-frame-annotations`, incluindo revisão humana) seja destruído.

```bash
aws dynamodb update-item --table-name siab-videos --region us-east-1 \
  --key '{"tenant_id":{"S":"<TENANT>"},"project_id#video_id":{"S":"<PROJECT>#<VIDEO_ID>"}}' \
  --update-expression "SET deleted_at = :d" \
  --expression-attribute-values "{\":d\":{\"S\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}"
```

Isso é reversível (basta remover o atributo `deleted_at` pra trazer o vídeo de volta) e
já resolve a esmagadora maioria dos casos reais (upload errado, vídeo de teste).

## Passo 2 — se precisar mesmo de deleção física (ex: pedido formal de LGPD)

Só depois de confirmar que soft delete não é suficiente pro caso (ex: obrigação legal
de apagar o dado de verdade, não só escondê-lo). Nessa ordem, e só nessa ordem:

1. Confirme lock (seção acima) de novo — não confie no passo 1.
2. Confirme PITR ativo nas 3 tabelas (`siab-videos`, `siab-appearances`,
   `siab-frame-annotations`) e versionamento ativo no bucket `siab-media-dev` — são a
   rede de segurança que faltava:
   ```bash
   aws dynamodb describe-continuous-backups --table-name siab-frame-annotations \
     --region us-east-1 --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus'
   aws s3api get-bucket-versioning --bucket siab-media-dev --region us-east-1
   ```
3. Apague na ordem: objetos S3 (`frames/<video_id>/*` + o vídeo original) →
   `siab-appearances` do vídeo → `siab-frame-annotations` do vídeo → registro em
   `siab-videos` por último (assim, se algo falhar no meio, o vídeo continua
   "existindo" pro app em vez de virar uma referência quebrada).
4. **Escreva a entrada em `siab-audit-log` ANTES de apagar qualquer coisa**, não
   depois — se a operação falhar no meio, você quer o registro de que foi tentada.

## Passo 3 — sempre, sem exceção: registrar em siab-audit-log

`siab-audit-log` é append-only, sem nenhum caminho de escrita pelo app — só existe pra
registrar exatamente esse tipo de operação manual. PK = `tenant_id`, SK =
`<timestamp ISO8601>#<seu usuário/IAM principal>`.

```bash
aws dynamodb put-item --table-name siab-audit-log --region us-east-1 --item '{
  "tenant_id":     {"S": "<TENANT>"},
  "timestamp#actor": {"S": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'#<seu-nome-ou-IAM-user>"},
  "action":        {"S": "soft_delete_video"},
  "target_table":  {"S": "siab-videos"},
  "target_key":    {"S": "<PROJECT>#<VIDEO_ID>"},
  "reason":        {"S": "<motivo — upload errado / pedido LGPD / etc>"},
  "source":        {"S": "manual-cli"}
}'
```

Troque `"action"` pra `"hard_delete_video"` se foi o passo 2 (deleção física), e
inclua nos detalhes o que foi de fato apagado (S3 keys, appearance_ids,
frame_idx range).

## Resumo em uma frase

Lock setado → pare. Senão → soft delete (`deleted_at`). Só se for legalmente
necessário → deleção física, na ordem certa, com PITR/versionamento como rede de
segurança. Sempre → uma entrada em `siab-audit-log`, antes de apagar, não depois.
