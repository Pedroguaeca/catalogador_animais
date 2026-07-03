"use client";

import { useRef, useEffect } from "react";
import { Search, X, Sparkles, Check, ChevronLeft, ChevronRight, SkipForward, Film } from "lucide-react";
import type { Detection, Category } from "../lib/types";

interface IdentificationPanelProps {
  detection: Detection | null;
  categories: Category[];
  query: string;
  selected: string | null;
  confirmed: boolean;
  newCatOpen: boolean;
  newCatName: string;
  frameIdx: number;
  totalFrames: number;
  onQuery: (q: string) => void;
  onSelect: (id: string) => void;
  onConfirmAI: () => void;
  onConfirmVideo: () => void;
  onReject: () => void;
  onPrevFrame: () => void;
  onNextFrame: () => void;
  onSkipFrame: () => void;
  onOpenNewCat: () => void;
  onCloseNewCat: () => void;
  onNewCatName: (name: string) => void;
  onAddCategory: (name: string) => void;
}

export function IdentificationPanel({
  detection,
  categories,
  query,
  selected,
  confirmed,
  newCatOpen,
  newCatName,
  frameIdx,
  totalFrames,
  onQuery,
  onSelect,
  onConfirmAI,
  onConfirmVideo,
  onReject,
  onPrevFrame,
  onNextFrame,
  onSkipFrame,
  onOpenNewCat,
  onCloseNewCat,
  onNewCatName,
  onAddCategory,
}: IdentificationPanelProps) {
  const newCatInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (newCatOpen) newCatInputRef.current?.focus();
  }, [newCatOpen]);

  const filtered = query
    ? categories.filter((c) =>
        c.name.toLowerCase().includes(query.toLowerCase())
      )
    : categories;

  const aiPt = detection?.genus_pt ?? null;
  const aiGenus = detection?.genus ?? null;
  const confidence = detection ? Math.round(detection.cls_conf * 100) : 0;

  const aiCategoryId = categories.find(
    (c) => c.name.toLowerCase() === aiPt?.toLowerCase()
  )?.id ?? null;

  const font = { fontFamily: "IBM Plex Sans, sans-serif" };
  const labelStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.1em",
    color: "#9A9080",
    ...font,
  };

  return (
    <div
      className="flex flex-col bg-white shrink-0"
      style={{
        width: 386,
        borderRadius: 16,
        boxShadow: "0 1px 2px rgba(34,31,26,0.04), 0 6px 20px rgba(34,31,26,0.05)",
        overflow: "hidden",
      }}
    >
      {/* ── Cartão IA ──────────────────────────────────── */}
      <div className="px-4 pt-4 pb-3 shrink-0">
        <div
          className="p-3.5 flex flex-col gap-2.5"
          style={{
            background: "#EEF5F0",
            border: "1px solid #CDE3D6",
            borderRadius: 13,
          }}
        >
          {/* Label + conf */}
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5" style={labelStyle}>
              <Sparkles size={11} style={{ color: "#2F6B4F" }} />
              A IA sugere
            </span>
            {detection && (
              <span
                className="text-xs font-semibold px-2 py-0.5 rounded-full"
                style={{ background: "#CDE3D6", color: "#1B5035" }}
              >
                conf. {confidence}%
              </span>
            )}
          </div>

          {detection ? (
            <>
              {/* Nome */}
              <div>
                <p
                  style={{
                    fontFamily: "Libre Franklin, sans-serif",
                    fontSize: 21,
                    fontWeight: 700,
                    color: "#221F1A",
                    lineHeight: 1.15,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {aiPt}
                </p>
                <p className="italic text-sm mt-0.5" style={{ color: "#6B6357", ...font }}>
                  {aiGenus}
                </p>
              </div>

              {/* Barra de confiança */}
              <div className="rounded-full overflow-hidden" style={{ height: 5, background: "#DCEBE1" }}>
                <div className="h-full rounded-full" style={{ width: `${confidence}%`, background: "#3E8E63" }} />
              </div>
            </>
          ) : (
            <p className="text-sm" style={{ color: "#9A9080", ...font }}>
              Nenhuma detecção neste frame.
            </p>
          )}
        </div>
      </div>

      {/* ── Faixa de ações + navegação de frame ────────── */}
      <div className="px-4 pb-3 flex flex-col gap-2 shrink-0">
        {/* Confirmar / Confirmar vídeo / Rejeitar — só com detecção */}
        {detection && (
          <div className="flex gap-2 items-stretch">
            <button
              onClick={onConfirmAI}
              className="flex-1 flex items-center justify-center gap-1.5 text-sm font-semibold text-white"
              style={{
                background: confirmed ? "#3E8E63" : "#2F6B4F",
                borderRadius: 10,
                padding: "9px 12px",
                transition: "background 0.15s",
                ...font,
              }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#3E8E63")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = confirmed ? "#3E8E63" : "#2F6B4F")}
            >
              {confirmed && <Check size={13} style={{ color: "#A9E8C2" }} />}
              Confirmar {aiPt}
              <kbd className="text-xs rounded px-1 py-0.5" style={{ background: "rgba(255,255,255,0.2)", fontFamily: "IBM Plex Mono, monospace" }}>⏎</kbd>
            </button>

            <button
              onClick={onConfirmVideo}
              className="flex items-center justify-center gap-1.5 text-xs font-medium"
              style={{
                padding: "9px 11px", borderRadius: 10,
                background: "#EFF6FF", color: "#2563EB",
                border: "1.5px solid #BFDBFE",
                transition: "background 0.15s",
                ...font,
              }}
              title="Confirmar para todos os frames do vídeo (⇧⏎)"
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#DBEAFE")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#EFF6FF")}
            >
              <Film size={13} />
              Vídeo
              <kbd className="text-xs rounded px-1" style={{ background: "rgba(37,99,235,0.12)", fontFamily: "IBM Plex Mono, monospace" }}>⇧⏎</kbd>
            </button>

            <button
              onClick={onReject}
              className="flex items-center justify-center"
              style={{
                width: 36, flexShrink: 0,
                borderRadius: 10,
                border: "1.5px solid #E7DECF",
                background: "#fff", color: "#6B6357",
                transition: "background 0.15s, color 0.15s",
              }}
              title="Rejeitar sugestão da IA"
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#FEF2EF"; (e.currentTarget as HTMLElement).style.color = "#C2503A"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#fff"; (e.currentTarget as HTMLElement).style.color = "#6B6357"; }}
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* Navegação de frame — sempre visível */}
        <div className="flex gap-2">
          <button
            onClick={onPrevFrame}
            disabled={frameIdx <= 1}
            className="flex items-center gap-1 px-3 py-2 text-xs font-medium rounded-xl disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "#FAF6EE", border: "1.5px solid #E7DECF", color: "#221F1A", transition: "background 0.15s", ...font }}
            onMouseEnter={(e) => { if (frameIdx > 1) (e.currentTarget as HTMLElement).style.background = "#EFE8DB"; }}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#FAF6EE")}
          >
            <ChevronLeft size={13} />
            Anterior
          </button>

          <button
            onClick={onSkipFrame}
            disabled={frameIdx >= totalFrames}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-xl disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "#FAF6EE", border: "1.5px solid #E7DECF", color: "#6B6357", transition: "background 0.15s", ...font }}
            onMouseEnter={(e) => { if (frameIdx < totalFrames) (e.currentTarget as HTMLElement).style.background = "#EFE8DB"; }}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#FAF6EE")}
          >
            <SkipForward size={13} />
            Pular
            <kbd className="text-xs rounded px-1" style={{ background: "#EFE8DB", color: "#9A9080", fontFamily: "IBM Plex Mono, monospace" }}>S</kbd>
          </button>

          <button
            onClick={onNextFrame}
            disabled={frameIdx >= totalFrames}
            className="flex items-center gap-1 px-3 py-2 text-xs font-medium rounded-xl disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "#2F6B4F", color: "#fff", border: "none", transition: "background 0.15s", ...font }}
            onMouseEnter={(e) => { if (frameIdx < totalFrames) (e.currentTarget as HTMLElement).style.background = "#3E8E63"; }}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#2F6B4F")}
          >
            Próximo
            <ChevronRight size={13} />
          </button>
        </div>
      </div>

      {/* ── Busca ──────────────────────────────────────── */}
      <div className="px-4 pb-2 shrink-0">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: "#9A9080" }}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="Buscar espécie…"
            className="w-full pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3E8E63]/30"
            style={{
              background: "#FAF6EE",
              border: "1.5px solid #E7DECF",
              borderRadius: 10,
              color: "#221F1A",
              ...font,
              fontSize: 13.5,
            }}
          />
        </div>
      </div>

      {/* ── Label ──────────────────────────────────────── */}
      <div className="px-4 pb-2 shrink-0">
        <span style={labelStyle}>{query ? "Resultados" : "Confirmar como"}</span>
      </div>

      {/* ── Grade de espécies ─────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <p className="text-sm text-center" style={{ color: "#9A9080", ...font }}>
              Nenhuma espécie encontrada.
            </p>
            <button
              onClick={onOpenNewCat}
              className="text-sm font-medium underline transition-colors"
              style={{ color: "#2F6B4F", ...font }}
            >
              Criar nova categoria
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {filtered.map((cat) => {
              const isSelected = selected === cat.id;
              return (
                <button
                  key={cat.id}
                  onClick={() => onSelect(cat.id)}
                  className="flex items-center justify-between gap-1 text-left transition-colors"
                  style={{
                    padding: "11px 12px",
                    borderRadius: 11,
                    border: isSelected ? "1.5px solid #2F6B4F" : "1.5px solid #E7DECF",
                    background: isSelected ? "#2F6B4F" : "#fff",
                    color: isSelected ? "#fff" : "#221F1A",
                    fontWeight: isSelected ? 600 : 500,
                    fontSize: 13,
                    ...font,
                    overflow: "hidden",
                  }}
                >
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {cat.name}
                  </span>
                  {isSelected && (
                    <Check size={13} style={{ color: "#A9E8C2", flexShrink: 0 }} />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Nova categoria (rodapé) ────────────────────── */}
      <div
        className="px-4 py-3 shrink-0 border-t"
        style={{ borderColor: "#EFE8DB" }}
      >
        {newCatOpen ? (
          <div className="flex items-center gap-2">
            <input
              ref={newCatInputRef}
              type="text"
              value={newCatName}
              onChange={(e) => onNewCatName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onAddCategory(newCatName);
                if (e.key === "Escape") onCloseNewCat();
              }}
              placeholder="Nome da espécie…"
              className="flex-1 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#E2A33C]/40"
              style={{
                background: "#FAF6EE",
                border: "1.5px solid #E7DECF",
                borderRadius: 9,
                color: "#221F1A",
                ...font,
              }}
            />
            <button
              onClick={() => onAddCategory(newCatName)}
              className="px-3 py-1.5 text-sm font-semibold rounded-lg transition-colors"
              style={{
                background: "#E2A33C",
                color: "#3A2A0E",
                borderRadius: 9,
                ...font,
              }}
              onMouseEnter={(e) =>
                ((e.target as HTMLElement).style.background = "#C2802B")
              }
              onMouseLeave={(e) =>
                ((e.target as HTMLElement).style.background = "#E2A33C")
              }
            >
              Criar
            </button>
            <button
              onClick={onCloseNewCat}
              className="text-sm transition-colors hover:text-red-500"
              style={{ color: "#9A9080" }}
            >
              <X size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenNewCat}
            className="w-full py-2 text-sm font-medium transition-colors rounded-lg"
            style={{
              border: "1.5px dashed #C3BAA8",
              color: "#6B6357",
              background: "transparent",
              borderRadius: 10,
              ...font,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = "#9A9080";
              (e.currentTarget as HTMLElement).style.color = "#221F1A";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = "#C3BAA8";
              (e.currentTarget as HTMLElement).style.color = "#6B6357";
            }}
          >
            + Nova categoria
          </button>
        )}
      </div>
    </div>
  );
}
