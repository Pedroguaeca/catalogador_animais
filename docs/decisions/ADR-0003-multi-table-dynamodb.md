# ADR-0003 — Multi-table no DynamoDB no MVP

**Status:** Aceito | **Data:** Junho 2026

## Contexto
DynamoDB idiomático favorece single-table design (todas as entidades numa tabela,
otimizada pelas access patterns) — mais performático e barato, porém mais difícil de
entender e evoluir. O SIAB é um MVP que ainda vai mudar muito e tem domínios futuros
(drones, satélites, flora) não totalmente definidos.

## Decisão
Usar **multi-table** (uma tabela por entidade principal: projects, videos, appearances,
reviews, species) no MVP.

## Justificativa
- Flexibilidade e clareza importam mais que otimização extrema nesta fase.
- Access patterns ainda podem mudar com o produto; multi-table absorve mudança melhor.
- Performance/custo de single-table só compensa quando os padrões estabilizam.

## Consequências
- Algumas consultas exigem mais de uma leitura (aceitável no volume do MVP).
- Reavaliar migração para single-table quando os access patterns estabilizarem e o volume
  justificar a otimização.
