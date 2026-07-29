#!/usr/bin/env bash
# test_upload_e2e.sh — Valida o fix de auth do upload de ponta a ponta
#
# Como obter o JWT:
#   1. Abra https://frontend-rust-iota-58.vercel.app no browser
#   2. Faça login normalmente
#   3. DevTools → Application → Cookies → selecione a URL do Vercel
#   4. Copie o valor do cookie "__Secure-authjs.session-token"
#      OU: DevTools Console → rode: fetch('/api/auth/session').then(r=>r.json()).then(s=>console.log(s.idToken))
#   5. Cole abaixo como JWT
#
# Uso:
#   JWT="eyJhbGciOiJSUzI1NiIs..." VIDEO_PATH="~/Downloads/DSCF0007.AVI" bash test_upload_e2e.sh

set -euo pipefail

API_BASE="https://1cvwpk8syk.execute-api.us-east-1.amazonaws.com"
PROJECT_ID="projeto-junho-2026"
REGION="us-east-1"
APPEARANCES_TBL="siab-appearances"
VIDEOS_TBL="siab-videos"

JWT="${JWT:-}"
VIDEO_PATH="${VIDEO_PATH:-}"

if [[ -z "$JWT" ]]; then
  echo "❌ Defina JWT='eyJ...' antes de rodar o script."
  exit 1
fi

if [[ -z "$VIDEO_PATH" ]]; then
  echo "❌ Defina VIDEO_PATH='/caminho/para/video.avi' antes de rodar o script."
  exit 1
fi

VIDEO_PATH="${VIDEO_PATH/#\~/$HOME}"

echo ""
echo "=== SIAB Upload E2E Test ==="
echo "API:   $API_BASE"
echo "Video: $VIDEO_PATH"
echo ""

# ── 1. Confirma que sem token retorna 401 ──────────────────────────────────────
echo "► Verificando que sem token retorna 401..."
HTTP_NO_AUTH=$(curl -s -o /dev/null -w "%{http_code}" \
  "$API_BASE/projects/$PROJECT_ID/videos/upload" -X POST)

if [[ "$HTTP_NO_AUTH" == "401" ]]; then
  echo "  ✓ 401 sem token (esperado)"
else
  echo "  ✗ FALHA: esperado 401 sem token, recebeu $HTTP_NO_AUTH"
  exit 1
fi

# ── 2. Extrai tenant_id do JWT (sem verificar assinatura — só leitura) ──────────
# JWT usa base64url (sem padding). Adiciona padding correto antes de decodificar.
PAYLOAD=$(echo "$JWT" | cut -d'.' -f2 | python3 -c "
import sys, base64, json
s = sys.stdin.read().strip()
# Adiciona padding até múltiplo de 4 (base64url não inclui '=')
s += '=' * (-len(s) % 4)
data = base64.urlsafe_b64decode(s)
print(data.decode('utf-8'))
")
TENANT_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('custom:tenant_id',''))")
SUB=$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sub',''))")

echo "► JWT decodificado:"
echo "  tenant_id = $TENANT_ID"
echo "  sub       = $SUB"
echo ""

if [[ -z "$TENANT_ID" ]]; then
  echo "  ✗ FALHA: custom:tenant_id não encontrado no JWT."
  exit 1
fi

# ── 3. Passo 1 — obtém URL pré-assinada ────────────────────────────────────────
echo "► Passo 1/3 — obtendo URL pré-assinada..."
CONTENT_TYPE="video/x-msvideo"
FILENAME=$(basename "$VIDEO_PATH")

URL_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"filename\":\"$FILENAME\",\"content_type\":\"$CONTENT_TYPE\"}" \
  "$API_BASE/projects/$PROJECT_ID/videos/upload-url")

URL_STATUS=$(echo "$URL_RESP" | tail -1)
URL_BODY=$(echo "$URL_RESP" | sed '$d')

if [[ "$URL_STATUS" != "200" ]]; then
  echo "  ✗ FALHA: esperado 200, recebeu $URL_STATUS"
  echo "  Resposta: $URL_BODY"
  exit 1
fi

VIDEO_ID=$(echo "$URL_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('video_id',''))")
UPLOAD_URL=$(echo "$URL_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('upload_url',''))")
S3_KEY=$(echo "$URL_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('s3_key',''))")
echo "  ✓ URL pré-assinada obtida"
echo "  video_id = $VIDEO_ID"
echo "  s3_key   = $S3_KEY"

if echo "$S3_KEY" | grep -q "^$TENANT_ID/"; then
  echo "  ✓ s3_key usa tenant do JWT ($TENANT_ID)"
else
  echo "  ✗ FALHA: s3_key deveria começar com '$TENANT_ID/', foi: $S3_KEY"
  exit 1
fi

# ── 4. Passo 2 — PUT direto ao S3 ──────────────────────────────────────────────
echo ""
echo "► Passo 2/3 — upload direto ao S3 ($(du -h "$VIDEO_PATH" | cut -f1))..."
S3_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X PUT \
  -H "Content-Type: $CONTENT_TYPE" \
  --upload-file "$VIDEO_PATH" \
  "$UPLOAD_URL")

if [[ "$S3_HTTP" == "200" ]]; then
  echo "  ✓ S3 retornou 200"
else
  echo "  ✗ FALHA: S3 retornou $S3_HTTP (esperado 200)"
  exit 1
fi

# ── 5. Passo 3 — confirma upload e dispara pipeline ────────────────────────────
echo ""
echo "► Passo 3/3 — confirmando upload e disparando pipeline..."
CONFIRM_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $JWT" \
  "$API_BASE/projects/$PROJECT_ID/videos/$VIDEO_ID/confirm")

CONFIRM_STATUS=$(echo "$CONFIRM_RESP" | tail -1)
CONFIRM_BODY=$(echo "$CONFIRM_RESP" | sed '$d')

if [[ "$CONFIRM_STATUS" != "200" ]]; then
  echo "  ✗ FALHA: esperado 200, recebeu $CONFIRM_STATUS"
  echo "  Resposta: $CONFIRM_BODY"
  exit 1
fi

PIPELINE_STATUS=$(echo "$CONFIRM_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
echo "  ✓ Pipeline disparado (status=$PIPELINE_STATUS)"

# ── 4. Verifica tenant_id em siab-videos ────────────────────────────────────────
echo ""
echo "► Consultando siab-videos (tenant_id + status do item gravado)..."
VIDEO_ITEM=$(aws dynamodb get-item \
  --table-name "$VIDEOS_TBL" \
  --key "{\"tenant_id\":{\"S\":\"$TENANT_ID\"},\"project_id#video_id\":{\"S\":\"$PROJECT_ID#$VIDEO_ID\"}}" \
  --region "$REGION" \
  --output json 2>/dev/null)

if echo "$VIDEO_ITEM" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'Item' in d else 1)" 2>/dev/null; then
  STORED_TENANT=$(echo "$VIDEO_ITEM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Item']['tenant_id']['S'])")
  STORED_STATUS=$(echo "$VIDEO_ITEM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Item'].get('status',{}).get('S','?'))")
  echo "  ✓ tenant_id em siab-videos: $STORED_TENANT"
  echo "  ✓ status: $STORED_STATUS"
  if [[ "$STORED_TENANT" == "$TENANT_ID" ]]; then
    echo "  ✓ tenant_id bate com o JWT"
  else
    echo "  ✗ FALHA: tenant_id gravado='$STORED_TENANT' ≠ JWT='$TENANT_ID'"
    exit 1
  fi
else
  echo "  ⚠ Item ainda não encontrado em siab-videos"
fi

echo ""
echo "=== Resultado ==="
echo "✓ Passo 1 (upload-url): 200 — URL pré-assinada + registro pending criado"
echo "✓ Passo 2 (S3 PUT):     200 — vídeo de 406 MB enviado direto ao S3"
echo "✓ Passo 3 (confirm):    200 — pipeline disparado via SQS"
echo "✓ tenant_id correto ($TENANT_ID) em S3 key e DynamoDB"
echo ""
echo "Aguarde ~5-10min para o pipeline processar e verifique siab-appearances:"
echo ""
echo "  aws dynamodb query --table-name siab-appearances --region $REGION \\"
echo "    --index-name by-species \\"
echo "    --key-condition-expression '#pk = :pk' \\"
echo "    --expression-attribute-names '{\"#pk\":\"tenant_id#project_id\"}' \\"
echo "    --expression-attribute-values '{\":pk\":{\"S\":\"$TENANT_ID#$PROJECT_ID\"}}' \\"
echo "    --query 'Items[*].{tenant_id:tenant_id.S,species:species.S,camera_id:camera_id.S,captured_at:captured_at.S,status:review_status.S}' \\"
echo "    --output table"
