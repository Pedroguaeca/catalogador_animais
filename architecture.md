# SIAB — Documento de Arquitetura e Decisões Técnicas

**Versão:** Junho 2026 (revisão pós-análise de modelos de visão computacional)
**Complementa:** SIAB Master PRD
**Destino:** raiz do repositório, em `docs/architecture.md`

---

## 1. Resumo da revisão

Este documento formaliza a arquitetura do MVP do SIAB e incorpora uma mudança central de abordagem na detecção/classificação de fauna, decidida após teste prático: **abandonar o YOLO genérico como solução de espécie e adotar um pipeline de dois estágios** baseado em modelos open-source consolidados de câmera-trap.

A mudança resolve o problema observado: o YOLO genérico detecta que há um animal, mas não identifica a espécie (ex.: cotia) por não ter fine-tuning para fauna brasileira.

---

## 2. A decisão central: pipeline de dois estágios

O padrão da indústria de câmera-trap separa duas tarefas distintas que o YOLO genérico tentava (e falhava em) unir:

| Estágio | Tarefa | Pergunta que responde |
|---|---|---|
| **1. Detecção** | Localizar e recortar animais nos frames | "Onde há um animal? Quais frames descarto por estarem vazios?" |
| **2. Classificação** | Identificar a espécie no recorte | "Que espécie é este animal?" |

O YOLO genérico fazia bem o estágio 1 e mal o estágio 2. A solução não é trocar de modelo, é **adicionar o estágio 2 com um classificador especializado**.

### Estágio 1 — Detecção: MegaDetector
- Modelo open-source da Microsoft (AI for Good), padrão mundial, licença MIT.
- Detecta animal / pessoa / veículo e marca bounding boxes.
- Filtra automaticamente frames vazios — crítico em vídeo, onde a maioria dos frames não tem fauna.
- Substitui (ou complementa) o YOLO genérico atual.

### Estágio 2 — Classificação: SpeciesNet (+ AI4G Amazon)
- **SpeciesNet (Google)**: ~2.000 rótulos (espécies + níveis taxonômicos), treinado em +65M de imagens. Licença Apache 2.0 (uso comercial e fine-tuning liberados). Já desenhado para consumir a saída do MegaDetector.
- **AI4G Amazon Rainforest** (via PyTorch-Wildlife): classificador focado no contexto amazônico.
- **TropiCam-AI**: 84 táxons neotropicais (Brasil, Peru, Guiana Francesa, Costa Rica), ConvNeXt-Base, ~95% de acurácia. Restrição: focado em fauna **arbórea** (dossel). Útil como classificador secundário onde aplicável.

### Por que não usar a API de LLM (GPT) como solução de produção
O teste com GPT foi um diagnóstico valioso (provou que o problema é classificação, não detecção), mas não serve como motor de produção:
- **Custo**: vídeo = milhares de frames × chamada de API por frame.
- **Sem rastreabilidade científica**: não retorna score de confiança calibrado nem taxonomia hierárquica.
- **Risco de alucinação**: inaceitável num contexto de compliance EIA/RIMA, onde o laudo precisa ser defensável.

Os modelos de câmera-trap rodam na própria AWS (sem custo por imagem), dão score calibrado, retornam taxonomia em múltiplos níveis e são validados em literatura peer-reviewed.

### A agregação taxonômica como rede de segurança
SpeciesNet e TropiCam-AI retornam a classificação em vários níveis da hierarquia (espécie → gênero → família → ordem). Quando a confiança na espécie exata é baixa, o sistema reporta o nível superior ("roedor da família Dasyproctidae") em vez de chutar. Isso é cientificamente defensável e deve ser uma regra de negócio explícita do SIAB.

---

## 3. O loop de dados — o fosso competitivo real

Esta é a peça estratégica que conecta a arquitetura técnica à Market Strategy do PRD (aquisição de dados via projetos de conservação e ONGs).

```
Detecção → Classificação automática → Human Review (analista confirma/corrige)
                                              │
                                              ▼
                                    Dado rotulado brasileiro
                                              │
                                              ▼
                          Fine-tuning do SpeciesNet (licença permite)
                                              │
                                              ▼
                              Modelo proprietário SIAB
```

A feature "Human Review" deixa de ser só controle de qualidade e passa a ser o **motor de geração de dataset**. Cada correção do analista é um rótulo. Quando o volume amadurece, faz-se fine-tuning e nasce o modelo proprietário — ativo mais valioso que o software em si.

**Implicação:** desde o MVP, toda revisão humana deve ser persistida em formato pronto para treino (recorte + label + score original + nível taxonômico + revisor + timestamp).

---

## 4. Impacto nas funcionalidades do MVP

Revisão das 13 funcionalidades à luz da nova abordagem:

| Funcionalidade | Mudança |
|---|---|
| Fauna Detection | Deixa de ser "YOLO". Passa a ser **MegaDetector (detecção) + SpeciesNet/AI4G (espécie)**. |
| Frame Extraction | Adicionar filtro de frames vazios via MegaDetector antes da classificação (economia de processamento). |
| Species Catalog | Ganha papel estratégico: ancora a taxonomia (alinhar ao Catalogue of Life, como faz o TropiCam) e serve de referência para o Human Review. |
| Human Review | Reposicionada como motor de dataset. Persistir saídas em formato de treino. |
| Evidence Persistence | Precisa guardar não só a detecção, mas o recorte, o score, o nível taxonômico e a versão do modelo usada. |
| Intelligent Reports / Chat with Data | Devem expor o nível de confiança e a taxonomia hierárquica, não só "espécie X". |

As demais (Project Management, Video Upload, Automatic Registration, Biodiversity Dashboard, Evidence Gallery, CSV Export) seguem como no PRD.

---

## 5. Lacunas que faltavam no PRD (a resolver antes/durante a construção)

O PRD está sólido na visão e na stack, mas estas definições técnicas precisam ser fechadas:

### 5.1 Modelo de dados (DynamoDB)
DynamoDB exige decidir as *access patterns* ANTES de modelar. Entidades mínimas do MVP:
- **Projeto** (cliente, área, período de monitoramento)
- **Vídeo/Captura** (origem, câmera, data, projeto)
- **Frame** (vídeo de origem, timestamp, status: vazio/com animal)
- **Detecção** (frame, bounding box, score do detector)
- **Classificação** (detecção, espécie, score, nível taxonômico, versão do modelo)
- **Revisão** (classificação, revisor, label confirmado/corrigido, timestamp)
- **Espécie** (catálogo taxonômico de referência)

*Pendência:* listar as consultas reais (ex.: "todas as detecções de espécie X num projeto", "todas as revisões pendentes") para então desenhar partition/sort keys e índices.

### 5.2 Pipeline de eventos
Fluxo proposto, a detalhar:
```
Upload (S3) → EventBridge → fila SQS de extração → ECS Fargate (extrai frames)
   → EventBridge → fila SQS de detecção → ECS Fargate (MegaDetector, filtra vazios)
   → EventBridge → fila SQS de classificação → ECS Fargate (SpeciesNet/AI4G)
   → persiste em DynamoDB + recortes em S3 → atualiza Dashboard
```
*Pendências:* definir exatamente quais eventos no EventBridge, política de retry/dead-letter nas SQS, e se a inferência roda em Fargate (CPU) ou exige instância com GPU.

### 5.3 GPU vs. CPU
MegaDetector e SpeciesNet rodam muito mais rápido em GPU. ECS Fargate não oferece GPU nativamente. Decisão pendente: usar EC2 com GPU para a etapa de inferência, ou aceitar latência maior em Fargate CPU no MVP. Impacta custo e a métrica de "processing cost" do PRD.

### 5.4 Critérios de aceite por feature
O PRD lista as 13 funcionalidades, mas sem critérios de aceite. Cada uma precisa de: qual JTBD atende, como saber que está pronta, e restrições. A definir feature a feature durante a construção.

### 5.5 Versionamento de modelo
Como compliance exige rastreabilidade, toda classificação persistida deve registrar qual versão de qual modelo a gerou. Necessário desde o MVP para que laudos antigos permaneçam auditáveis quando o modelo for atualizado.

### 5.6 Estratégia de vídeo
SpeciesNet processa imagens estáticas; o suporte a vídeo passa por extrair frames. Definir taxa de extração (o TropiCam usou 3 frames/segundo) e como consolidar múltiplas detecções do mesmo animal ao longo de uma sequência (evitar contar a mesma cotia 40 vezes).

---

## 6. Sequência de construção recomendada (fatia vertical)

Como o MVP de detecção já existe, a prioridade é trocar o miolo de IA e fechar o loop de dados:

1. **Integrar MegaDetector** no lugar/ao lado do YOLO atual (estágio 1).
2. **Plugar SpeciesNet** no recorte do MegaDetector (estágio 2) — validar com a imagem da cotia que o YOLO errou.
3. **Persistir em formato de treino** (recorte + label + score + versão).
4. **Conectar o Human Review** para confirmar/corrigir e alimentar o dataset.
5. **Refletir confiança/taxonomia** no Dashboard e nos Reports.
6. Só então otimizar infra (GPU, filas, dead-letter) e expandir features.

---

## 7. Stack consolidada (sem mudanças na fundação do PRD)

- **Detecção:** MegaDetector (via PyTorch-Wildlife)
- **Classificação:** SpeciesNet + AI4G Amazon Rainforest (TropiCam-AI para arbóreo)
- **Cloud:** S3, ECS Fargate (+ EC2 GPU a decidir), SQS, EventBridge, DynamoDB, CloudWatch, Terraform
- **Backend:** FastAPI
- **Frontend:** React/Next.js (Streamlit no MVP)
- **Taxonomia de referência:** Catalogue of Life

---

## 8. Próximos passos

1. Fechar as access patterns do DynamoDB (seção 5.1).
2. Detalhar o pipeline de eventos e a decisão GPU/CPU (5.2, 5.3).
3. Escrever critérios de aceite das features do miolo de IA (5.4).
4. Montar o `CLAUDE.md` do repositório com estas decisões.
5. Executar a fatia vertical da seção 6 no Claude Code.
