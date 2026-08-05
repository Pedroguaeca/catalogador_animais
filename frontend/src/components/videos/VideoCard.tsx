"use client";

import { useState } from "react";
import { Film, Thermometer } from "lucide-react";
import type { VideoItem } from "../../lib/videoTypes";
import { statusStyle } from "../../lib/statusColors";
import { formatDate, formatConfidence } from "../../lib/videoFormat";

interface VideoCardProps {
  video:    VideoItem;
  selected: boolean;
  onClick:  () => void;
}

function StatusPill({ video }: { video: VideoItem }) {
  const st = statusStyle(video.display_status);
  const isProcessing = video.display_status === "Processando";
  return (
    <span
      className={isProcessing ? "animate-pulse" : ""}
      style={{
        padding: "3px 9px", borderRadius: 6, fontSize: 12, fontWeight: 500,
        background: st.bg, color: st.color, whiteSpace: "nowrap",
        fontFamily: "IBM Plex Sans, sans-serif",
      }}
    >
      {isProcessing ? "Processando…" : formatConfidence(video.confidence) !== "—"
        ? formatConfidence(video.confidence)
        : video.display_status}
    </span>
  );
}

export function VideoCard({ video, selected, onClick }: VideoCardProps) {
  const [imgError, setImgError] = useState(false);
  const showThumb = video.thumbnail_url && !imgError;

  const isProcessing  = video.display_status === "Processando";
  const isSemDeteccao = video.display_status === "Sem detecção";
  const tags = video.display_status === "Revisado" ? video.species : video.ai_species;

  return (
    <button
      onClick={onClick}
      className="flex items-stretch gap-3 text-left w-full"
      style={{
        padding: 10, borderRadius: 12,
        border: selected ? "1.5px solid #2F6B4F" : "1.5px solid #E7DECF",
        background: selected ? "#F2FAF6" : "#fff",
        cursor: "pointer", transition: "background 0.15s, border 0.15s",
      }}
    >
      <div style={{
        width: 96, height: 64, borderRadius: 9, overflow: "hidden",
        background: "#F1F0EE", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
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
          <Film size={18} style={{ color: "#C3BAA8" }} />
        )}
      </div>

      <div className="flex flex-col gap-1.5 min-w-0" style={{ flex: 1 }}>
        <span style={{
          fontFamily: "IBM Plex Mono, monospace", fontSize: 12, color: "#221F1A",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {video.original_filename ?? (video.video_id.slice(0, 16) + "…")}
        </span>

        <div className="flex items-center gap-2 flex-wrap" style={{
          fontSize: 11.5, color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif",
        }}>
          <span>{video.camera_id ?? "Sem câmera"}</span>
          <span>·</span>
          <span style={{ fontFamily: "IBM Plex Mono, monospace" }}>
            {formatDate(video.captured_at ?? video.uploaded_at)}
          </span>
          {video.temperature_c !== null && (
            <>
              <span>·</span>
              <span className="flex items-center gap-0.5">
                <Thermometer size={10} />
                {video.temperature_c}°C
              </span>
            </>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {isProcessing ? (
            <span style={{ color: "#9A9080", fontSize: 11.5, fontStyle: "italic", fontFamily: "IBM Plex Sans, sans-serif" }}>
              detecção em andamento
            </span>
          ) : isSemDeteccao ? (
            <span style={{ color: "#9A9080", fontSize: 11.5, fontStyle: "italic", fontFamily: "IBM Plex Sans, sans-serif" }}>
              sem detecção
            </span>
          ) : tags.length === 0 ? (
            <span style={{ color: "#C5B9AD", fontSize: 11.5, fontStyle: "italic" }}>—</span>
          ) : (
            tags.map((sp) => (
              <span key={sp} style={{
                padding: "2px 7px", borderRadius: 5,
                background: "#EEF5F0", color: "#2F6B4F",
                fontSize: 11, fontStyle: "italic", whiteSpace: "nowrap",
              }}>
                {sp}
              </span>
            ))
          )}
        </div>
      </div>

      <div className="flex items-start shrink-0">
        <StatusPill video={video} />
      </div>
    </button>
  );
}
