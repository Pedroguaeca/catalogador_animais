# SIAB — Modelo de Dados

**Banco:** DynamoDB | **Storage de mídia:** S3
**Complementa:** `architecture.md` | **Decisões relacionadas:** ADR-0002, ADR-0003

---

## 1. Princípio de modelagem

DynamoDB se modela a partir das **perguntas** (access patterns), não das tabelas. Esta
seção lista as perguntas primeiro; chaves e índices derivam delas.

Decisão de estilo: **multi-table** no MVP (uma tabela por entidade principal). Mais
intuitivo e flexível para um produto que ainda vai evoluir (drones, satélites, flora nas
fases futuras). Otimização single-table pode ser reavaliada quando os padrões estabilizarem.
Ver ADR-0003.

## 2. Access patterns (as perguntas do sistema)

| # | Pergunta | Entidade-alvo |
|---|---|---|
| AP1 | Todos os projetos de um cliente | Projeto |
| AP2 | Todos os vídeos/capturas de um projeto | Vídeo |
| AP3 | Todas as aparições de um vídeo | Aparição |
| AP4 | Todas as aparições de uma espécie num projeto | Aparição |
| AP5 | Todas as aparições com revisão pendente (fila do analista) | Aparição |
| AP6 | Uma aparição e seu histórico de revisão (auditoria) | Aparição + Revisão |
| AP7 | Contagem de espécies distintas num projeto (biodiversidade) | Aparição |
| AP8 | Exportar todas as aparições de um projeto (CSV) | Aparição |
| AP9 | Consultar o catálogo taxonômico de referência | Espécie |

## 3. Entidades e relacionamentos

```
Cliente
  └─ Projeto
       └─ Vídeo/Captura
            └─ Aparição  ◄── unidade central de registro
                 └─ Revisão (histórico; pode haver mais de uma)

Espécie (catálogo taxonômico de referência — vive à parte)
```

A entidade **Aparição** substitui Frame+Detecção como registro persistente. Frames e
detecções individuais existem só durante o processamento; consolidam-se numa Aparição.

## 4. Tabelas

### 4.1 `projects`
| Campo | Tipo | Notas |
|---|---|---|
| PK: `client_id` | string | partição por cliente |
| SK: `project_id` | string | |
| name, area, start_date, end_date, status | — | metadados do projeto |

Atende AP1.

### 4.2 `videos`
| Campo | Tipo | Notas |
|---|---|---|
| PK: `project_id` | string | |
| SK: `video_id` | string | |
| s3_key, camera_id, captured_at, duration, status | — | `status`: uploaded/processing/done/error |

Atende AP2. `s3_key` aponta para o vídeo original no S3.

### 4.3 `appearances` (tabela central)
| Campo | Tipo | Notas |
|---|---|---|
| PK: `video_id` | string | |
| SK: `appearance_id` | string | ordenável por tempo de início |
| project_id | string | denormalizado p/ índices |
| species, species_score | string/number | espécie classificada |
| taxonomic_level | string | nível reportado (species/genus/family/...) |
| taxonomic_path | string | hierarquia completa (Catalogue of Life) |
| model_version | string | **obrigatório** — rastreabilidade |
| frame_start, frame_end | number | janela da aparição no vídeo |
| ts_start, ts_end | number | timestamps no vídeo |
| support_frames | number | nº de frames que sustentaram (confiança) |
| best_crop_s3_key | string | melhor recorte (revisão + treino) |
| individual_count | number | nº de indivíduos (1 no MVP; corrigível pelo analista) |
| review_status | string | pending/confirmed/corrected |

Atende AP3 (PK = video_id).

**GSI-1 — por espécie no projeto (AP4, AP7, AP8):**
PK: `project_id`, SK: `species#appearance_id`

**GSI-2 — fila de revisão (AP5):**
PK: `review_status`, SK: `project_id#appearance_id` (consultar status = "pending")

### 4.4 `reviews`
| Campo | Tipo | Notas |
|---|---|---|
| PK: `appearance_id` | string | |
| SK: `reviewed_at` | string (ISO) | histórico ordenado |
| reviewer_id | string | |
| original_species, original_score | — | o que o modelo previu |
| confirmed_species | string | o que o analista confirmou/corrigiu |
| corrected_individual_count | number | ajuste de contagem |
| model_version | string | versão que gerou a predição revisada |

Atende AP6. **Cada item aqui é um dado de treino** para o fine-tuning futuro.

### 4.5 `species` (catálogo)
| Campo | Tipo | Notas |
|---|---|---|
| PK: `species_id` | string | |
| common_name, scientific_name | — | |
| taxonomic_path | string | alinhado ao Catalogue of Life |
| conservation_status | string | p/ relatórios e alertas |

Atende AP9. Tabela de referência, baixo volume.

## 5. Divisão DynamoDB × S3

| No S3 | No DynamoDB |
|---|---|
| Vídeos originais | Metadados de vídeo + `s3_key` |
| Frames extraídos (transitórios) | — (não persistem como registro) |
| Recortes (crops) das aparições | `best_crop_s3_key` na Aparição |

Regra: nada de binário no DynamoDB; só ponteiros.

## 6. Pontos em aberto / a validar na implementação
- Volume real de aparições por vídeo → confirmar custo das GSIs.
- Política de TTL para frames transitórios (limpar do storage de trabalho).
- Se `review_status` como PK da GSI-2 gera "hot partition" (poucos valores distintos);
  avaliar chave composta se necessário.
- Particionamento do GSI-1 se um projeto tiver volume muito alto de uma só espécie.
