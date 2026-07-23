"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { SiabNav } from "../../src/components/SiabNav";
import { ReviewPage } from "../../src/components/ReviewPage";
import { API_BASE, apiHeaders } from "../../src/lib/api";
import type { Video, Frame } from "../../src/lib/types";

const PROJECT_ID = "projeto-junho-2026";

interface ApiVideoItem {
  video_id:          string;
  original_filename: string | null;
  display_status:    string;
}

interface ApiFrameItem {
  video_id:          string;
  frame_idx:         number;
  thumbnail_url:     string | null;
  ai_species:        string | null;
  ai_score:          number | null;
  bbox:              [number, number, number, number] | null;
  annotated_species: string | null;
  novo_evento?:      boolean | null;
  tem_filhote?:      boolean | null;
  individual_count?: number | null;
  annotated_at?:      string | null;
}

// Frame-annotations só existem para frames onde o MegaDetector encontrou algo
// (ver docs/pipeline.md) — por isso "empty" nunca ocorre aqui na prática.
function mapFrames(items: ApiFrameItem[]): Frame[] {
  return items.map((f, i): Frame => ({
    idx: i + 1,
    rawFrameIdx: f.frame_idx,
    path: `${f.video_id}/frame_${String(f.frame_idx).padStart(5, "0")}.jpg`,
    imageUrl: f.thumbnail_url ?? undefined,
    video_uuid: f.video_id,
    timestamp: "",
    date: "",
    time: "",
    detection: f.ai_species ? {
      genus: f.ai_species,
      genus_pt: f.ai_species,
      det_conf: f.ai_score ?? 0,
      cls_conf: f.ai_score ?? 0,
      bbox: f.bbox ?? [0, 0, 0, 0],
      bboxNormalized: true,
    } : null,
    // status alimenta o dot do Filmstrip: aqui usado como "confirmado" vs "pendente",
    // não como faixa de confiança da IA (que é o uso original no /  local).
    status: f.annotated_species ? "detection" : (f.ai_score ?? 0) > 0 ? "review" : "empty",
    novoEvento: f.novo_evento ?? false,
    temFilhote: f.tem_filhote ?? false,
    annotatedSpecies: f.annotated_species ?? undefined,
    annotatedAt: f.annotated_at ?? undefined,
    individualCount: f.individual_count ?? 1,
  }));
}

function ReviewPageDataLoader() {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;
  const searchParams = useSearchParams();
  const initialVideoId = searchParams.get("video") ?? undefined;

  const [videos,  setVideos]  = useState<Video[] | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    if (!idToken) return;
    let cancelled = false;

    (async () => {
      try {
        const listRes = await fetch(`${API_BASE}/projects/${PROJECT_ID}/videos`, {
          headers: apiHeaders(idToken),
        });
        if (!listRes.ok) throw new Error(`HTTP ${listRes.status}`);
        const listData = await listRes.json();
        const items: ApiVideoItem[] = listData.videos ?? [];

        const withFrames = await Promise.all(items.map(async (v) => {
          const r = await fetch(
            `${API_BASE}/projects/${PROJECT_ID}/videos/${v.video_id}/frames`,
            { headers: apiHeaders(idToken) },
          );
          if (!r.ok) {
            return {
              id: v.video_id,
              original_filename: v.original_filename,
              display_status:    v.display_status,
              frames: [],
            };
          }
          const d = await r.json();
          return {
            id: v.video_id,
            original_filename: v.original_filename,
            display_status:    v.display_status,
            frames: mapFrames(d.frames ?? []),
          };
        }));

        if (!cancelled) setVideos(withFrames);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Erro ao carregar dados");
      }
    })();

    return () => { cancelled = true; };
  }, [idToken]);

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2 p-6" style={{ color: "#C2503A" }}>
        <AlertCircle size={16} />
        <span className="text-sm">{error}</span>
      </div>
    );
  }

  if (!videos) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: "#9A9080" }}>
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  if (videos.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2" style={{ color: "#9A9080" }}>
        <CheckCircle2 size={28} style={{ color: "#5FD08A" }} />
        <p className="text-sm">Nenhum vídeo neste projeto ainda.</p>
      </div>
    );
  }

  return <ReviewPage videos={videos} initialVideoId={initialVideoId} projectId={PROJECT_ID} />;
}

export default function Review() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <SiabNav />
      <Suspense fallback={null}>
        <ReviewPageDataLoader />
      </Suspense>
    </div>
  );
}
