"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { statusStyle } from "../lib/statusColors";

interface VideoOption {
  id: string;
  label: string;
  display_status?: string;
}

interface TopBarProps {
  videoId: string;
  videos: VideoOption[];
  frameIdx: number;
  totalFrames: number;
  videoIdx: number;
  totalVideos: number;
  annotated: number;
  onVideoChange: (id: string) => void;
  onJumpUnannotated: () => void;
}

const font = { fontFamily: "IBM Plex Sans, sans-serif" };

// Dropdown custom em vez de <select> nativo — <option> não suporta um ponto
// colorido por item, e o pedido é reaproveitar as cores de status de /videos.
function VideoDropdown({
  videos, videoId, onVideoChange,
}: {
  videos: VideoOption[];
  videoId: string;
  onVideoChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = videos.find((v) => v.id === videoId);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const currentDot = statusStyle(current?.display_status).color;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 pl-3 pr-8 py-1.5 text-sm font-medium rounded-full border cursor-pointer relative"
        style={{
          background: "#FAF6EE", borderColor: "#E7DECF", color: "#221F1A",
          fontSize: 13.5, maxWidth: 260, ...font,
        }}
      >
        <span
          className="rounded-full shrink-0"
          style={{ width: 7, height: 7, background: currentDot }}
        />
        <span className="truncate">{current?.label ?? videoId}</span>
        <ChevronDown
          size={13}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ color: "#9A9080" }}
        />
      </button>

      {open && (
        <div
          className="absolute left-0 top-full mt-1.5 overflow-y-auto rounded-2xl bg-white z-50"
          style={{
            minWidth: 280, maxWidth: 340, maxHeight: 320,
            border: "1px solid #E7DECF",
            boxShadow: "0 4px 20px rgba(34,31,26,0.12)",
            padding: 6,
          }}
        >
          {videos.map((v) => {
            const st = statusStyle(v.display_status);
            const active = v.id === videoId;
            return (
              <button
                key={v.id}
                type="button"
                onClick={() => { onVideoChange(v.id); setOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-left rounded-xl transition-colors"
                style={{
                  background: active ? "#FAF6EE" : "transparent",
                  fontSize: 13, ...font,
                }}
                onMouseEnter={(e) => { if (!active) (e.currentTarget as HTMLElement).style.background = "#FAF6EE"; }}
                onMouseLeave={(e) => { if (!active) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
              >
                <span className="rounded-full shrink-0" style={{ width: 7, height: 7, background: st.color }} />
                <span className="flex-1 truncate" style={{ color: "#221F1A", fontWeight: active ? 600 : 400 }}>
                  {v.label}
                </span>
                <span
                  className="shrink-0 px-1.5 py-0.5 rounded-full text-[10px] font-medium"
                  style={{ background: st.bg, color: st.color }}
                >
                  {v.display_status ?? "Processando"}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function TopBar({
  videoId,
  videos,
  frameIdx,
  totalFrames,
  videoIdx,
  totalVideos,
  annotated,
  onVideoChange,
  onJumpUnannotated,
}: TopBarProps) {
  const progress = totalFrames > 0 ? (annotated / totalFrames) * 100 : 0;

  return (
    <header
      className="flex items-center justify-between px-5 border-b bg-white shrink-0"
      style={{ height: 52 }}
    >
      {/* Seletor de vídeo */}
      <VideoDropdown videos={videos} videoId={videoId} onVideoChange={onVideoChange} />

      {/* Contadores + progress */}
      <div className="flex items-center gap-4">
        <span className="text-xs" style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
          Frame{" "}
          <span className="font-semibold" style={{ color: "#221F1A" }}>
            {frameIdx}
          </span>
          /{totalFrames}
        </span>
        <span className="text-xs" style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
          Vídeo{" "}
          <span className="font-semibold" style={{ color: "#221F1A" }}>
            {videoIdx + 1}
          </span>
          /{totalVideos}
        </span>
        <button
          onClick={onJumpUnannotated}
          title="Ir para o primeiro frame não anotado"
          className="text-xs font-semibold transition-colors"
          style={{
            color: "#2F8F4E", fontFamily: "IBM Plex Sans, sans-serif",
            background: "none", border: "none", cursor: "pointer",
            padding: "2px 6px", borderRadius: 6,
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#EEF5F0")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "none")}
        >
          {annotated} anotados
        </button>
        {/* Barra de progresso */}
        <div
          className="rounded-full overflow-hidden"
          style={{ width: 230, height: 5, background: "#EFE8DB" }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${progress}%`, background: "#3E8E63" }}
          />
        </div>
      </div>
    </header>
  );
}
