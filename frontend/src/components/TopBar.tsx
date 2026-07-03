"use client";

import { ChevronDown } from "lucide-react";

interface TopBarProps {
  videoId: string;
  videos: string[];
  frameIdx: number;
  totalFrames: number;
  videoIdx: number;
  totalVideos: number;
  annotated: number;
  onVideoChange: (id: string) => void;
  onJumpUnannotated: () => void;
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
      <div className="relative">
        <select
          value={videoId}
          onChange={(e) => onVideoChange(e.target.value)}
          className="appearance-none flex items-center gap-2 pl-8 pr-8 py-1.5 text-sm font-medium rounded-full border cursor-pointer focus:outline-none"
          style={{
            background: "#FAF6EE",
            borderColor: "#E7DECF",
            color: "#221F1A",
            fontFamily: "IBM Plex Sans, sans-serif",
            fontSize: 13.5,
          }}
        >
          {videos.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        {/* Dot verde */}
        <span
          className="absolute left-2.5 top-1/2 -translate-y-1/2 rounded-full"
          style={{ width: 7, height: 7, background: "#5FD08A" }}
        />
        <ChevronDown
          size={13}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ color: "#9A9080" }}
        />
      </div>

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
