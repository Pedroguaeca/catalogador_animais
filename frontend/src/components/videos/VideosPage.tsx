"use client";

import { useMemo, useState } from "react";
import { Film, Loader2, RefreshCw, AlertCircle } from "lucide-react";
import type { VideoItem } from "../../lib/videoTypes";
import type { Project, Client } from "../../lib/projectTypes";
import { StatusTabs, type TabKey } from "./StatusTabs";
import { FilterRail, type ChipCount, type Filters } from "./FilterRail";
import { VideoCard } from "./VideoCard";
import { SidePanel } from "./SidePanel";
import { ProjectSelector } from "../ProjectSelector";

const DEFAULT_FILTERS: Filters = {
  cameraId: null, species: null, minConfidence: 0, semDeteccaoOnly: false,
};

// A API pode estar numa versão anterior ao SIAB-105 (deploy de frontend e
// backend é manual e separado — ver CLAUDE.md) e simplesmente não mandar os
// campos novos. `undefined` (campo ausente) é diferente de `null` (campo
// presente, sem dado) — sem isso, .length/.map em ai_species undefined
// derruba a página inteira com "Application error".
function normalizeVideo(v: VideoItem): VideoItem {
  return {
    ...v,
    ai_species:    v.ai_species    ?? [],
    confidence:    v.confidence    ?? null,
    thumbnail_url: v.thumbnail_url ?? null,
    reviewed_by:   v.reviewed_by   ?? null,
    reviewed_at:   v.reviewed_at   ?? null,
    temperature_c: v.temperature_c ?? null,
  };
}

function tabForVideo(v: VideoItem): TabKey {
  if (v.display_status === "Processando") return "processando";
  if (v.display_status === "Revisado")    return "revisado";
  // "Sem detecção" entra em Aguardando revisão como categoria própria — ainda
  // precisa de alguém confirmar se é vazio de verdade ou falso negativo.
  return "aguardando";
}

function countBy(videos: VideoItem[], pick: (v: VideoItem) => string[], none: string): ChipCount[] {
  const counts = new Map<string, number>();
  for (const v of videos) {
    const values = pick(v);
    if (values.length === 0) {
      counts.set(none, (counts.get(none) ?? 0) + 1);
      continue;
    }
    for (const val of values) counts.set(val, (counts.get(val) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({ value, label: value === none ? "Sem câmera" : value, count }));
}

interface VideosPageProps {
  videos:          VideoItem[];
  loading:         boolean;
  error:           string | null;
  onRefresh:       () => void;
  projects:        Project[];
  clients:         Client[];
  projectId:       string;
  onProjectChange: (projectId: string) => void;
}

export function VideosPage({
  videos: rawVideos, loading, error, onRefresh,
  projects, clients, projectId, onProjectChange,
}: VideosPageProps) {
  const [activeTab, setActiveTab]           = useState<TabKey>("aguardando");
  const [filters, setFilters]               = useState<Filters>(DEFAULT_FILTERS);
  const [sortOrder, setSortOrder]           = useState<"asc" | "desc">("desc");
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);

  const videos = useMemo(() => rawVideos.map(normalizeVideo), [rawVideos]);

  function changeTab(tab: TabKey) {
    setActiveTab(tab);
    setFilters(DEFAULT_FILTERS);
    setSelectedVideoId(null);
  }

  const counts = useMemo<Record<TabKey, number>>(() => {
    const c: Record<TabKey, number> = { aguardando: 0, processando: 0, revisado: 0 };
    for (const v of videos) c[tabForVideo(v)]++;
    return c;
  }, [videos]);

  const tabVideos = useMemo(
    () => videos.filter((v) => tabForVideo(v) === activeTab),
    [videos, activeTab],
  );

  const cameraChips = useMemo(
    () => countBy(tabVideos, (v) => [v.camera_id ?? "__none__"], "__none__"),
    [tabVideos],
  );
  const speciesChips = useMemo(
    () => countBy(tabVideos, (v) => (activeTab === "revisado" ? v.species : v.ai_species), "__none__")
      .filter((c) => c.value !== "__none__"),
    [tabVideos, activeTab],
  );

  const confidenceDisabled = activeTab === "processando";

  const filteredVideos = useMemo(() => {
    let list = tabVideos;
    if (filters.cameraId !== null) {
      list = list.filter((v) => (v.camera_id ?? "__none__") === filters.cameraId);
    }
    if (filters.species !== null) {
      list = list.filter((v) =>
        (activeTab === "revisado" ? v.species : v.ai_species).includes(filters.species as string),
      );
    }
    if (filters.semDeteccaoOnly) {
      list = list.filter((v) => v.display_status === "Sem detecção");
    } else if (!confidenceDisabled && filters.minConfidence > 0) {
      list = list.filter((v) => v.confidence !== null && v.confidence * 100 >= filters.minConfidence);
    }
    return [...list].sort((a, b) => {
      const da = a.captured_at ?? a.uploaded_at ?? "";
      const db = b.captured_at ?? b.uploaded_at ?? "";
      return sortOrder === "asc" ? da.localeCompare(db) : db.localeCompare(da);
    });
  }, [tabVideos, filters, activeTab, confidenceDisabled, sortOrder]);

  const selectedVideo = filteredVideos.find((v) => v.video_id === selectedVideoId) ?? filteredVideos[0] ?? null;

  return (
    <main className="flex flex-col flex-1 px-6 py-6 gap-4" style={{ maxWidth: 1240, width: "100%", margin: "0 auto" }}>

      {/* Header */}
      <div className="flex items-center gap-3">
        <Film size={18} style={{ color: "#2F6B4F" }} />
        <h1 style={{ fontSize: 18, fontWeight: 700, color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif" }}>
          Vídeos
        </h1>
        <ProjectSelector
          projects={projects}
          clients={clients}
          value={projectId}
          onChange={onProjectChange}
          style={{ padding: "4px 28px 4px 10px", fontSize: 12, borderRadius: 8 }}
        />
        <div style={{ flex: 1 }} />
        <button
          onClick={onRefresh}
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

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl"
          style={{ background: "#FBF0F0", color: "#C0392B", fontSize: 13 }}>
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {loading && !error && (
        <div className="flex items-center justify-center py-16" style={{ color: "#9A9080" }}>
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {!loading && !error && (
        <>
          <StatusTabs active={activeTab} counts={counts} onChange={changeTab} />

          {videos.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-2"
              style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
              <Film size={32} style={{ opacity: 0.3 }} />
              <p style={{ fontSize: 14 }}>Nenhum vídeo neste projecto.</p>
            </div>
          ) : (
            <div className="flex gap-5 items-start">
              <FilterRail
                cameras={cameraChips}
                species={speciesChips}
                filters={filters}
                onChange={setFilters}
                confidenceDisabled={confidenceDisabled}
                showSemDeteccaoToggle={activeTab === "aguardando"}
                sortOrder={sortOrder}
                onSortOrderChange={setSortOrder}
              />

              <div className="flex flex-col gap-2" style={{ flex: 1, minWidth: 0 }}>
                {tabVideos.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-2"
                    style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
                    <p style={{ fontSize: 13 }}>Nenhum vídeo nesta aba.</p>
                  </div>
                ) : filteredVideos.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-2"
                    style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
                    <p style={{ fontSize: 13 }}>Nenhum vídeo corresponde aos filtros.</p>
                  </div>
                ) : (
                  filteredVideos.map((v) => (
                    <VideoCard
                      key={v.video_id}
                      video={v}
                      selected={v.video_id === selectedVideo?.video_id}
                      onClick={() => setSelectedVideoId(v.video_id)}
                    />
                  ))
                )}
              </div>

              <SidePanel video={selectedVideo} />
            </div>
          )}
        </>
      )}

    </main>
  );
}
