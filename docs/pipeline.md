# SIAB — Pipeline de Processamento

**Complementa:** `architecture.md`, `data-model.md` | **Decisões:** ADR-0001, ADR-0002

---

## 1. Visão geral

Do upload do vídeo à aparição persistida e revisável:

```
Upload vídeo (S3)
   │  EventBridge
   ▼
[SQS: extração] → ECS Fargate: extrai frames (taxa definida, ex. 3 fps)
   │  EventBridge
   ▼
[SQS: detecção] → ECS Fargate: MegaDetector
   │   • marca bounding boxes de animais
   │   • descarta frames vazios  ◄── grande economia
   │  EventBridge
   ▼
[SQS: classificação] → ECS Fargate (GPU?): SpeciesNet + AI4G
   │   • classifica cada recorte
   │   • retorna espécie + score + taxonomia hierárquica
   ▼
Consolidação em APARIÇÕES (gap temporal)
   │   • agrupa detecções contíguas da mesma espécie
   │   • fecha aparição após gap sem detecção
   │   • escolhe melhor recorte da sequência
   ▼
Persiste Aparição (DynamoDB) + recorte (S3)
   ▼
Entra na fila de Human Review (review_status = pending)
```

## 2. Estágio de detecção (MegaDetector)
- Entrada: frames extraídos. Saída: bounding boxes + score, ou "vazio".
- Frames vazios são descartados aqui — a maioria, em câmera-trap.
- Não classifica espécie; só localiza.

## 3. Estágio de classificação (SpeciesNet + AI4G)
- Entrada: recortes (crops) das caixas do MegaDetector.
- Saída: espécie + score + caminho taxonômico.
- Regra de confiança: abaixo do limiar de espécie, reportar nível taxonômico superior
  (gênero/família) em vez de chutar. Defensável em laudo.
- Registrar SEMPRE a `model_version`.

## 4. Consolidação em aparições (gap temporal — MVP)
Lógica de pós-processamento sobre as detecções classificadas de um vídeo:

```
para cada espécie detectada no vídeo, em ordem temporal:
    se (tempo desde a última detecção desta espécie) > GAP:
        fecha a aparição anterior
        abre uma nova aparição
    senão:
        estende a aparição atual (atualiza frame_end, support_frames)
ao fechar: escolhe o frame de melhor qualidade como best_crop
```

- `GAP` é **configurável por projeto** (comportamento varia por espécie/ambiente).
- `individual_count` = 1 por aparição no MVP; o analista corrige no Human Review.
- Tracking (contagem real de indivíduos) entra na V1 — ver ADR-0002. A entidade Aparição
  já comporta ambos; muda só como os campos são preenchidos.

## 5. Human Review (motor de dados)
- Consome a fila `review_status = pending` (GSI-2).
- Analista confirma/corrige espécie e ajusta contagem de indivíduos.
- Cada revisão é persistida em `reviews` em formato pronto para treino.
- Acumulado o volume → fine-tuning do SpeciesNet → modelo proprietário SIAB.

## 6. Pendências de infra
- **GPU vs. Fargate CPU** na classificação (e em tracking futuro). Impacta latência e custo.
- Política de retry e dead-letter queue em cada SQS.
- TTL/limpeza dos frames transitórios após consolidação.
