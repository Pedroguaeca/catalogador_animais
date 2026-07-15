// Cores de display_status compartilhadas entre /videos e o dropdown de
// vídeos do /review — um único lugar para não divergir a paleta entre as
// duas telas.
export function statusStyle(s: string | undefined): { bg: string; color: string } {
  if (s === "Revisado")           return { bg: "#EEF5F0", color: "#2F6B4F" };
  if (s === "Aguardando revisão") return { bg: "#FFF8EC", color: "#B45309" };
  if (s === "Sem detecção")       return { bg: "#EEF1F4", color: "#5B6B7A" };
  return                                  { bg: "#F1F0EE", color: "#6B6357" }; // Processando
}
