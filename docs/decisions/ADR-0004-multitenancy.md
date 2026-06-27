# ADR-0004 — Multitenancy: pool com isolamento por tenant_id, preparado desde o MVP

**Status:** Aceito | **Data:** Junho 2026

## Contexto
O SIAB será um SaaS para consultorias ambientais. Cada cliente (tenant) precisa ter seus
dados — vídeos, detecções, aparições, laudos — **isolados** dos demais. São dados de
compliance ambiental (vão a órgãos públicos), então a confidencialidade tem peso jurídico,
não só comercial.

O primeiro cliente será um **piloto com uma única consultoria**, com expansão para vários
clientes depois. Isso cria uma tensão: construir toda a máquina multitenant agora adiciona
complexidade a um MVP que ainda valida o core (detecção → identificação); mas tomar decisões
de modelagem que impeçam a multitenancy depois geraria reescrita cara.

Há ainda uma particularidade do SIAB: o diferencial é o **loop de dados**. Cada cliente deve
ver apenas seus próprios dados, mas o **modelo** deve poder aprender com o agregado de todos.
"Dado do cliente" e "aprendizado agregado" são coisas separadas e precisam ser tratadas como tal.

## Decisão
**Estratégia: pool com isolamento lógico por `tenant_id`, preparado desde o MVP mas sem
construir a operação multitenant completa antes de ser necessário.**

Concretamente:
1. **Toda entidade** do modelo de dados ganha `tenant_id` como primeira dimensão da chave de
   partição (ver data-model.md). Vale desde já, mesmo com um único tenant no piloto.
2. **Toda consulta** ao banco filtra obrigatoriamente por `tenant_id`. Sem exceção.
3. **S3** é particionado por prefixo de tenant (`s3://bucket/{tenant_id}/...`), com permissões
   que impedem um tenant de acessar o caminho de outro.
4. **Autenticação** (a definir, ex.: AWS Cognito) carrega o `tenant_id` do usuário; cada
   usuário só enxerga o seu tenant.
5. **Dados de treino** do loop são extraídos das revisões com o `tenant_id` registrado, mas o
   dataset agregado para fine-tuning é desacoplado da fronteira de visualização do cliente
   (o cliente não vê dados de outros; o modelo aprende com todos).

O que **NÃO** se constrói agora: billing por tenant, onboarding self-service, painel de
administração multi-cliente. Isso entra quando houver o segundo cliente.

## Justificativa
- "Pool" é mais simples de operar que "silo" (infra separada por cliente) e adequado ao
  estágio. O isolamento depende de disciplina de código — daí a regra de filtro obrigatório.
- Preparar as chaves agora é barato (modelo ainda no papel); refazê-las depois seria caro.
- Single-tenant no piloto evita complexidade prematura sem fechar portas.
- Separar dado-do-cliente de aprendizado-agregado protege o diferencial sem violar a
  confidencialidade.

## Consequências
- As access patterns do data-model.md passam a ser "dentro do tenant X, faça Y".
- A partition key das tabelas muda para incluir `tenant_id` (ver data-model atualizado).
- Surge uma nova dependência no roadmap: sistema de autenticação ciente de tenant.
- O pipeline precisa carregar o `tenant_id` de ponta a ponta (upload → aparição → revisão).
- Risco a vigiar: como o isolamento é lógico (não físico), um bug de filtro pode vazar dados
  entre tenants. Mitigação: centralizar o acesso a dados numa camada que sempre aplica o
  filtro, em vez de espalhar queries soltas pelo código.

## Evolução prevista: pool → silo

A migração de **pool** (banco compartilhado) para **silo** (infraestrutura dedicada por
tenant) é uma evolução esperada conforme o SIAB cresce. Gatilhos prováveis no mercado de
compliance ambiental:
- Cliente grande (mineradora, órgão público) exige isolamento físico por contrato.
- Exigência de conformidade/auditoria que peça separação mais forte que a lógica.
- "Vizinho barulhento": um tenant de alto volume degrada a performance dos demais.
- Necessidade de transparência de custo/faturamento por cliente.

Na prática isso costuma virar um **modelo misto**: poucos clientes grandes em silo, a maioria
em pool. Esta ADR assume pool agora, mas adota desde já dois princípios de design que mantêm
a porta do silo aberta a baixo custo:

1. **Camada única de acesso a dados.** Toda query passa por um mesmo ponto que resolve "onde
   moram os dados deste tenant?". No dia da migração, muda-se esse ponto — não cada query
   espalhada. (É a mesma camada que mitiga o risco de vazamento acima.)
2. **`tenant_id` como ponteiro de roteamento, não filtro fixo.** Em vez de `WHERE tenant_id = X`
   hardcoded, a lógica é "para o tenant X, descubra qual recurso usar". Hoje a resposta é
   sempre "o pool"; amanhã, para alguns, vira "o silo dele". O roteamento já nasce preparado.

O que **habilita** essa migração (e já está garantido): todo dado nasce com `tenant_id` na
chave e o S3 é particionado por prefixo de tenant. Extrair "tudo do tenant X" é uma operação
limpa porque a fronteira já está desenhada. O que **a impediria** seria espalhar `tenant_id`
cru por queries soltas — por isso o princípio 1 é inegociável desde o início.

**Decisão:** manter pool no MVP, mas projetar a camada de dados respeitando os dois princípios
acima, de modo que pool → silo seja evolução, não reescrita.
