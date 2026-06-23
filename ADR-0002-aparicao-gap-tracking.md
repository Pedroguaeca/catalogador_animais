# ADR-0002 — Unidade "Aparição": gap temporal no MVP, tracking na V1

**Status:** Aceito | **Data:** Junho 2026

## Contexto
Um vídeo gera milhares de frames; persistir cada detecção produziria milhões de registros
de baixo valor. O objetivo de negócio é registrar **aparições únicas de indivíduos**: uma
cotia entra, fica, sai = 1 registro; outra cotia depois = novo registro.

O desafio é separar aparições quando a espécie é a mesma. Três abordagens:
- **Gap temporal**: nova aparição após X tempo sem detecção da espécie. Simples,
  pós-processamento, sem GPU. Erra na super/subcontagem no limiar.
- **Tracking**: segue o indivíduo frame a frame. Conta indivíduos de verdade. Exige
  componente novo (tracker), processamento sequencial, idealmente GPU. Erros próprios
  (oclusão, troca de identidade).
- **Re-ID visual**: fora de escopo de MVP.

## Decisão
- Entidade central de registro = **Aparição**, consolidando detecções (não frames).
- **MVP usa gap temporal**, com `GAP` configurável por projeto.
- **Tracking entra na V1.**
- O modelo de dados da Aparição comporta ambos; muda só como os campos são preenchidos e a
  confiança da contagem de indivíduos.

## Justificativa
- Gap destrava o produto rápido e valida o pipeline inteiro sem complexidade de tracking.
- O Human Review cobre a fraqueza do gap (analista corrige a contagem) — e essa correção
  vira dado de treino.
- Tracking entra quando houver volume, infra de GPU resolvida e evidência (pelas correções)
  de quanto o gap erra — decisão baseada em dados, não no escuro.

## Consequências
- Volume de registros cai de milhões para dezenas/centenas por vídeo.
- Métrica de biodiversidade melhora (conta aparições, não frames).
- `individual_count` = 1 no MVP, corrigível pelo analista.
- Migração para tracking não exige reescrever o modelo de dados.
