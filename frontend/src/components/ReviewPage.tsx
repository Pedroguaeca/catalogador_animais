"use client";

import { useReducer, useEffect, useState, useCallback, useRef } from "react";
import { reviewReducer, initialState } from "../lib/reducer";
import type { Video } from "../lib/types";
import { TopBar } from "./TopBar";
import { FrameStage } from "./FrameStage";
import { Filmstrip } from "./Filmstrip";
import { IdentificationPanel } from "./IdentificationPanel";
import { BottomBar } from "./BottomBar";
import { CompletionCelebration } from "./CompletionCelebration";

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

  // Overrides otimistas de novo_evento/tem_filhote — os frames vêm do fetch inicial
  // (não são recarregados após cada PATCH), então a marcação local sobrepõe o valor
  // vindo da API até a próxima troca de página. Chave = frame.path (único no projeto).
  const [novoEventoOverrides, setNovoEventoOverrides] = useState<Record<string, boolean>>({});
  const [temFilhoteOverrides, setTemFilhoteOverrides] = useState<Record<string, boolean>>({});

  const currentVideo = videos.find((v) => v.id === state.videoId) ?? videos[0];
  const videoIdx = videos.findIndex((v) => v.id === state.videoId);
  const frames = currentVideo?.frames ?? [];
  const frame = frames[state.frameIdx - 1] ?? null;
  const totalFrames = frames.length;

  const novoEventoMarked = frame ? (novoEventoOverrides[frame.path] ?? frame.novoEvento ?? false) : false;
  const temFilhote = frame ? (temFilhoteOverrides[frame.path] ?? frame.temFilhote ?? false) : false;

  // Atalhos de teclado
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "Enter") {
        if (frame?.detection) {
          dispatch({ type: "CONFIRM_AI" });
          dispatch({ type: "MARK_ANNOTATED" });
        }
      }
      if (e.key === "ArrowRight") dispatch({ type: "NEXT_FRAME" });
      if (e.key === "ArrowLeft") dispatch({ type: "PREV_FRAME" });
      if (e.key === "s" || e.key === "S") dispatch({ type: "SKIP_FRAME" });
    },
    [frame]
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

  // Celebração: só quando o vídeo ATUAL vira totalmente revisado (transição
  // "aguardando revisão" → "revisado"), nunca a cada frame confirmado.
  // `null` = ainda não sabemos o estado anterior deste vídeo (troca/carregamento
  // inicial) — evita comemorar por engano ao entrar num vídeo já completo.
  const [celebrate, setCelebrate] = useState(false);
  const prevFullyAnnotatedRef = useRef<boolean | null>(null);

  useEffect(() => {
    prevFullyAnnotatedRef.current = null;
    setCelebrate(false);
  }, [state.videoId]);

  useEffect(() => {
    const isFull = totalFrames > 0 && state.annotated >= totalFrames;
    const prev = prevFullyAnnotatedRef.current;
    if (prev === false && isFull) {
      setCelebrate(true);
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

  return (
    <div
      className="flex flex-col flex-1 min-h-0 overflow-hidden"
      style={{ background: "#FAF6EE", fontFamily: "IBM Plex Sans, sans-serif" }}
    >
      <CompletionCelebration active={celebrate} />

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
          />
          <Filmstrip
            frames={frames}
            frameIdx={state.frameIdx}
            onSelect={(idx) => dispatch({ type: "SET_FRAME", payload: idx })}
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
            dispatch({ type: "SELECT", payload: id });
            dispatch({ type: "MARK_ANNOTATED" });
            if (frame?.path) {
              const name = state.categories.find((c) => c.id === id)?.name ?? id;
              persistFrameAnnotation(state.videoId, frame.path, name, "chip_select", idToken);
            }
          }}
          onConfirmAI={() => {
            dispatch({ type: "CONFIRM_AI" });
            dispatch({ type: "MARK_ANNOTATED" });
            if (frame?.path && frame.detection) {
              persistFrameAnnotation(state.videoId, frame.path, frame.detection.genus, "ai_confirm", idToken);
            }
          }}
          onConfirmVideo={() => {
            dispatch({ type: "CONFIRM_ALL_VIDEO", payload: totalFrames });
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
            dispatch({ type: "MARK_ANNOTATED" });
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
        />
      </div>

      <BottomBar
        videoIdx={videoIdx}
        totalVideos={videos.length}
        onPrevVideo={() => {
          if (videoIdx > 0) {
            const v = videos[videoIdx - 1];
            dispatch({ type: "SET_VIDEO", payload: { videoId: v.id, frames: v.frames } });
          }
        }}
        onNextVideo={() => {
          if (videoIdx < videos.length - 1) {
            const v = videos[videoIdx + 1];
            dispatch({ type: "SET_VIDEO", payload: { videoId: v.id, frames: v.frames } });
          }
        }}
      />
    </div>
  );
}
