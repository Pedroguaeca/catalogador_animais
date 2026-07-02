#!/usr/bin/env bash
# scripts/run_dev.sh — Sobe API FastAPI + frontend Next.js juntos.
#
# Uso: bash scripts/run_dev.sh
#
# Pressione Ctrl+C para encerrar ambos os processos.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  echo ""
  echo "Encerrando…"
  kill "$API_PID" "$NEXT_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

cd "$ROOT"

# ── API FastAPI ────────────────────────────────────────────────────────────────
echo "→ Subindo API FastAPI em http://localhost:8000 …"
uvicorn backend.api:app --reload --port 8000 &
API_PID=$!

# ── Frontend Next.js ───────────────────────────────────────────────────────────
echo "→ Subindo frontend Next.js em http://localhost:3000 …"
cd "$ROOT/frontend" && npm run dev &
NEXT_PID=$!

echo ""
echo "  API      → http://localhost:8000"
echo "  Docs API → http://localhost:8000/docs"
echo "  Frontend → http://localhost:3000"
echo ""
echo "  Upload   → http://localhost:3000/upload"
echo "  Revisão  → http://localhost:3000/review"
echo "  Exportar → http://localhost:3000/export"
echo ""
echo "  Pressione Ctrl+C para encerrar."
echo ""

wait
