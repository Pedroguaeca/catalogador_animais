"use client";

import type { Frame } from "../lib/types";

interface FilmstripProps {
  frames: Frame[];
  frameIdx: number; // 1-based
  onSelect: (idx: number) => void;
}

const STATUS_COLOR: Record<string, string> = {
  detection: "#5FD08A",
  review: "#E2A33C",
  empty: "#9A9080",
};

export function Filmstrip({ frames, frameIdx, onSelect }: FilmstripProps) {
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
          return (
            <button
              key={f.idx}
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
              {/* Dot de status — inf dir */}
              <span
                className="absolute bottom-1 right-1 rounded-full"
                style={{
                  width: 7,
                  height: 7,
                  background: STATUS_COLOR[f.status ?? "empty"],
                  boxShadow: "0 0 0 1.5px rgba(0,0,0,0.4)",
                }}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
