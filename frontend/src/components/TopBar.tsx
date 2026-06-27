"use client";

import { ChevronDown, UploadCloud } from "lucide-react";

interface TopBarProps {
  videoId: string;
  videos: string[];
  frameIdx: number;
  totalFrames: number;
  videoIdx: number;
  totalVideos: number;
  annotated: number;
  onVideoChange: (id: string) => void;
  onUpload: () => void;
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
  onUpload,
}: TopBarProps) {
  const progress = totalFrames > 0 ? (annotated / totalFrames) * 100 : 0;

  return (
    <header
      className="flex items-center justify-between px-5 border-b bg-white shrink-0"
      style={{ height: 60 }}
    >
      {/* Logo + título + upload */}
      <div className="flex items-center gap-3">
        <div
          className="flex items-center justify-center text-white font-bold text-xs"
          style={{
            width: 30,
            height: 30,
            background: "#2F6B4F",
            borderRadius: 9,
            boxShadow: "0 0 0 2px #fff, 0 0 0 3.5px #2F6B4F",
            fontFamily: "Libre Franklin, sans-serif",
          }}
        >
          S
        </div>
        <span
          className="font-semibold text-sm tracking-tight"
          style={{ color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif" }}
        >
          SIAB{" "}
          <span style={{ color: "#9A9080", fontWeight: 400 }}>/ Revisão</span>
        </span>
        <button
          onClick={onUpload}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-colors"
          style={{
            background: "#EEF5F0",
            border: "1.5px solid #CDE3D6",
            color: "#2F6B4F",
            fontFamily: "IBM Plex Sans, sans-serif",
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#CDE3D6")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#EEF5F0")}
        >
          <UploadCloud size={13} />
          Adicionar vídeos
        </button>
      </div>

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
        <span
          className="text-xs font-semibold"
          style={{ color: "#2F8F4E", fontFamily: "IBM Plex Sans, sans-serif" }}
        >
          {annotated} anotados
        </span>
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
