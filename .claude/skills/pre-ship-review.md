# Pre-ship Review

Roda os 3 subagentes de qualidade do SIAB em sequência e consolida o resultado num relatório único antes de qualquer deploy ou merge.

## Quando usar

```
/pre-ship-review
```

Rode antes de:
- Abrir um PR com mudanças em `backend/api.py` (novos endpoints, auth, queries DynamoDB)
- Fazer deploy de uma nova versão da imagem ECR do `siab-api` Lambda
- Adicionar uma nova tabela DynamoDB ou índice GSI
- Qualquer mudança no fluxo de autenticação (NextAuth config, Cognito triggers, JWT handling)

## O que roda

### 1. security-reviewer
Varre todos os endpoints FastAPI e componentes frontend verificando:
- JWT validado com assinatura (não só decodificado)
- `get_current_tenant()` em todos os endpoints protegidos
- Toda query DynamoDB filtra por `tenant_id` do JWT
- Inputs validados via Pydantic
- Sem dados sensíveis em logs/erros

### 2. prd-validator
Compara a implementação atual contra `docs/PRD.md`:
- Jornada completa (upload → pipeline → revisão → dashboard → export)
- Features especificadas mas não implementadas
- Comportamentos divergentes da spec

### 3. test-writer (modo análise)
Identifica gaps de cobertura de testes sem escrever nada ainda:
- Endpoints sem testes de autenticação
- Cenários de tenant isolation não testados
- Casos extremos descobertos pelos outros dois agentes que precisam de teste

## Formato do relatório consolidado

```
# Pre-Ship Review — SIAB
Data: YYYY-MM-DD
Commit: (git log --oneline -1)

## Segurança
[resultado do security-reviewer]

## Conformidade com PRD
[resultado do prd-validator]

## Cobertura de testes
[resultado do test-writer em modo análise]

## Resumo executivo
- 🔴 Críticos (bloqueiam ship): N itens
- ⚠️  Importantes (resolver em breve): N itens
- ✅ OK: N itens

## Decisão recomendada
SHIP / NÃO SHIP / SHIP COM RESSALVAS
```

## Instrução para o Claude

Quando o usuário invocar `/pre-ship-review`:

1. Leia o estado atual do git: `git log --oneline -5` e `git diff HEAD~1 --stat`
2. Lance o security-reviewer contra o codebase completo (não só o diff)
3. Lance o prd-validator lendo `docs/PRD.md` e comparando com o código
4. Lance o test-writer em modo análise (identificar gaps, não escrever testes ainda)
5. Consolide os três relatórios no formato acima
6. Se houver 🔴 críticos: recomende NÃO SHIP até corrigir
7. Se houver só ⚠️: recomende SHIP COM RESSALVAS listando o que precisa de follow-up
