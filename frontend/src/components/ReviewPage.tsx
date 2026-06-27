"use client";

import { useReducer, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { reviewReducer, initialState } from "../lib/reducer";
import type { Video } from "../lib/types";
import { TopBar } from "./TopBar";
import { FrameStage } from "./FrameStage";
import { Filmstrip } from "./Filmstrip";
import { IdentificationPanel } from "./IdentificationPanel";
import { BottomBar } from "./BottomBar";
import { UploadModal } from "./UploadModal";

interface ReviewPageProps {
  videos: Video[];
}

export function ReviewPage({ videos }: ReviewPageProps) {
  const firstVideoId = videos[0]?.id ?? "";
  const [state, dispatch] = useReducer(
    reviewReducer,
    initialState(firstVideoId, videos[0]?.frames.length ?? 0)
  );
  const [zoom,         setZoom]         = useState(false);
  const [uploadOpen,   setUploadOpen]   = useState(false);
  const router = useRouter();

  const currentVideo = videos.find((v) => v.id === state.videoId) ?? videos[0];
  const videoIdx = videos.findIndex((v) => v.id === state.videoId);
  const frames = currentVideo?.frames ?? [];
  const frame = frames[state.frameIdx - 1] ?? null;
  const totalFrames = frames.length;

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

  return (
    <div
      className="flex flex-col h-screen overflow-hidden"
      style={{ background: "#FAF6EE", fontFamily: "IBM Plex Sans, sans-serif" }}
    >
      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onPipelineDone={() => router.refresh()}
        />
      )}
      <TopBar
        videoId={state.videoId}
        videos={videos.map((v) => v.id)}
        frameIdx={state.frameIdx}
        totalFrames={totalFrames}
        videoIdx={videoIdx}
        totalVideos={videos.length}
        annotated={state.annotated}
        onVideoChange={(id) => dispatch({ type: "SET_VIDEO", payload: id })}
        onUpload={() => setUploadOpen(true)}
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
          onQuery={(q) => dispatch({ type: "SET_QUERY", payload: q })}
          onSelect={(id) => {
            dispatch({ type: "SELECT", payload: id });
            dispatch({ type: "MARK_ANNOTATED" });
          }}
          onConfirmAI={() => {
            dispatch({ type: "CONFIRM_AI" });
            dispatch({ type: "MARK_ANNOTATED" });
          }}
          onReject={() => dispatch({ type: "REJECT" })}
          onOpenNewCat={() => dispatch({ type: "OPEN_NEW_CAT" })}
          onCloseNewCat={() => dispatch({ type: "CLOSE_NEW_CAT" })}
          onNewCatName={(n) => dispatch({ type: "SET_NEW_CAT_NAME", payload: n })}
          onAddCategory={(name) => {
            dispatch({ type: "ADD_CATEGORY", payload: name });
            dispatch({ type: "MARK_ANNOTATED" });
          }}
        />
      </div>

      <BottomBar
        frameIdx={state.frameIdx}
        totalFrames={totalFrames}
        videoIdx={videoIdx}
        totalVideos={videos.length}
        onPrevFrame={() => dispatch({ type: "PREV_FRAME" })}
        onNextFrame={() => dispatch({ type: "NEXT_FRAME" })}
        onSkipFrame={() => dispatch({ type: "SKIP_FRAME" })}
        onPrevVideo={() => {
          if (videoIdx > 0) dispatch({ type: "SET_VIDEO", payload: videos[videoIdx - 1].id });
        }}
        onNextVideo={() => {
          if (videoIdx < videos.length - 1) dispatch({ type: "SET_VIDEO", payload: videos[videoIdx + 1].id });
        }}
      />
    </div>
  );
}
