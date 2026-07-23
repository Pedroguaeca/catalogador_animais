"use client";

import { useEffect, useState } from "react";
import { X, Minus, Plus, ChevronRight } from "lucide-react";
import type { VideoSegment } from "../lib/types";

export interface CheckoutValues {
  species:         string;
  segment:         number;
  individualCount: number;
  temFilhote:      boolean;
}

interface CheckoutModalProps {
  open: boolean;
  segments: VideoSegment[];
  onClose: () => void;
  onConfirm: (values: CheckoutValues[]) => void;
}

const font = { fontFamily: "IBM Plex Sans, sans-serif" };

// Modal de checkout ao concluir um vídeo — 1 card por segmento, com
// indivíduos pré-preenchido com o maior valor marcado em qualquer frame do
// segmento e "tem filhote(s)" pré-marcado se qualquer frame tiver isso
// marcado. Ambos editáveis. Substitui a celebração direta (que agora dispara
// só depois de "Concluir").
export function CheckoutModal({ open, segments, onClose, onConfirm }: CheckoutModalProps) {
  const [values, setValues] = useState<Record<string, CheckoutValues>>({});

  useEffect(() => {
    if (!open) return;
    const seed: Record<string, CheckoutValues> = {};
    for (const s of segments) {
      seed[`${s.species}#${s.segment}`] = {
        species: s.species,
        segment: s.segment,
        individualCount: s.individual_count,
        temFilhote: s.tem_filhote,
      };
    }
    setValues(seed);
  }, [open, segments]);

  if (!open) return null;

  const update = (key: string, patch: Partial<CheckoutValues>) => {
    setValues((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(34,31,26,0.45)" }}
    >
      <div
        className="flex flex-col bg-white"
        style={{
          width: 480,
          maxHeight: "85vh",
          borderRadius: 18,
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
          overflow: "hidden",
        }}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: "#EFE8DB" }}>
          <div>
            <p className="font-semibold" style={{ fontSize: 16, color: "#221F1A", ...font }}>
              Confirmar aparições do vídeo
            </p>
            <p className="text-xs mt-0.5" style={{ color: "#9A9080", ...font }}>
              Revise a quantidade de indivíduos antes de concluir.
            </p>
          </div>
          <button onClick={onClose} style={{ color: "#9A9080" }} title="Voltar e revisar de novo">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
          {segments.map((s) => {
            const key = `${s.species}#${s.segment}`;
            const v = values[key];
            if (!v) return null;
            return (
              <div
                key={key}
                className="flex items-center justify-between gap-3 p-3"
                style={{ border: "1.5px solid #E7DECF", borderRadius: 12 }}
              >
                <div className="min-w-0">
                  <p className="font-semibold truncate" style={{ fontSize: 14, color: "#221F1A", ...font }}>
                    {s.species}
                  </p>
                  <p className="text-xs" style={{ color: "#9A9080", ...font }}>
                    frames {s.frame_start}–{s.frame_end} · {s.frame_count} confirmados
                  </p>
                  <label
                    className="flex items-center gap-1.5 text-xs mt-1.5 cursor-pointer select-none"
                    style={{ color: "#6B6357", ...font }}
                  >
                    <input
                      type="checkbox"
                      checked={v.temFilhote}
                      onChange={(e) => update(key, { temFilhote: e.target.checked })}
                      style={{ accentColor: "#2D8B5F", width: 13, height: 13 }}
                    />
                    Tem filhote(s)
                  </label>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => update(key, { individualCount: Math.max(1, v.individualCount - 1) })}
                    disabled={v.individualCount <= 1}
                    className="flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
                    style={{ width: 26, height: 26, borderRadius: 7, border: "1.5px solid #E7DECF", color: "#6B6357" }}
                  >
                    <Minus size={12} />
                  </button>
                  <span className="text-center font-semibold" style={{ width: 24, fontSize: 14, color: "#221F1A", ...font }}>
                    {v.individualCount}
                  </span>
                  <button
                    onClick={() => update(key, { individualCount: v.individualCount + 1 })}
                    className="flex items-center justify-center"
                    style={{ width: 26, height: 26, borderRadius: 7, border: "1.5px solid #E7DECF", color: "#6B6357" }}
                  >
                    <Plus size={12} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        <div className="px-5 py-4 border-t shrink-0" style={{ borderColor: "#EFE8DB" }}>
          <button
            onClick={() => onConfirm(Object.values(values))}
            className="w-full flex items-center justify-center gap-1.5 font-semibold"
            style={{
              padding: "12px 18px", borderRadius: 11,
              background: "#2D8B5F", color: "#fff",
              fontSize: 14, ...font,
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#256E4B")}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#2D8B5F")}
          >
            Concluir e ir pro próximo vídeo
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
