"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { API_BASE, apiHeaders } from "../../src/lib/api";
import { Film, Trash2, ExternalLink, Loader2, RefreshCw, AlertCircle } from "lucide-react";

const PROJECT_ID = "projeto-junho-2026";

interface VideoItem {
  video_id:          string;
  original_filename: string | null;
  camera_id:         string | null;
  captured_at:       string | null;
  uploaded_at:       string | null;
  status:            string | null;
  display_status:    string;
  species:           string[];
  appearance_count:  number;
}

function statusStyle(s: string): { bg: string; color: string } {
  if (s === "Revisado")           return { bg: "#EEF5F0", color: "#2F6B4F" };
  if (s === "Aguardando revisão") return { bg: "#FFF8EC", color: "#B45309" };
  return                                  { bg: "#F1F0EE", color: "#6B6357" };
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    }).format(new Date(iso));
  } catch { return iso; }
}

export default function VideosPage() {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;

  const [videos,   setVideos]   = useState<VideoItem[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!idToken) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/projects/${PROJECT_ID}/videos`, {
        headers: apiHeaders(idToken),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setVideos(d.videos ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  }, [idToken]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = useCallback(async (videoId: string, filename: string | null) => {
    const label = filename ?? videoId.slice(0, 8);
    if (!window.confirm(`Apagar vídeo "${label}" e todos os seus dados?\n\nEsta acção não pode ser desfeita.`)) return;
    setDeleting(videoId);
    try {
      const r = await fetch(`${API_BASE}/projects/${PROJECT_ID}/videos/${videoId}`, {
        method:  "DELETE",
        headers: apiHeaders(idToken),
      });
      if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
      setVideos((v) => v.filter((x) => x.video_id !== videoId));
    } catch (e) {
      alert(`Erro ao apagar: ${e instanceof Error ? e.message : e}`);
    } finally {
      setDeleting(null);
    }
  }, [idToken]);

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#F7F3EE" }}>
      <SiabNav />

      <main className="flex flex-col flex-1 px-6 py-6 gap-4" style={{ maxWidth: 960, width: "100%", margin: "0 auto" }}>

        {/* Header */}
        <div className="flex items-center gap-3">
          <Film size={18} style={{ color: "#2F6B4F" }} />
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif" }}>
            Vídeos
          </h1>
          <span style={{
            fontSize: 12, color: "#9A9080", fontFamily: "IBM Plex Mono, monospace",
            background: "#EFE8DB", padding: "2px 8px", borderRadius: 6,
          }}>
            {PROJECT_ID}
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={load}
            disabled={loading}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "6px 12px", borderRadius: 10,
              border: "1px solid #E7DECF", background: "#fff",
              fontSize: 13, color: "#6B6357", cursor: "pointer",
              fontFamily: "IBM Plex Sans, sans-serif",
            }}
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Actualizar
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl"
            style={{ background: "#FBF0F0", color: "#C0392B", fontSize: 13 }}>
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && !error && (
          <div className="flex items-center justify-center py-16" style={{ color: "#9A9080" }}>
            <Loader2 size={20} className="animate-spin" />
          </div>
        )}

        {/* Empty */}
        {!loading && !error && videos.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-2"
            style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
            <Film size={32} style={{ opacity: 0.3 }} />
            <p style={{ fontSize: 14 }}>Nenhum vídeo neste projecto.</p>
          </div>
        )}

        {/* Table */}
        {!loading && videos.length > 0 && (
          <div style={{
            background: "#fff", borderRadius: 16,
            border: "1px solid #E7DECF", overflow: "hidden",
          }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{
                width: "100%", borderCollapse: "collapse",
                fontFamily: "IBM Plex Sans, sans-serif", fontSize: 13,
              }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #EFE8DB" }}>
                    {["Ficheiro", "Câmera", "Captura", "Espécies", "Aparições", "Status", "Acções"].map((h) => (
                      <th key={h} style={{
                        padding: "10px 14px", textAlign: "left",
                        fontSize: 11, fontWeight: 600, color: "#9A9080",
                        letterSpacing: "0.04em", textTransform: "uppercase",
                        whiteSpace: "nowrap",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {videos.map((v, idx) => {
                    const st = statusStyle(v.display_status);
                    return (
                      <tr key={v.video_id}
                        style={{
                          borderBottom: idx < videos.length - 1 ? "1px solid #F5F0EA" : "none",
                        }}
                      >
                        <td style={{ padding: "10px 14px", maxWidth: 240 }}>
                          <span style={{
                            fontFamily: "IBM Plex Mono, monospace", fontSize: 12,
                            color: "#221F1A", overflow: "hidden", textOverflow: "ellipsis",
                            whiteSpace: "nowrap", display: "block",
                          }}
                            title={v.original_filename ?? v.video_id}
                          >
                            {v.original_filename ?? (v.video_id.slice(0, 16) + "…")}
                          </span>
                        </td>
                        <td style={{ padding: "10px 14px", color: "#6B6357", whiteSpace: "nowrap" }}>
                          {v.camera_id ?? "—"}
                        </td>
                        <td style={{ padding: "10px 14px", whiteSpace: "nowrap", color: "#6B6357",
                          fontFamily: "IBM Plex Mono, monospace", fontSize: 12 }}>
                          {formatDate(v.captured_at ?? v.uploaded_at)}
                        </td>
                        <td style={{ padding: "10px 14px" }}>
                          {v.species.length === 0 ? (
                            <span style={{ color: "#C5B9AD", fontStyle: "italic" }}>—</span>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {v.species.map((sp) => (
                                <span key={sp} style={{
                                  padding: "2px 7px", borderRadius: 5,
                                  background: "#EEF5F0", color: "#2F6B4F",
                                  fontSize: 11, fontStyle: "italic", whiteSpace: "nowrap",
                                }}>
                                  {sp}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "10px 14px", textAlign: "center",
                          fontFamily: "IBM Plex Mono, monospace", color: "#6B6357" }}>
                          {v.appearance_count}
                        </td>
                        <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                          <span style={{
                            padding: "3px 9px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                            background: st.bg, color: st.color,
                          }}>
                            {v.display_status}
                          </span>
                        </td>
                        <td style={{ padding: "10px 14px" }}>
                          <div className="flex items-center gap-2">
                            <a
                              href={`/review?video=${v.video_id}`}
                              title="Abrir em Revisão"
                              style={{
                                display: "flex", alignItems: "center", gap: 4,
                                padding: "5px 9px", borderRadius: 8,
                                border: "1px solid #E7DECF", background: "#fff",
                                fontSize: 12, color: "#6B6357", textDecoration: "none",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <ExternalLink size={11} />
                              Revisão
                            </a>
                            <button
                              onClick={() => handleDelete(v.video_id, v.original_filename)}
                              disabled={deleting === v.video_id}
                              title="Apagar vídeo"
                              style={{
                                display: "flex", alignItems: "center",
                                padding: "5px 7px", borderRadius: 8,
                                border: "1px solid #EBDADA", background: "#fff",
                                cursor: deleting === v.video_id ? "not-allowed" : "pointer",
                                color: deleting === v.video_id ? "#C5B9AD" : "#C0392B",
                                opacity: deleting === v.video_id ? 0.6 : 1,
                              }}
                            >
                              {deleting === v.video_id
                                ? <Loader2 size={13} className="animate-spin" />
                                : <Trash2 size={13} />
                              }
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Summary footer */}
        {!loading && videos.length > 0 && (
          <div style={{
            display: "flex", gap: 16, fontSize: 12,
            color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif",
          }}>
            <span>{videos.length} vídeo{videos.length !== 1 ? "s" : ""}</span>
            <span>·</span>
            <span>{videos.filter((v) => v.display_status === "Revisado").length} revisado{videos.filter((v) => v.display_status === "Revisado").length !== 1 ? "s" : ""}</span>
            <span>·</span>
            <span>{videos.filter((v) => v.display_status === "Aguardando revisão").length} aguardando revisão</span>
            <span>·</span>
            <span>{videos.filter((v) => v.display_status === "Processando").length} a processar</span>
          </div>
        )}

      </main>
    </div>
  );
}
