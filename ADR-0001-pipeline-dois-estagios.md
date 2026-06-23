# ADR-0001 — Pipeline de dois estágios em vez de YOLO genérico

**Status:** Aceito | **Data:** Junho 2026

## Contexto
O MVP inicial usava YOLO genérico. Teste prático mostrou que ele detecta a presença de
animal mas não identifica a espécie (ex.: cotia), por não ter fine-tuning para fauna
brasileira. Um teste paralelo com API de LLM (GPT) identificou a espécie, revelando que o
problema é de **classificação**, não de **detecção**.

## Decisão
Adotar o pipeline de dois estágios, padrão da indústria de câmera-trap:
1. **Detecção** — MegaDetector (open-source, Microsoft, MIT): localiza animais e filtra
   frames vazios.
2. **Classificação** — SpeciesNet (Google, Apache 2.0, ~2.000 espécies) + AI4G Amazon
   Rainforest, via PyTorch-Wildlife.

Não usar API de LLM como classificador de produção.

## Justificativa
- LLM em produção: custo por frame (vídeo = milhares), sem score calibrado, sem taxonomia
  hierárquica, risco de alucinação — inaceitável para laudos EIA/RIMA.
- Modelos de câmera-trap: rodam na própria AWS sem custo por imagem, score calibrado,
  taxonomia em múltiplos níveis, validação peer-reviewed.
- SpeciesNet tem licença que permite uso comercial e fine-tuning futuro.

## Consequências
- Feature "Fauna Detection" do PRD passa a ser MegaDetector + SpeciesNet/AI4G.
- O LLM permanece útil só como ferramenta de diagnóstico/exploração, não de produção.
- Abre caminho para o loop de dados (ADR-0002) e modelo proprietário via fine-tuning.
