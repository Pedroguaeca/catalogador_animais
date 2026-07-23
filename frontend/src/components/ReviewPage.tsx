"use client";

import { useReducer, useEffect, useState, useCallback, useRef, useMemo } from "react";
import { reviewReducer, initialState } from "../lib/reducer";
import type { Video, Frame, VideoSegment } from "../lib/types";
import { TopBar } from "./TopBar";
import { FrameStage } from "./FrameStage";
import { Filmstrip } from "./Filmstrip";
import { SegmentStrip } from "./SegmentStrip";
import { IdentificationPanel } from "./IdentificationPanel";
import { CompletionCelebration } from "./CompletionCelebration";
import { CheckoutModal, type CheckoutValues } from "./CheckoutModal";

import { useSession } from "next-auth/react";
import { API_BASE, apiHeaders } from "../lib/api";

function persistFrameAnnotation(
  videoId: string,
  framePath: string,
  annotatedSpecies: string,
  source: "ai_confirm" | "chip_select" | "new_category",
  idToken?: string,
) {
  const video_uuid = framePath.split("/")[0] ?? "";
  if (!video_uuid || !framePath) return;
  fetch(`${API_BASE}/frames/annotation`, {
    method: "PATCH",
    headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({
      video_id:          video_uuid,
      frame_path:        framePath,
      annotated_species: annotatedSpecies,
      annotation_source: source,
    }),
  }).catch(() => {});
}

interface ReviewPageProps {
  videos: Video[];
  initialVideoId?: string;
  projectId?: string;
}

function confirmAllVideoOnServer(projectId: string, videoId: string, idToken?: string) {
  if (!videoId) return;
  fetch(`${API_BASE}/projects/${projectId}/videos/${videoId}/confirm-all`, {
    method: "POST",
    headers: apiHeaders(idToken),
  }).catch(() => {});
}

function persistFrameFlag(
  endpoint: "novo-evento" | "tem-filhote",
  videoId: string,
  framePath: string,
  value: boolean,
  idToken?: string,
) {
  if (!videoId || !framePath) return;
  fetch(`${API_BASE}/frames/${endpoint}`, {
    method: "PATCH",
    headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({ video_id: videoId, frame_path: framePath, value }),
  }).catch(() => {});
}

function persistFrameIndividualCount(videoId: string, framePath: string, value: number, idToken?: string) {
  if (!videoId || !framePath) return;
  fetch(`${API_BASE}/frames/individual-count`, {
    method: "PATCH",
    headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({ video_id: videoId, frame_path: framePath, value }),
  }).catch(() => {});
}

function finalizeSegment(videoId: string, values: CheckoutValues, idToken?: string) {
  return fetch(`${API_BASE}/appearances/individual-count`, {
    method: "PATCH",
    headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({
      video_id:          videoId,
      species:           values.species,
      segment:           values.segment,
      individual_count:  values.individualCount,
      tem_filhote:       values.temFilhote,
    }),
  }).catch(() => {});
}

// Espelha _frame_segments_for_video (backend/api.py) inteiramente no cliente:
// mesma regra (video_id, annotated_species, segmento — segmento incrementa a
// cada novo_evento, contador único por vídeo). Calculado a partir do estado já
// carregado, sem round-trip ao servidor — evita corrida entre "acabei de
// confirmar o último frame" e "o GET /segments ainda não viu essa escrita".
interface ComputedSegments {
  segments: VideoSegment[];
  // frame.path → chave "species#segment", pra destacar a linha ativa na faixa
  // de segmentos sem depender de sobreposição de faixas de frame_idx entre
  // espécies diferentes.
  segmentKeyByFramePath: Record<string, string>;
}

function computeSegments(
  frames: Frame[],
  annotatedSpecies: Record<number, string>,
  novoEventoOverrides: Record<string, boolean>,
  individualCountOverrides: Record<string, number>,
  temFilhoteOverrides: Record<string, boolean>,
): ComputedSegments {
  let segment = 0;
  const groups = new Map<string, { species: string; segment: number; members: Frame[] }>();
  const segmentKeyByFramePath: Record<string, string> = {};

  for (const f of frames) {
    const novoEvento = novoEventoOverrides[f.path] ?? f.novoEvento ?? false;
    if (novoEvento) segment += 1;
    const species = annotatedSpecies[f.idx];
    if (!species) continue;
    const key = `${species}#${segment}`;
    if (!groups.has(key)) groups.set(key, { species, segment, members: [] });
    groups.get(key)!.members.push(f);
    segmentKeyByFramePath[f.path] = key;
  }

  const segments = Array.from(groups.values())
    .map(({ species, segment, members }) => {
      const counts = members.map((f) => individualCountOverrides[f.path] ?? f.individualCount ?? 1);
      const idxs = members.map((f) => f.rawFrameIdx);
      return {
        species,
        segment,
        frame_start:      Math.min(...idxs),
        frame_end:        Math.max(...idxs),
        frame_count:      members.length,
        individual_count: Math.max(...counts),
        tem_filhote:      members.some((f) => temFilhoteOverrides[f.path] ?? f.temFilhote ?? false),
      };
    })
    .sort((a, b) => a.frame_start - b.frame_start);

  return { segments, segmentKeyByFramePath };
}

export function ReviewPage({ videos, initialVideoId, projectId }: ReviewPageProps) {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;

  const firstVideoId = (initialVideoId && videos.some((v) => v.id === initialVideoId))
    ? initialVideoId
    : videos[0]?.id ?? "";
  const [state, dispatch] = useReducer(
    reviewReducer,
    initialState(firstVideoId, videos.find((v) => v.id === firstVideoId)?.frames ?? [])
  );
  const [zoom, setZoom] = useState(false);

  // Overrides otimistas de novo_evento/tem_filhote/individual_count — os frames
  // vêm do fetch inicial (não são recarregados após cada PATCH), então a marcação
  // local sobrepõe o valor vindo da API até a próxima troca de página. Chave =
  // frame.path (único no projeto).
  const [novoEventoOverrides, setNovoEventoOverrides] = useState<Record<string, boolean>>({});
  const [temFilhoteOverrides, setTemFilhoteOverrides] = useState<Record<string, boolean>>({});
  const [individualCountOverrides, setIndividualCountOverrides] = useState<Record<string, number>>({});

  const currentVideo = videos.find((v) => v.id === state.videoId) ?? videos[0];
  const videoIdx = videos.findIndex((v) => v.id === state.videoId);
  const frames = currentVideo?.frames ?? [];
  const frame = frames[state.frameIdx - 1] ?? null;
  const totalFrames = frames.length;

  const novoEventoMarked = frame ? (novoEventoOverrides[frame.path] ?? frame.novoEvento ?? false) : false;
  const temFilhote = frame ? (temFilhoteOverrides[frame.path] ?? frame.temFilhote ?? false) : false;
  const individualCount = frame ? (individualCountOverrides[frame.path] ?? frame.individualCount ?? 1) : 1;

  // Fonte única do "revisado" — Filmstrip, FrameStage e o painel de identificação
  // leem os três daqui. Corrigir a espécie atualiza annotatedSpecies e os 3
  // re-renderizam juntos, sem estado duplicado.
  const isFrameAnnotated = state.annotatedFrames.has(state.frameIdx);
  const annotatedSpeciesLabel = state.annotatedSpecies[state.frameIdx] ?? null;
  const annotatedAtLabel = state.annotatedAt[state.frameIdx] ?? null;

  const { segments, segmentKeyByFramePath } = useMemo(
    () => computeSegments(frames, state.annotatedSpecies, novoEventoOverrides, individualCountOverrides, temFilhoteOverrides),
    [frames, state.annotatedSpecies, novoEventoOverrides, individualCountOverrides, temFilhoteOverrides]
  );
  const activeSegmentKey = frame ? segmentKeyByFramePath[frame.path] ?? null : null;

  const confirmFrame = useCallback(() => {
    if (!frame?.detection) return;
    dispatch({ type: "CONFIRM_AI" });
    dispatch({ type: "MARK_ANNOTATED", payload: { species: frame.detection.genus_pt } });
    if (frame.path) persistFrameAnnotation(state.videoId, frame.path, frame.detection.genus, "ai_confirm", idToken);
  }, [frame, state.videoId, idToken]);

  // Atalhos de teclado
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "Enter") confirmFrame();
      if (e.key === "ArrowRight") dispatch({ type: "NEXT_FRAME" });
      if (e.key === "ArrowLeft") dispatch({ type: "PREV_FRAME" });
      if (e.key === "s" || e.key === "S") dispatch({ type: "SKIP_FRAME" });
    },
    [confirmFrame]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [handleKey]);

  const handleJumpToFirstUnannotated = useCallback(() => {
    for (let i = 1; i <= totalFrames; i++) {
      if (!state.annotatedFrames.has(i)) {
        dispatch({ type: "SET_FRAME", payload: i });
        return;
      }
    }
  }, [state.annotatedFrames, totalFrames]);

  const jumpToSegment = useCallback((seg: VideoSegment) => {
    const target = frames.find((f) => f.rawFrameIdx === seg.frame_start);
    if (target) dispatch({ type: "SET_FRAME", payload: target.idx });
  }, [frames]);

  // Navegação de vídeo — migrada da barra inferior pro painel lateral (Tarefa 2, 23/07).
  const goToPrevVideo = useCallback(() => {
    if (videoIdx > 0) {
      const v = videos[videoIdx - 1];
      dispatch({ type: "SET_VIDEO", payload: { videoId: v.id, frames: v.frames } });
    }
  }, [videos, videoIdx]);

  const goToNextVideo = useCallback(() => {
    if (videoIdx < videos.length - 1) {
      const v = videos[videoIdx + 1];
      dispatch({ type: "SET_VIDEO", payload: { videoId: v.id, frames: v.frames } });
    }
  }, [videos, videoIdx]);

  // Checkout: ao completar um vídeo INTEIRO (transição "aguardando revisão" →
  // "revisado"), abre o modal de consolidação em vez de celebrar direto — a
  // celebração só dispara depois que o revisor confirma o checkout.
  // `null` = ainda não sabemos o estado anterior deste vídeo (troca/carregamento
  // inicial) — evita abrir o modal por engano ao entrar num vídeo já completo.
  const [celebrate, setCelebrate] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const prevFullyAnnotatedRef = useRef<boolean | null>(null);

  useEffect(() => {
    prevFullyAnnotatedRef.current = null;
    setCelebrate(false);
    setCheckoutOpen(false);
  }, [state.videoId]);

  useEffect(() => {
    const isFull = totalFrames > 0 && state.annotated >= totalFrames;
    const prev = prevFullyAnnotatedRef.current;
    if (prev === false && isFull) {
      setCheckoutOpen(true);
    }
    prevFullyAnnotatedRef.current = isFull;
  }, [state.annotated, totalFrames]);

  // Timer de auto-hide isolado num effect próprio (dependência só de `celebrate`).
  // Antes, o timeout vivia no effect acima e sua cleanup rodava sempre que
  // totalFrames/annotated mudava (ex.: troca de vídeo logo após completar um) —
  // cancelava o setCelebrate(false) pendente sem reagendar, deixando o overlay
  // preso em `true` para sempre.
  useEffect(() => {
    if (!celebrate) return;
    const t = setTimeout(() => setCelebrate(false), 500);
    return () => clearTimeout(t);
  }, [celebrate]);

  const goToNextPendingVideo = useCallback(() => {
    for (let i = 1; i <= videos.length; i++) {
      const v = videos[(videoIdx + i) % videos.length];
      if (v.display_status === "Aguardando revisão") {
        dispatch({ type: "SET_VIDEO", payload: { videoId: v.id, frames: v.frames } });
        return;
      }
    }
  }, [videos, videoIdx]);

  const handleCheckoutConfirm = useCallback((values: CheckoutValues[]) => {
    setCheckoutOpen(false);
    Promise.all(values.map((v) => finalizeSegment(state.videoId, v, idToken))).finally(() => {
      setCelebrate(true);
      goToNextPendingVideo();
    });
  }, [state.videoId, idToken, goToNextPendingVideo]);

  return (
    <div
      className="flex flex-col flex-1 min-h-0 overflow-hidden"
      style={{ background: "#FAF6EE", fontFamily: "IBM Plex Sans, sans-serif" }}
    >
      <CompletionCelebration active={celebrate} />
      <CheckoutModal
        open={checkoutOpen}
        segments={segments}
        onClose={() => setCheckoutOpen(false)}
        onConfirm={handleCheckoutConfirm}
      />

      <TopBar
        videoId={state.videoId}
        videos={videos.map((v) => ({
          id: v.id,
          label: v.original_filename || v.id,
          display_status: v.display_status,
        }))}
        frameIdx={state.frameIdx}
        totalFrames={totalFrames}
        videoIdx={videoIdx}
        totalVideos={videos.length}
        annotated={state.annotated}
        onVideoChange={(id) => dispatch({
          type: "SET_VIDEO",
          payload: { videoId: id, frames: videos.find((v) => v.id === id)?.frames ?? [] },
        })}
        onJumpUnannotated={handleJumpToFirstUnannotated}
      />

      {/* Body */}
      <div className="flex-1 flex gap-5 p-5 min-h-0">
        {/* Coluna palco */}
        <div className="flex-1 flex flex-col gap-3.5 min-w-0">
          <FrameStage
            frame={frame}
            zoom={zoom}
            onToggleZoom={() => setZoom((z) => !z)}
            isAnnotated={isFrameAnnotated}
          />
          <Filmstrip
            frames={frames}
            frameIdx={state.frameIdx}
            onSelect={(idx) => dispatch({ type: "SET_FRAME", payload: idx })}
            annotatedFrames={state.annotatedFrames}
          />
          <SegmentStrip
            segments={segments}
            activeSegmentKey={activeSegmentKey}
            onSelect={jumpToSegment}
          />
        </div>

        {/* Painel de identificação */}
        <IdentificationPanel
          detection={frame?.detection ?? null}
          categories={state.categories}
          query={state.query}
          selected={state.selected}
          confirmed={state.confirmed}
          newCatOpen={state.newCatOpen}
          newCatName={state.newCatName}
          frameIdx={state.frameIdx}
          totalFrames={totalFrames}
          onQuery={(q) => dispatch({ type: "SET_QUERY", payload: q })}
          onSelect={(id) => {
            const name = state.categories.find((c) => c.id === id)?.name ?? id;
            dispatch({ type: "SELECT", payload: id });
            dispatch({ type: "MARK_ANNOTATED", payload: { species: name } });
            if (frame?.path) {
              persistFrameAnnotation(state.videoId, frame.path, name, "chip_select", idToken);
            }
          }}
          onConfirmAI={confirmFrame}
          onConfirmVideo={() => {
            dispatch({ type: "CONFIRM_ALL_VIDEO", payload: { frames } });
            if (projectId) confirmAllVideoOnServer(projectId, state.videoId, idToken);
          }}
          onReject={() => dispatch({ type: "REJECT" })}
          onPrevFrame={() => dispatch({ type: "PREV_FRAME" })}
          onNextFrame={() => dispatch({ type: "NEXT_FRAME" })}
          onSkipFrame={() => dispatch({ type: "SKIP_FRAME" })}
          onOpenNewCat={() => dispatch({ type: "OPEN_NEW_CAT" })}
          onCloseNewCat={() => dispatch({ type: "CLOSE_NEW_CAT" })}
          onNewCatName={(n) => dispatch({ type: "SET_NEW_CAT_NAME", payload: n })}
          onAddCategory={(name) => {
            dispatch({ type: "ADD_CATEGORY", payload: name });
            dispatch({ type: "MARK_ANNOTATED", payload: { species: name } });
            if (frame?.path) {
              persistFrameAnnotation(state.videoId, frame.path, name, "new_category", idToken);
            }
          }}
          novoEventoMarked={novoEventoMarked}
          onMarkNovoEvento={() => {
            if (!frame?.path) return;
            const next = !novoEventoMarked;
            setNovoEventoOverrides((prev) => ({ ...prev, [frame.path]: next }));
            persistFrameFlag("novo-evento", state.videoId, frame.path, next, idToken);
          }}
          temFilhote={temFilhote}
          onToggleTemFilhote={(value) => {
            if (!frame?.path) return;
            setTemFilhoteOverrides((prev) => ({ ...prev, [frame.path]: value }));
            persistFrameFlag("tem-filhote", state.videoId, frame.path, value, idToken);
          }}
          isAnnotated={isFrameAnnotated}
          annotatedSpeciesLabel={annotatedSpeciesLabel}
          annotatedAt={annotatedAtLabel}
          individualCount={individualCount}
          onChangeIndividualCount={(n) => {
            if (!frame?.path) return;
            setIndividualCountOverrides((prev) => ({ ...prev, [frame.path]: n }));
            persistFrameIndividualCount(state.videoId, frame.path, n, idToken);
          }}
          videoIdx={videoIdx}
          totalVideos={videos.length}
          onPrevVideo={goToPrevVideo}
          onNextVideo={goToNextVideo}
        />
      </div>
    </div>
  );
}
