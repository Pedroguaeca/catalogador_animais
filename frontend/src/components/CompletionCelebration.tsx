"use client";

import { Check } from "lucide-react";

// Micro-interação não-intrusiva mostrada só quando um vídeo INTEIRO passa de
// "aguardando revisão" para "revisado" — não a cada frame confirmado.
// Sempre montado; controlado por CSS transition via `active`, sem exigir
// clique para dispensar e sem bloquear o fluxo (pointer-events: none).
export function CompletionCelebration({ active }: { active: boolean }) {
  return (
    <div
      aria-hidden
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{ pointerEvents: "none" }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: "50%",
          background: "#2D8B5F",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 8px 28px rgba(45,139,95,0.4)",
          opacity: active ? 1 : 0,
          transform: active ? "scale(1)" : "scale(0.55)",
          transition: "opacity 220ms ease, transform 220ms cubic-bezier(0.34, 1.56, 0.64, 1)",
        }}
      >
        <Check size={34} color="#fff" strokeWidth={3} />
      </div>
    </div>
  );
}
