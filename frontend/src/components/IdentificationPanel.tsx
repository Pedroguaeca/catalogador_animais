"use client";

import { useRef, useEffect, useState } from "react";
import { Search, X, Sparkles, Check, CheckCircle2, ChevronLeft, ChevronRight, SkipForward, Film, PencilLine, SplitSquareHorizontal, Minus, Plus } from "lucide-react";
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
  novoEventoMarked: boolean;
  onMarkNovoEvento: () => void;
  temFilhote: boolean;
  onToggleTemFilhote: (value: boolean) => void;
  isAnnotated: boolean;
  annotatedSpeciesLabel: string | null;
  individualCount: number;
  onChangeIndividualCount: (n: number) => void;
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
  novoEventoMarked,
  onMarkNovoEvento,
  temFilhote,
  onToggleTemFilhote,
  isAnnotated,
  annotatedSpeciesLabel,
  individualCount,
  onChangeIndividualCount,
}: IdentificationPanelProps) {
  const newCatInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (newCatOpen) newCatInputRef.current?.focus();
  }, [newCatOpen]);

  // Distingue qual dos dois botões de confirmação foi clicado — `confirmed`
  // (vindo do reducer) é compartilhado entre confirmar-frame e
  // confirmar-vídeo, mas o feedback textual precisa ser específico por botão.
  const [justConfirmed, setJustConfirmed] = useState<"frame" | "video" | null>(null);

  useEffect(() => {
    if (!confirmed) setJustConfirmed(null);
  }, [confirmed]);

  useEffect(() => {
    setJustConfirmed(null);
  }, [frameIdx]);

  // Busca é o único caminho de correção manual — sem grade fixa, resultados
  // só aparecem quando o revisor digita algo.
  const filtered = query
    ? categories.filter((c) =>
        c.name.toLowerCase().includes(query.toLowerCase())
      )
    : [];

  const startCorrection = () => {
    onReject();
    searchInputRef.current?.focus();
  };

  const aiPt = detection?.genus_pt ?? null;
  const aiGenus = detection?.genus ?? null;
  const confidence = detection ? Math.round(detection.cls_conf * 100) : 0;

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
      {/* ── Cartão IA / Revisado ───────────────────────── */}
      <div className="px-4 pt-4 pb-3 shrink-0">
        <div
          className="p-3.5 flex flex-col gap-2.5"
          style={{
            background: isAnnotated ? "#EAF6EE" : "#EEF5F0",
            border: isAnnotated ? "1px solid #A9DABB" : "1px solid #CDE3D6",
            borderRadius: 13,
          }}
        >
          {isAnnotated && annotatedSpeciesLabel ? (
            /* Frame já revisado — mesmo painel, mesmo dado (fonte única com o
               selo do carrossel e do frame grande), sem estado duplicado. */
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 min-w-0" style={{ ...font }}>
                <CheckCircle2 size={16} style={{ color: "#2D8B5F", flexShrink: 0 }} />
                <span
                  className="font-semibold truncate"
                  style={{ fontSize: 15, color: "#1B5035" }}
                  title={annotatedSpeciesLabel}
                >
                  Revisado: {annotatedSpeciesLabel}
                </span>
              </span>
              <button
                onClick={startCorrection}
                className="text-xs font-semibold underline shrink-0"
                style={{ color: "#2F6B4F", ...font }}
              >
                Corrigir
              </button>
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      </div>

      {/* ── Faixa de ações + navegação de frame ────────── */}
      <div className="px-4 pb-3 flex flex-col gap-2 shrink-0">
        {/* Confirmar frame / Confirmar vídeo / Corrigir — só com detecção.
            "Confirmar este frame" numa linha própria, largura total (é a
            ação mais frequente). "Confirmar vídeo" e "Corrigir" lado a lado,
            mesma largura — diferenciados só por cor/peso, não por tamanho. */}
        {detection && (
          <div className="flex flex-col gap-2">
            <button
              onClick={() => { onConfirmAI(); setJustConfirmed("frame"); }}
              title="Marca só este frame como revisado — os outros continuam pendentes"
              className="w-full flex items-center justify-center gap-1.5 font-semibold"
              style={{
                background: "#E8F5EE",
                color: "#2D8B5F",
                borderRadius: 10,
                padding: "10px 14px",
                fontSize: 13,
                transition: "background 0.15s",
                ...font,
              }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#D9EEE3")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#E8F5EE")}
            >
              {justConfirmed === "frame" && <Check size={13} />}
              {justConfirmed === "frame" ? "Frame confirmado" : "Confirmar este frame"}
              <kbd className="text-xs rounded px-1 py-0.5" style={{ background: "rgba(45,139,95,0.12)", fontFamily: "IBM Plex Mono, monospace" }}>⏎</kbd>
            </button>

            <div className="flex gap-2 items-stretch">
              <button
                onClick={() => { onConfirmVideo(); setJustConfirmed("video"); }}
                title="Aplica esta espécie a todos os frames deste vídeo de uma vez"
                className="flex-1 flex items-center justify-center gap-1.5 font-semibold"
                style={{
                  padding: "10px 12px", borderRadius: 10,
                  background: "#2D8B5F", color: "#FFFFFF",
                  fontSize: 13,
                  transition: "background 0.15s",
                  ...font,
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#256E4B")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#2D8B5F")}
              >
                {justConfirmed === "video" ? <Check size={14} /> : <Film size={14} />}
                {justConfirmed === "video" ? "Vídeo confirmado" : "Confirmar vídeo inteiro"}
              </button>

              <button
                onClick={startCorrection}
                title="Escolhe outra espécie para este frame"
                className="flex-1 flex items-center justify-center gap-1.5 font-semibold"
                style={{
                  padding: "10px 12px", borderRadius: 10,
                  border: "1.5px solid #2D8B5F",
                  background: "#FFFFFF", color: "#2D8B5F",
                  fontSize: 13,
                  transition: "background 0.15s",
                  ...font,
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#F2FAF6")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#FFFFFF")}
              >
                <PencilLine size={13} />
                Não é isso? Corrigir
              </button>
            </div>
          </div>
        )}

        {/* Marcador de novo evento — ação rara, peso visual leve, não compete
            com os 3 botões principais. Caso 4 do plano de aparições (16/07):
            mesma espécie reaparecendo após um intervalo real de ausência. */}
        {detection && (
          <button
            onClick={onMarkNovoEvento}
            title="Usa isso só se o mesmo tipo de animal saiu de cena e voltou depois, no mesmo vídeo — não precisa pra vídeos com um evento contínuo."
            className="self-start flex items-center gap-1 text-xs font-medium transition-colors"
            style={{
              color: novoEventoMarked ? "#2D8B5F" : "#9A9080",
              ...font,
            }}
            onMouseEnter={(e) => { if (!novoEventoMarked) (e.currentTarget as HTMLElement).style.color = "#6B6357"; }}
            onMouseLeave={(e) => { if (!novoEventoMarked) (e.currentTarget as HTMLElement).style.color = "#9A9080"; }}
          >
            <SplitSquareHorizontal size={12} />
            {novoEventoMarked ? "Novo evento marcado aqui" : "Marcar como novo evento aqui"}
          </button>
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

      {/* ── Filhote + indivíduos (metadado de treino, junto com a correção) ── */}
      {detection && (
        <div className="px-4 pb-2 shrink-0 flex items-center justify-between gap-3">
          <label
            className="flex items-center gap-2 text-sm cursor-pointer select-none"
            style={{ color: "#6B6357", ...font }}
          >
            <input
              type="checkbox"
              checked={temFilhote}
              onChange={(e) => onToggleTemFilhote(e.target.checked)}
              style={{ accentColor: "#2D8B5F", width: 14, height: 14 }}
            />
            Tem filhote(s) neste frame
          </label>

          <div className="flex items-center gap-1 shrink-0" title="Quantidade de indivíduos neste frame (opcional)">
            <button
              onClick={() => onChangeIndividualCount(Math.max(1, individualCount - 1))}
              disabled={individualCount <= 1}
              className="flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
              style={{ width: 22, height: 22, borderRadius: 6, border: "1.5px solid #E7DECF", color: "#6B6357" }}
            >
              <Minus size={11} />
            </button>
            <span
              className="text-center font-semibold"
              style={{ width: 20, fontSize: 13, color: "#221F1A", ...font }}
            >
              {individualCount}
            </span>
            <button
              onClick={() => onChangeIndividualCount(individualCount + 1)}
              className="flex items-center justify-center"
              style={{ width: 22, height: 22, borderRadius: 6, border: "1.5px solid #E7DECF", color: "#6B6357" }}
            >
              <Plus size={11} />
            </button>
            <span className="text-xs" style={{ color: "#9A9080", ...font }}>indivíduos</span>
          </div>
        </div>
      )}

      {/* ── Busca ──────────────────────────────────────── */}
      <div className="px-4 pb-2 shrink-0">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: "#9A9080" }}
          />
          <input
            ref={searchInputRef}
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

      {/* ── Resultados da busca — grade fixa removida; sem digitar, nada aparece ── */}
      <div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
        {query && (
          <div className="pb-2">
            <span style={labelStyle}>Resultados</span>
          </div>
        )}
        {!query ? (
          <p className="text-sm text-center py-8" style={{ color: "#C3BAA8", ...font }}>
            Digite pra buscar uma espécie.
          </p>
        ) : filtered.length === 0 ? (
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
