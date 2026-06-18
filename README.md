# SIAB — Sistema de Inteligência Ambiental e Biodiversidade

Plataforma de inteligência ambiental e compliance de biodiversidade. O MVP monitora fauna a
partir de vídeos de câmeras-trap: detecta animais, identifica espécie, consolida aparições
únicas e gera evidências auditáveis para laudos ambientais.

## Documentação
| Arquivo | Conteúdo |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | Resumo do projeto lido pelo Claude Code a cada sessão |
| [`docs/PRD.md`](./docs/PRD.md) | Visão de produto, JTBD, funcionalidades, roadmap |
| [`docs/architecture.md`](./docs/architecture.md) | Arquitetura técnica e stack |
| [`docs/data-model.md`](./docs/data-model.md) | Modelo de dados (DynamoDB) e access patterns |
| [`docs/pipeline.md`](./docs/pipeline.md) | Pipeline de processamento de vídeo |
| [`docs/decisions/`](./docs/decisions/) | ADRs — registros de decisões de arquitetura |

## Abordagem técnica em uma frase
Pipeline de dois estágios (MegaDetector → SpeciesNet/AI4G), consolidando detecções em
**Aparições** únicas, com Human Review que alimenta um dataset proprietário de fauna brasileira.

## Estrutura sugerida do repositório
```
.
├── CLAUDE.md
├── README.md
├── docs/
│   ├── PRD.md
│   ├── architecture.md
│   ├── data-model.md
│   ├── pipeline.md
│   └── decisions/
│       ├── ADR-0001-pipeline-dois-estagios.md
│       ├── ADR-0002-aparicao-gap-tracking.md
│       └── ADR-0003-multi-table-dynamodb.md
├── src/            # código (a criar)
├── tests/
└── infra/          # Terraform (a criar)
```

## Estado atual
MVP de detecção existe (YOLO genérico) e será substituído pelo pipeline de dois estágios.
Próximo passo: fatia vertical — MegaDetector → SpeciesNet → persistência da Aparição → Human Review.
