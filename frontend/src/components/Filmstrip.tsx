"use client";

import { Check } from "lucide-react";
import type { Frame } from "../lib/types";

interface FilmstripProps {
  frames: Frame[];
  frameIdx: number; // 1-based
  onSelect: (idx: number) => void;
  // Fonte única do "revisado" — mesmo Set usado no selo do frame grande e no
  // painel "A IA sugere" (ReviewPage). Sem isso cada lugar podia divergir.
  annotatedFrames: Set<number>;
  // Espécie confirmada por frame (state.annotatedSpecies, ReviewPage) — não
  // dá pra usar frame.annotatedSpecies direto porque esse é só o valor do
  // fetch inicial; correções feitas nesta sessão vivem no reducer.
  annotatedSpecies: Record<number, string>;
}

const STATUS_COLOR: Record<string, string> = {
  review: "#E2A33C",
  empty: "#9A9080",
};

export function Filmstrip({ frames, frameIdx, onSelect, annotatedFrames, annotatedSpecies }: FilmstripProps) {
  const current = frames[frameIdx - 1];

  return (
    <div
      className="shrink-0 bg-white flex flex-col"
      style={{
        borderRadius: 14,
        boxShadow: "0 1px 2px rgba(34,31,26,0.04), 0 6px 20px rgba(34,31,26,0.05)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: "#EFE8DB" }}
      >
        <span
          className="text-xs font-semibold uppercase tracking-widest"
          style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}
        >
          Frames do Vídeo
        </span>
        <span
          className="text-xs"
          style={{ color: "#B0A893", fontFamily: "IBM Plex Sans, sans-serif" }}
        >
          <span className="font-semibold" style={{ color: "#6B6357" }}>
            {frameIdx}
          </span>{" "}
          de {frames.length}
        </span>
      </div>

      {/* Tira de miniaturas */}
      <div className="overflow-x-auto flex gap-2 p-3">
        {frames.map((f, i) => {
          const isActive = f.idx === frameIdx;
          const isAnnotated = annotatedFrames.has(f.idx);
          // Label por PRESENÇA de espécie (SIAB-104), não confiança — frame
          // sem espécie às vezes tem confiança maior que frame com espécie,
          // e é a espécie que importa pro revisor escolher pra onde ir.
          // Confirmada tem prioridade sobre a sugestão da IA (mesmo frame
          // pode ter as duas depois de uma correção).
          const confirmedSpecies = annotatedSpecies[f.idx];
          const aiSuggestion = f.detection?.genus_pt;
          const label = confirmedSpecies || aiSuggestion || null;
          return (
            <div key={f.idx} className="shrink-0 flex flex-col gap-1" style={{ width: 96 }}>
              <button
                onClick={() => onSelect(f.idx)}
                className="relative shrink-0 focus:outline-none transition-opacity"
                style={{
                  width: 96,
                  height: 54,
                  borderRadius: 9,
                  opacity: isActive ? 1 : 0.78,
                  outline: isActive ? "2px solid #3E8E63" : "none",
                  outlineOffset: isActive ? 2 : 0,
                  boxShadow: isActive ? "0 0 0 4px rgba(62,142,99,0.15)" : "none",
                  overflow: "hidden",
                  background: "#1A1E1A",
                }}
              >
                <img
                  src={f.imageUrl ?? `/api/image?p=${encodeURIComponent(f.path)}`}
                  alt={`Frame ${f.idx}`}
                  className="w-full h-full"
                  style={{ objectFit: "cover" }}
                />
                {/* Número do frame — sup esq */}
                <span
                  className="absolute top-1 left-1 text-white font-medium leading-none"
                  style={{
                    fontSize: 9,
                    background: "rgba(0,0,0,0.55)",
                    borderRadius: 4,
                    padding: "1px 4px",
                  }}
                >
                  {f.idx}
                </span>
                {/* Selo de revisado — inf dir. Peso visual consistente com o
                    selo do frame grande (mesmo ✓, mesma cor), em vez do ponto
                    verde discreto que só um olho treinado notava. */}
                {isAnnotated ? (
                  <span
                    className="absolute bottom-1 right-1 flex items-center justify-center rounded-full"
                    style={{ width: 15, height: 15, background: "#2D8B5F", boxShadow: "0 0 0 1.5px rgba(0,0,0,0.35)" }}
                  >
                    <Check size={10} color="#fff" strokeWidth={3} />
                  </span>
                ) : (
                  <span
                    className="absolute bottom-1 right-1 rounded-full"
                    style={{
                      width: 7,
                      height: 7,
                      // f.status "detection" sem estar em annotatedFrames não deveria
                      // acontecer (annotatedFrames é semeado a partir dele) — "review"
                      // como fallback seguro.
                      background: STATUS_COLOR[f.status ?? "empty"] ?? STATUS_COLOR.review,
                      boxShadow: "0 0 0 1.5px rgba(0,0,0,0.4)",
                    }}
                  />
                )}
              </button>
              {/* Label de espécie — confirmada (sólido, verde) ou sugestão da
                  IA ainda não confirmada (itálico, cor neutra). Altura fixa
                  mesmo vazio, pra miniaturas não pularem de posição. */}
              <span
                className="text-center leading-tight truncate"
                style={{
                  fontSize: 9.5,
                  height: 12,
                  fontFamily: "IBM Plex Sans, sans-serif",
                  fontStyle: confirmedSpecies ? "normal" : "italic",
                  fontWeight: confirmedSpecies ? 600 : 400,
                  color: confirmedSpecies ? "#2D8B5F" : "#9A9080",
                }}
                title={label ?? undefined}
              >
                {label ?? ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
