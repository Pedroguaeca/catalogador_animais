"use client";

import { Users, Baby } from "lucide-react";
import type { VideoSegment } from "../lib/types";

interface SegmentStripProps {
  segments: VideoSegment[];
  activeSegmentKey: string | null; // "species#segment" do frame atual, ou null
  onSelect: (segment: VideoSegment) => void;
}

const font = { fontFamily: "IBM Plex Sans, sans-serif" };

// Faixa de resumo dos segmentos (video_id, annotated_species, segmento) do
// vídeo atual — cada linha navega pro primeiro frame daquele segmento ao
// clicar. Ver GET /projects/{id}/videos/{id}/segments.
export function SegmentStrip({ segments, activeSegmentKey, onSelect }: SegmentStripProps) {
  if (segments.length === 0) return null;

  return (
    <div
      className="shrink-0 bg-white flex flex-col"
      style={{
        borderRadius: 14,
        boxShadow: "0 1px 2px rgba(34,31,26,0.04), 0 6px 20px rgba(34,31,26,0.05)",
        overflow: "hidden",
      }}
    >
      <div className="flex items-center px-4 py-2.5 border-b shrink-0" style={{ borderColor: "#EFE8DB" }}>
        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#9A9080", ...font }}>
          Registros do vídeo
        </span>
      </div>

      <div className="overflow-x-auto flex gap-2 p-3">
        {segments.map((s) => {
          const key = `${s.species}#${s.segment}`;
          const isActive = activeSegmentKey === key;
          return (
            <button
              key={key}
              onClick={() => onSelect(s)}
              className="flex flex-col items-start gap-1 text-left shrink-0 transition-colors"
              style={{
                padding: "8px 12px",
                borderRadius: 10,
                border: isActive ? "1.5px solid #2D8B5F" : "1.5px solid #E7DECF",
                background: isActive ? "#EAF6EE" : "#fff",
                minWidth: 148,
                ...font,
              }}
            >
              <span className="text-sm font-semibold truncate" style={{ color: "#221F1A", maxWidth: 180 }}>
                {s.species}
              </span>
              <span className="flex items-center gap-2 text-xs" style={{ color: "#6B6357" }}>
                <span>frames {s.frame_start}–{s.frame_end}</span>
                <span className="flex items-center gap-0.5">
                  <Users size={11} /> {s.individual_count}
                </span>
                {s.tem_filhote && <Baby size={12} style={{ color: "#2D8B5F" }} />}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
