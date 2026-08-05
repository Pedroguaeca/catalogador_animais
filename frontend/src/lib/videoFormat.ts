export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    }).format(new Date(iso));
  } catch { return iso; }
}

// confidence vem 0–1 do backend; null quando não há dado (Processando/Sem
// detecção) — nunca coagir com `?? 0`, colapsaria com confiança 0% real.
export function formatConfidence(confidence: number | null): string {
  if (confidence === null) return "—";
  return `${Math.round(confidence * 100)}%`;
}
