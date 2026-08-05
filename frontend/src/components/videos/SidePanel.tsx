"use client";

import { useState } from "react";
import Link from "next/link";
import { Film, ArrowRight, Loader2, Eye, Thermometer } from "lucide-react";
import type { VideoItem } from "../../lib/videoTypes";
import { formatDate, formatConfidence } from "../../lib/videoFormat";

interface SidePanelProps {
  video: VideoItem | null;
}

export function SidePanel({ video }: SidePanelProps) {
  const [imgError, setImgError] = useState(false);

  if (!video) {
    return (
      <div className="flex flex-col items-center justify-center gap-2" style={{
        width: 280, flexShrink: 0, padding: 24, color: "#9A9080",
        fontFamily: "IBM Plex Sans, sans-serif",
      }}>
        <Film size={24} style={{ opacity: 0.3 }} />
        <p style={{ fontSize: 13, textAlign: "center" }}>Nenhum vídeo selecionado.</p>
      </div>
    );
  }

  const showThumb = video.thumbnail_url && !imgError;
  const tags = video.display_status === "Revisado" ? video.species : video.ai_species;

  return (
    <div className="flex flex-col gap-3" style={{
      width: 280, flexShrink: 0, background: "#fff",
      border: "1px solid #E7DECF", borderRadius: 16, padding: 14,
      height: "fit-content", position: "sticky", top: 16,
    }}>
      <div style={{
        width: "100%", height: 160, borderRadius: 10, overflow: "hidden",
        background: "#F1F0EE", display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {showThumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={video.thumbnail_url ?? undefined}
            alt=""
            onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <Film size={22} style={{ color: "#C3BAA8" }} />
        )}
      </div>

      <span style={{
        fontFamily: "IBM Plex Mono, monospace", fontSize: 12.5, color: "#221F1A",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      }}>
        {video.original_filename ?? video.video_id}
      </span>

      <div className="flex flex-col gap-1" style={{
        fontSize: 12, color: "#6B6357", fontFamily: "IBM Plex Sans, sans-serif",
      }}>
        <span>{video.camera_id ?? "Sem câmera"}</span>
        <span style={{ fontFamily: "IBM Plex Mono, monospace" }}>
          {formatDate(video.captured_at ?? video.uploaded_at)}
        </span>
        {video.temperature_c !== null && (
          <span className="flex items-center gap-1">
            <Thermometer size={11} />
            {video.temperature_c}°C
          </span>
        )}
        {video.display_status !== "Processando" && (
          <span>Confiança: {formatConfidence(video.confidence)}</span>
        )}
        {video.display_status === "Revisado" && video.reviewed_by && (
          <span title={video.reviewed_by} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            Revisado por {video.reviewed_by.slice(0, 12)}… · {formatDate(video.reviewed_at)}
          </span>
        )}
      </div>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map((sp) => (
            <span key={sp} style={{
              padding: "2px 7px", borderRadius: 5,
              background: "#EEF5F0", color: "#2F6B4F",
              fontSize: 11, fontStyle: "italic",
            }}>
              {sp}
            </span>
          ))}
        </div>
      )}

      <ActionButton video={video} />
    </div>
  );
}

function ActionButton({ video }: { video: VideoItem }) {
  const font = { fontFamily: "IBM Plex Sans, sans-serif" };

  if (video.display_status === "Processando") {
    return (
      <button
        disabled
        className="flex items-center justify-center gap-1.5 font-semibold"
        style={{
          padding: "9px 11px", borderRadius: 10,
          background: "#F1F0EE", color: "#9A9080",
          fontSize: 13, cursor: "not-allowed", ...font,
        }}
      >
        <Loader2 size={14} className="animate-spin" />
        Ainda processando
      </button>
    );
  }

  if (video.display_status === "Revisado") {
    return (
      <Link
        href={`/review?video=${video.video_id}`}
        className="flex items-center justify-center gap-1.5 font-semibold"
        style={{
          padding: "9px 11px", borderRadius: 10,
          border: "1.5px solid #2D8B5F",
          background: "#FFFFFF", color: "#2D8B5F",
          fontSize: 13, textDecoration: "none", ...font,
        }}
      >
        <Eye size={13} />
        Ver revisão
      </Link>
    );
  }

  // Aguardando revisão (inclui "sem detecção")
  return (
    <Link
      href={`/review?video=${video.video_id}`}
      className="flex items-center justify-center gap-1.5 font-semibold"
      style={{
        padding: "9px 11px", borderRadius: 10,
        background: "#2D8B5F", color: "#FFFFFF",
        fontSize: 13, textDecoration: "none", transition: "background 0.15s", ...font,
      }}
      onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#256E4B")}
      onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#2D8B5F")}
    >
      Abrir revisão
      <ArrowRight size={14} />
    </Link>
  );
}
