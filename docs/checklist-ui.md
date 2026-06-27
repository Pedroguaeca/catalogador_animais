# Checklist de Teste Manual — Interface SIAB

Execute estes testes com o servidor dev rodando (`npm run dev` na pasta `frontend/`).

---

## 0. Pré-condições

- [ ] Pipeline rodado (`python main.py`) → CSV gerado em `resultados/catalogo_animais.csv`
- [ ] Frames presentes em `frames/<genero>/`
- [ ] Frontend rodando em http://localhost:3000
- [ ] Nenhum erro no console do navegador (F12 → Console)

---

## 1. Tela de Revisão — Carregamento

- [ ] **Vídeos carregam:** a tela mostra o primeiro frame do primeiro vídeo sem erro
- [ ] **TopBar:** exibe "Frame 1/N · Vídeo 1/M · 0 anotados"
- [ ] **Seletor de vídeo:** dropdown mostra todos os IDs de vídeo do CSV
- [ ] **Empty state:** se CSV não existir, a página mostra mensagem de "Nenhum vídeo encontrado"

---

## 2. Frame Stage — Imagem e Bounding Box

- [ ] **Frame visível:** imagem do animal aparece no painel central
- [ ] **Bounding box:** retângulo colorido desenhado sobre o animal
  - Verde → det_conf ≥ 0.7
  - Laranja → 0.4 ≤ det_conf < 0.7
  - Cinza → det_conf < 0.4
- [ ] **Label do bbox:** mostra gênero + confiança (ex: "Dasyprocta 0.91")
- [ ] **Letterboxing:** imagem com `object-fit: contain` — bbox permanece alinhado ao animal mesmo com barras laterais/superior

---

## 3. Painel de Identificação

- [ ] **Chip de sugestão IA:** mostra gênero detectado em PT (ex: "Cutia") + confiança
- [ ] **Pills de categorias:** todas as espécies listadas são clicáveis
- [ ] **Filtro de busca:** digitar "cut" filtra para "Cutia"
- [ ] **Confirmar IA:** botão verde "Confirmar Cutia" aplica a anotação
- [ ] **Rejeitar:** botão "Rejeitar" desmarca a sugestão sem salvar
- [ ] **Nova categoria:** campo de texto permite adicionar espécie nova e ela aparece nas pills
- [ ] **Contagem de anotados:** incrementa após confirmar ou selecionar pill

---

## 4. Navegação

- [ ] **Frame seguinte (→):** avança para o próximo frame do mesmo vídeo
- [ ] **Frame anterior (←):** volta para o frame anterior
- [ ] **Vídeo seguinte:** carrega o primeiro frame do vídeo seguinte
- [ ] **Vídeo anterior:** carrega o primeiro frame do vídeo anterior
- [ ] **Botões desabilitados:** "Frame anterior" desabilitado no frame 1; "Vídeo anterior" desabilitado no vídeo 1
- [ ] **Filmstrip:** miniaturas na parte inferior; clicar numa miniatura vai direto para aquele frame
- [ ] **Seletor de vídeo (dropdown):** selecionar vídeo diferente carrega frame 1 daquele vídeo

---

## 5. Atalhos de Teclado

- [ ] **Enter:** confirma sugestão da IA e avança frame
- [ ] **→ (seta direita):** frame seguinte
- [ ] **← (seta esquerda):** frame anterior
- [ ] **S:** pula frame sem anotar

---

## 6. Upload de Vídeos

- [ ] **Botão "Adicionar vídeos":** abre modal de upload
- [ ] **Drag & drop:** arrastar arquivo de vídeo para a zona pontilhada adiciona à fila
- [ ] **Seletor de arquivo:** clicar na zona abre o file picker nativo
- [ ] **Múltiplos arquivos:** adicionar 2+ vídeos exibe todos na lista
- [ ] **Formatos aceitos:** MP4, AVI, MOV, MKV, WebM — outros formatos devem ser rejeitados ou exibir erro
- [ ] **Progresso por arquivo:** barra de progresso individual durante upload
- [ ] **Status por arquivo:** ícone muda (pendente → enviando → concluído / erro)
- [ ] **Botão "Processar vídeos":** aparece somente após upload bem-sucedido
- [ ] **Log do pipeline:** caixa preta mostra output do `main.py` em tempo real (SSE)
- [ ] **Linhas coloridas no log:** verde ✅, vermelho ❌, amarelo ⚠
- [ ] **Botão "Ir para revisão":** aparece ao final com pipeline concluído; fecha modal e recarrega frames

---

## 7. Responsividade e Aparência

- [ ] **Sem scroll vertical:** toda a UI cabe na viewport (1280×800 mínimo)
- [ ] **Cores corretas:** background #FAF6EE, primário #2F6B4F, destaque #E2A33C
- [ ] **Fontes:** Libre Franklin nos títulos, IBM Plex Sans no corpo
- [ ] **Sem overflow de texto:** nomes de arquivos longos truncados com reticências
- [ ] **Sem erros de layout em viewport menor:** testar em 1024×768

---

## 8. Regressão

- [ ] Anotar frame 1, navegar para frame 2 e voltar → frame 1 ainda mostra a anotação confirmada
- [ ] Recarregar a página → contador de anotados volta a 0 (estado é client-side, não persistido no servidor)
- [ ] Abrir e fechar o modal de upload sem selecionar arquivos → nenhum erro no console
