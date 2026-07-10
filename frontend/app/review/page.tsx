"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2, XCircle, PencilLine, Loader2, AlertCircle,
  RefreshCw, X, SkipForward, Film,
} from "lucide-react";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { API_BASE, apiHeaders } from "../../src/lib/api";

const PROJECT_ID = "projeto-junho-2026";

interface Appearance {
  appearance_id:      string;
  species:            string;
  species_score:      number;
  camera_id:          string | null;
  ts_start:           string | null;
  support_frames:     number;
  individual_count:   number;
  review_status:      string;
  best_crop_s3_key:   string | null;
  thumbnail_url:      string | null;
  taxonomic_path:     string | null;
  video_id?:          string;
  discrepant_species: string[] | null;
  frame_start:        number | null;
  frame_end:          number | null;
  bbox:               [number, number, number, number] | null;
}

interface FrameAnnotation {
  frame_idx:         number;
  frame_path:        string;
  annotated_species: string;
  annotation_source: string;
  thumbnail_url:     string | null;
}

// Groups appearances by video. Prefers video_id; falls back to camera_id+date.
function videoKey(app: Appearance): string {
  if (app.video_id) return app.video_id;
  return `${app.camera_id ?? "unknown"}|${app.ts_start?.slice(0, 10) ?? "nodate"}`;
}

function isLowConfidence(app: Appearance): boolean {
  return app.support_frames <= 2 || app.species_score < 0.5;
}

function formatTs(ts: string | null): { date: string; time: string } {
  if (!ts) return { date: "—", time: "—" };
  try {
    const dt = new Date(ts);
    return {
      date: dt.toLocaleDateString("pt-BR"),
      time: dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    };
  } catch {
    return { date: ts, time: "" };
  }
}

// ── Small UI atoms ─────────────────────────────────────────────────────────────

function Chip({ label, accent = false }: { label: string; accent?: boolean }) {
  return (
    <span className="px-2 py-0.5 rounded-full text-xs" style={{
      background: accent ? "#FFF7E8" : "#FAF6EE",
      color:      accent ? "#E2A33C" : "#6B6357",
      border:     `1px solid ${accent ? "#F5DFA0" : "#E7DECF"}`,
      fontFamily: "IBM Plex Sans, sans-serif",
    }}>
      {label}
    </span>
  );
}

function LowConfidenceBadge() {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold" style={{
      background: "#FFF3E0", color: "#B45309", border: "1px solid #FBBF24",
    }}>
      ⚠ Baixa confiança
    </span>
  );
}

function ConfidenceDot({ score }: { score: number }) {
  const pct   = Math.round(score * 100);
  const color = pct >= 90 ? "#2F8F4E" : pct >= 70 ? "#E2A33C" : "#C2503A";
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
      style={{ background: `${color}18`, color }}>
      <span className="inline-block rounded-full" style={{ width: 6, height: 6, background: color }} />
      {pct}%
    </span>
  );
}

function KbdHint({ label }: { label: string }) {
  return (
    <kbd style={{
      display: "inline-flex", alignItems: "center", padding: "1px 4px",
      borderRadius: 4, fontSize: 9, fontWeight: 700, lineHeight: 1.6,
      background: "rgba(0,0,0,0.07)", border: "1px solid rgba(0,0,0,0.14)",
      color: "inherit", fontFamily: "IBM Plex Mono, monospace", letterSpacing: "0.01em",
    }}>
      {label}
    </kbd>
  );
}

function DiscrepancyBadge({ species }: { species: string[] }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold" style={{
      background: "#FEF2EF", color: "#C2503A", border: "1px solid #F5C7BB",
    }}>
      ⚠ Discrepância: {species.join(" × ")}
    </span>
  );
}

function FrameCarousel({ appearanceId }: { appearanceId: string }) {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;
  const [annotations, setAnnotations] = useState<FrameAnnotation[]>([]);
  const [loading, setLoading]         = useState(true);
  const [activeIdx, setActiveIdx]     = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/appearances/${appearanceId}/frame-annotations`, { headers: apiHeaders(idToken) })
      .then((r) => r.json())
      .then((d) => { if (!cancelled) { setAnnotations(d.items ?? []); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [appearanceId]);

  if (loading) return (
    <div className="flex items-center justify-center py-6" style={{ color: "#9A9080" }}>
      <Loader2 size={14} className="animate-spin" />
    </div>
  );
  if (annotations.length === 0) return null;

  // Assign a color per unique species
  const speciesColors: Record<string, string> = {};
  const palette = ["#2F6B4F", "#C2503A", "#E2A33C", "#2563EB", "#7C3AED"];
  const uniqueSpecies = Array.from(new Set(annotations.map((a) => a.annotated_species)));
  uniqueSpecies.forEach((sp, i) => { speciesColors[sp] = palette[i % palette.length]; });

  const active = annotations[activeIdx];

  return (
    <div className="flex flex-col gap-2">
      {/* Main frame image */}
      {active?.thumbnail_url && (
        <div className="relative overflow-hidden rounded-xl" style={{ height: 160, background: "#EFE8DB" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={active.thumbnail_url}
            alt={`Frame ${active.frame_idx}`}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
          />
          <div style={{
            position: "absolute", bottom: 6, left: 6, right: 6,
            display: "flex", justifyContent: "space-between", alignItems: "flex-end",
          }}>
            <span style={{
              padding: "2px 7px", borderRadius: 6, fontSize: 11, fontWeight: 600,
              background: "rgba(34,31,26,0.72)", color: "#fff",
              fontFamily: "IBM Plex Mono, monospace", backdropFilter: "blur(4px)",
            }}>
              frame {active.frame_idx}
            </span>
            <span style={{
              padding: "2px 7px", borderRadius: 6, fontSize: 11, fontWeight: 700,
              background: speciesColors[active.annotated_species] ?? "#2F6B4F",
              color: "#fff", backdropFilter: "blur(4px)",
              fontFamily: "IBM Plex Sans, sans-serif",
            }}>
              {active.annotated_species}
            </span>
          </div>
        </div>
      )}

      {/* Thumbnail strip */}
      <div className="flex gap-1.5 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
        {annotations.map((ann, i) => {
          const color = speciesColors[ann.annotated_species] ?? "#2F6B4F";
          const isActive = i === activeIdx;
          return (
            <button
              key={ann.frame_idx}
              onClick={() => setActiveIdx(i)}
              style={{
                flexShrink: 0, width: 52, height: 40, borderRadius: 7,
                overflow: "hidden", position: "relative",
                border: isActive ? `2.5px solid ${color}` : "2px solid transparent",
                outline: "none", cursor: "pointer", padding: 0,
                background: "#EFE8DB",
              }}
            >
              {ann.thumbnail_url
                ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={ann.thumbnail_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                )
                : (
                  <span style={{ fontSize: 9, color: "#9A9080", fontFamily: "IBM Plex Mono, monospace" }}>
                    {ann.frame_idx}
                  </span>
                )
              }
              {/* Species colour dot */}
              <span style={{
                position: "absolute", bottom: 2, right: 2,
                width: 6, height: 6, borderRadius: "50%", background: color,
                border: "1px solid rgba(255,255,255,0.7)",
              }} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── DiscrepancyResolver ────────────────────────────────────────────────────────

function DiscrepancyResolver({
  species, onResolve, loading,
}: {
  species: string[];
  onResolve: (sp: string) => void;
  loading: boolean;
}) {
  const [selected, setSelected] = useState(species[0] ?? "");
  return (
    <div className="flex items-center gap-2 p-3 rounded-xl"
      style={{ background: "#FEF9F0", border: "1.5px solid #F5DFA0" }}>
      <span className="text-xs font-semibold flex-shrink-0" style={{ color: "#B45309" }}>
        Resolver discrepância:
      </span>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        style={{
          flex: 1, padding: "4px 8px", borderRadius: 7, fontSize: 12,
          border: "1.5px solid #F5DFA0", background: "#fff",
          fontFamily: "IBM Plex Sans, sans-serif", color: "#221F1A",
        }}
      >
        {species.map((sp) => (
          <option key={sp} value={sp}>{sp}</option>
        ))}
      </select>
      <button
        onClick={() => onResolve(selected)}
        disabled={loading || !selected}
        style={{
          padding: "4px 12px", borderRadius: 7, fontSize: 12, fontWeight: 600,
          background: "#E2A33C", color: "#3A2A0E", border: "none", cursor: "pointer",
          fontFamily: "IBM Plex Sans, sans-serif",
        }}
      >
        Confirmar
      </button>
    </div>
  );
}

// ── ThumbnailWithBbox ─────────────────────────────────────────────────────────

function ThumbnailWithBbox({
  url, bbox, timeLabel,
}: {
  url: string;
  bbox: [number, number, number, number] | null;
  timeLabel: string;
}) {
  const imgRef       = useRef<HTMLImageElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const draw = useCallback(() => {
    const canvas    = canvasRef.current;
    const img       = imgRef.current;
    const container = containerRef.current;
    if (!canvas || !img || !container || !bbox) return;

    const cW = container.clientWidth;
    const cH = container.clientHeight;
    canvas.width  = cW;
    canvas.height = cH;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, cW, cH);

    const natW = img.naturalWidth;
    const natH = img.naturalHeight;
    if (!natW || !natH) return;

    // object-fit: contain — escala para caber sem cortar
    const scale   = Math.min(cW / natW, cH / natH);
    const dispW   = natW * scale;
    const dispH   = natH * scale;
    const offsetX = (cW - dispW) / 2;
    const offsetY = (cH - dispH) / 2;

    // MegaDetector bbox: [x_min, y_min, width, height] normalizado 0-1
    const [bx, by, bw, bh] = bbox;
    const sx = bx * natW * scale + offsetX;
    const sy = by * natH * scale + offsetY;
    const sw = bw * natW * scale;
    const sh = bh * natH * scale;

    ctx.strokeStyle = "#34C759";
    ctx.lineWidth   = 2;
    ctx.strokeRect(sx, sy, sw, sh);
    ctx.fillStyle   = "#34C75918";
    ctx.fillRect(sx, sy, sw, sh);
  }, [bbox]);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    if (img.complete && img.naturalWidth) draw();
    else img.onload = draw;
  }, [draw]);

  // Redesenha em resize (container pode mudar de largura)
  useEffect(() => {
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [draw]);

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", height: 140, background: "#1A1814", borderRadius: 12, overflow: "hidden" }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={imgRef}
        src={url}
        alt=""
        onLoad={draw}
        style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
      />
      {bbox && (
        <canvas
          ref={canvasRef}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        />
      )}
      {timeLabel !== "—" && (
        <span style={{
          position: "absolute", bottom: 6, left: 6,
          padding: "2px 7px", borderRadius: 6,
          fontSize: 11, fontWeight: 600, letterSpacing: "0.01em",
          background: "rgba(34,31,26,0.72)", color: "#fff",
          fontFamily: "IBM Plex Mono, monospace", backdropFilter: "blur(4px)",
        }}>
          {timeLabel}
        </span>
      )}
    </div>
  );
}


// ── AppearanceFrames ──────────────────────────────────────────────────────────

interface FrameItem {
  frame_idx: number;
  url:       string | null;
  is_best:   boolean;
  bbox:      [number, number, number, number] | null;
}

function AppearanceFrames({
  appearanceId,
  projectId,
  fallbackUrl,
  fallbackBbox,
  timeLabel,
}: {
  appearanceId: string;
  projectId:    string;
  fallbackUrl:  string | null;
  fallbackBbox: [number, number, number, number] | null;
  timeLabel:    string;
}) {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;
  const [frames,    setFrames]    = useState<FrameItem[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(
      `${API_BASE}/projects/${projectId}/appearances/${appearanceId}/frames`,
      { headers: apiHeaders(idToken) },
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled) return;
        const fs: FrameItem[] = d?.frames ?? [];
        setFrames(fs);
        const bestIdx = fs.findIndex((f) => f.is_best);
        setActiveIdx(bestIdx >= 0 ? bestIdx : 0);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [appearanceId, projectId, idToken]);

  if (loading) return (
    <div
      className="flex items-center justify-center"
      style={{ height: 140, background: "#1A1814", borderRadius: 12, color: "#9A9080" }}
    >
      <Loader2 size={14} className="animate-spin" />
    </div>
  );

  if (frames.length === 0) {
    return fallbackUrl
      ? <ThumbnailWithBbox url={fallbackUrl} bbox={fallbackBbox} timeLabel={timeLabel} />
      : null;
  }

  const active = frames[activeIdx];

  return (
    <div className="flex flex-col gap-2">
      <div style={{ position: "relative" }}>
        {active?.url ? (
          <ThumbnailWithBbox url={active.url} bbox={active.bbox ?? null} timeLabel={timeLabel} />
        ) : (
          <div style={{ height: 140, background: "#1A1814", borderRadius: 12 }} />
        )}
        <span style={{
          position: "absolute", top: 6, right: 6,
          padding: "2px 7px", borderRadius: 6, fontSize: 11,
          background: "rgba(34,31,26,0.72)", color: "#9A9080",
          fontFamily: "IBM Plex Mono, monospace", backdropFilter: "blur(4px)",
        }}>
          {activeIdx + 1} / {frames.length}
        </span>
        {frames.length > 1 && (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); setActiveIdx((i) => Math.max(0, i - 1)); }}
              disabled={activeIdx === 0}
              style={{
                position: "absolute", left: 4, top: "50%", transform: "translateY(-50%)",
                width: 28, height: 28, borderRadius: 6, border: "none",
                background: "rgba(34,31,26,0.64)", color: "#fff", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                opacity: activeIdx === 0 ? 0.3 : 0.8, backdropFilter: "blur(4px)",
                fontSize: 18, lineHeight: "1",
              }}
            >
              ‹
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setActiveIdx((i) => Math.min(frames.length - 1, i + 1)); }}
              disabled={activeIdx === frames.length - 1}
              style={{
                position: "absolute", right: 4, top: "50%", transform: "translateY(-50%)",
                width: 28, height: 28, borderRadius: 6, border: "none",
                background: "rgba(34,31,26,0.64)", color: "#fff", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                opacity: activeIdx === frames.length - 1 ? 0.3 : 0.8, backdropFilter: "blur(4px)",
                fontSize: 18, lineHeight: "1",
              }}
            >
              ›
            </button>
          </>
        )}
      </div>

      {frames.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
          {frames.slice(0, 12).map((f, i) => (
            <button
              key={f.frame_idx}
              onClick={(e) => { e.stopPropagation(); setActiveIdx(i); }}
              style={{
                flexShrink: 0, width: 52, height: 40, borderRadius: 7,
                overflow: "hidden", position: "relative",
                border: i === activeIdx ? "2.5px solid #2F6B4F" : "2px solid transparent",
                outline: "none", cursor: "pointer", padding: 0,
                background: "#EFE8DB",
              }}
            >
              {f.url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={f.url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <span style={{ fontSize: 9, color: "#9A9080", fontFamily: "IBM Plex Mono, monospace" }}>
                  {f.frame_idx}
                </span>
              )}
              {f.is_best && (
                <span style={{
                  position: "absolute", bottom: 2, right: 2,
                  width: 6, height: 6, borderRadius: "50%", background: "#2F6B4F",
                  border: "1px solid rgba(255,255,255,0.7)",
                }} />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AppearanceCard ─────────────────────────────────────────────────────────────

interface CardProps {
  app:            Appearance;
  focused:        boolean;
  correcting:     boolean;
  onAction:       (id: string, action: "confirm" | "reject" | "correct", species?: string) => Promise<void>;
  onSkip:         () => void;
  onConfirmVideo: () => void;
  onOpenCorrect:  () => void;
  onCloseCorrect: () => void;
  onFocus:        () => void;
  cardRef:        (el: HTMLDivElement | null) => void;
}

function AppearanceCard({
  app, focused, correcting,
  onAction, onSkip, onConfirmVideo, onOpenCorrect, onCloseCorrect, onFocus, cardRef,
}: CardProps) {
  const [actionState, setActionState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [correction,  setCorrection]  = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const corrInputRef = useRef<HTMLInputElement>(null);

  // Open correction input when parent signals it
  useEffect(() => {
    if (correcting) {
      setCorrection("");
      // Defer focus to after render
      requestAnimationFrame(() => corrInputRef.current?.focus());
    }
  }, [correcting]);

  const submit = async (action: "confirm" | "reject" | "correct", species?: string) => {
    setActionState("loading");
    setActionError(null);
    try {
      await onAction(app.appearance_id, action, species);
      setActionState("done");
    } catch (e) {
      setActionState("error");
      setActionError(String(e));
    }
  };

  const { date, time } = formatTs(app.ts_start);
  const low = isLowConfidence(app);

  if (actionState === "done") return null;

  return (
    <div
      ref={cardRef}
      onClick={onFocus}
      className="flex flex-col gap-3 p-4 rounded-2xl bg-white"
      style={{
        border:     `1.5px solid ${focused ? "#2F6B4F" : "#E7DECF"}`,
        boxShadow:  focused
          ? "0 0 0 3px #2F6B4F22, 0 2px 8px rgba(34,31,26,.06)"
          : "0 1px 2px rgba(34,31,26,.04)",
        opacity:    actionState === "loading" ? 0.6 : 1,
        transition: "border-color 0.12s, box-shadow 0.12s, opacity 0.2s",
        fontFamily: "IBM Plex Sans, sans-serif",
        scrollMarginTop: 80,
        cursor:     "default",
      }}
    >
      {/* Species + badges */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold italic" style={{ color: "#221F1A" }}>
              {app.species}
            </p>
            {low && <LowConfidenceBadge />}
            {app.review_status === "flagged_discrepancy" && app.discrepant_species && (
              <DiscrepancyBadge species={app.discrepant_species} />
            )}
          </div>
          {app.taxonomic_path && (
            <p className="text-xs truncate" style={{ color: "#9A9080" }}>
              {app.taxonomic_path.split(";").join(" › ")}
            </p>
          )}
        </div>
        <ConfidenceDot score={app.species_score} />
      </div>

      {/* Frame evidence: carousel for discrepant, frame strip otherwise */}
      {app.review_status === "flagged_discrepancy" ? (
        <FrameCarousel appearanceId={app.appearance_id} />
      ) : (
        <AppearanceFrames
          appearanceId={app.appearance_id}
          projectId={PROJECT_ID}
          fallbackUrl={app.thumbnail_url}
          fallbackBbox={app.bbox ?? null}
          timeLabel={time}
        />
      )}

      {/* Discrepancy resolution — species picker */}
      {app.review_status === "flagged_discrepancy" && app.discrepant_species && !correcting && (
        <DiscrepancyResolver
          species={app.discrepant_species}
          onResolve={(sp) => submit("correct", sp)}
          loading={actionState === "loading"}
        />
      )}

      {/* Meta chips */}
      <div className="flex flex-wrap gap-2">
        {app.camera_id && <Chip label={`Câmera ${app.camera_id}`} />}
        <Chip label={date} />
        {time !== "—" && <Chip label={time} />}
        <Chip label={`${app.support_frames} frame${app.support_frames !== 1 ? "s" : ""}`} />
        {app.individual_count > 1 && <Chip label={`${app.individual_count} indivíduos`} accent />}
      </div>

      {/* Correction input (controlled by parent via correcting prop) */}
      {correcting && (
        <div className="flex items-center gap-2 mt-1">
          <input
            ref={corrInputRef}
            type="text"
            placeholder="Nome científico correto…"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation(); // Prevent global shortcuts while typing
              if (e.key === "Enter" && correction.trim()) {
                submit("correct", correction.trim());
                onCloseCorrect();
              }
              if (e.key === "Escape") { onCloseCorrect(); }
            }}
            style={{
              flex: 1, padding: "6px 10px", borderRadius: 8, fontSize: 13,
              border: "1.5px solid #CDE3D6", fontStyle: "italic",
              fontFamily: "IBM Plex Sans, sans-serif", color: "#221F1A",
            }}
          />
          <button
            tabIndex={0}
            onClick={() => { if (correction.trim()) { submit("correct", correction.trim()); onCloseCorrect(); } }}
            disabled={!correction.trim() || actionState === "loading"}
            style={{
              padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: "#2F6B4F", color: "#fff", border: "none",
              cursor: correction.trim() ? "pointer" : "default",
              fontFamily: "IBM Plex Sans, sans-serif",
            }}
          >
            Salvar
          </button>
          <button
            tabIndex={0}
            onClick={onCloseCorrect}
            style={{ padding: 6, borderRadius: 8, background: "transparent", border: "none", cursor: "pointer", color: "#9A9080" }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {actionError && (
        <p className="text-xs" style={{ color: "#C2503A" }}>{actionError}</p>
      )}

      {/* Action buttons — Tab order: Confirmar(0) → Confirmar vídeo(0) → Pular(0) → Rejeitar(0) → Corrigir(0) */}
      {!correcting && actionState !== "loading" && (
        <div className="flex items-center gap-2 pt-1 flex-wrap">
          <button
            tabIndex={focused ? 0 : -1}
            onClick={(e) => { e.stopPropagation(); submit("confirm"); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: "#EEF5F0", color: "#2F8F4E", border: "1.5px solid #2F8F4E30", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif" }}
          >
            <CheckCircle2 size={13} />
            Confirmar
            {focused && <KbdHint label="↵" />}
          </button>

          <button
            tabIndex={focused ? 0 : -1}
            onClick={(e) => { e.stopPropagation(); onConfirmVideo(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: "#EFF6FF", color: "#2563EB", border: "1.5px solid #2563EB30", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif" }}
          >
            <Film size={13} />
            Confirmar vídeo
            {focused && <KbdHint label="⇧↵" />}
          </button>

          <button
            tabIndex={focused ? 0 : -1}
            onClick={(e) => { e.stopPropagation(); onSkip(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: "#FAF6EE", color: "#6B6357", border: "1.5px solid #C3BAA830", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif" }}
          >
            <SkipForward size={13} />
            Pular
            {focused && <KbdHint label="S" />}
          </button>

          <button
            tabIndex={focused ? 0 : -1}
            onClick={(e) => { e.stopPropagation(); submit("reject"); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: "#FEF2EF", color: "#C2503A", border: "1.5px solid #C2503A30", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif" }}
          >
            <XCircle size={13} />
            Rejeitar
            {focused && <KbdHint label="R" />}
          </button>

          <button
            tabIndex={focused ? 0 : -1}
            onClick={(e) => { e.stopPropagation(); onOpenCorrect(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity hover:opacity-80"
            style={{ background: "#FAF6EE", color: "#6B6357", border: "1.5px solid #6B635730", cursor: "pointer", fontFamily: "IBM Plex Sans, sans-serif" }}
          >
            <PencilLine size={13} />
            Corrigir
            {focused && <KbdHint label="C" />}
          </button>
        </div>
      )}

      {actionState === "loading" && (
        <div className="flex items-center gap-2 pt-1" style={{ color: "#9A9080" }}>
          <Loader2 size={13} className="animate-spin" />
          <span className="text-xs">Salvando…</span>
        </div>
      )}
    </div>
  );
}

// ── Shortcut bar ───────────────────────────────────────────────────────────────

function KbdBarHint({ label }: { label: string }) {
  return (
    <kbd style={{
      display: "inline-flex", alignItems: "center", padding: "1px 5px",
      borderRadius: 4, fontSize: 10, fontWeight: 600, lineHeight: 1.6,
      background: "rgba(255,255,255,0.15)", border: "1px solid rgba(255,255,255,0.25)",
      color: "inherit", fontFamily: "IBM Plex Mono, monospace",
    }}>
      {label}
    </kbd>
  );
}

function ShortcutBar() {
  const hints: { key: string; label: string }[] = [
    { key: "↵",   label: "confirmar" },
    { key: "⇧↵",  label: "vídeo inteiro" },
    { key: "S",   label: "pular" },
    { key: "R",   label: "rejeitar" },
    { key: "C",   label: "corrigir" },
    { key: "J/K", label: "navegar" },
  ];

  return (
    <div
      className="fixed bottom-0 left-0 right-0 flex items-center justify-center flex-wrap gap-x-5 gap-y-1 px-6 py-2"
      style={{
        background: "rgba(34,31,26,0.85)",
        backdropFilter: "blur(10px)",
        fontFamily: "IBM Plex Sans, sans-serif",
        zIndex: 50,
      }}
    >
      {hints.map(({ key, label }) => (
        <span key={key} className="flex items-center gap-1.5 text-xs" style={{ color: "rgba(255,255,255,0.65)" }}>
          <KbdBarHint label={key} />
          {label}
        </span>
      ))}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ReviewPage() {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;

  const [appearances,  setAppearances]  = useState<Appearance[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [focusedIdx,   setFocusedIdx]   = useState(0);
  const [correctingId, setCorrectingId] = useState<string | null>(null);

  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Scroll focused card into view whenever the index changes
  useEffect(() => {
    const app = appearances[focusedIdx];
    if (!app) return;
    cardRefs.current.get(app.appearance_id)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [focusedIdx, appearances]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingRes, discrepantRes] = await Promise.all([
        fetch(`${API_BASE}/projects/${PROJECT_ID}/appearances?review_status=pending`, { headers: apiHeaders(idToken) }),
        fetch(`${API_BASE}/projects/${PROJECT_ID}/appearances?review_status=flagged_discrepancy`, { headers: apiHeaders(idToken) }),
      ]);
      if (!pendingRes.ok) throw new Error(`HTTP ${pendingRes.status}`);
      const [pendingData, discrepantData] = await Promise.all([
        pendingRes.json(),
        discrepantRes.ok ? discrepantRes.json() : Promise.resolve({ items: [] }),
      ]);
      const combined = [
        ...(discrepantData.items ?? []),
        ...(pendingData.items ?? []),
      ];
      setAppearances(combined);
      setFocusedIdx(0);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Removes one appearance and adjusts focus to stay at same list position
  const removeOne = useCallback((id: string) => {
    setAppearances((prev) => {
      const next = prev.filter((a) => a.appearance_id !== id);
      setFocusedIdx((fi) => Math.min(fi, Math.max(0, next.length - 1)));
      return next;
    });
  }, []);

  const handleAction = useCallback(async (
    id: string,
    action: "confirm" | "reject" | "correct",
    species?: string,
  ) => {
    const res = await fetch(`${API_BASE}/appearances/${id}/review`, {
      method:  "PATCH",
      headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
      body:    JSON.stringify({ action, corrected_species: species }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}${text ? ": " + text : ""}`);
    }
    removeOne(id);
  }, [removeOne]);

  const handleSkip = useCallback(() => {
    setFocusedIdx((i) => Math.min(i + 1, appearances.length - 1));
  }, [appearances.length]);

  // Confirms all appearances that share the same video as the currently focused one
  const handleConfirmVideo = useCallback(async () => {
    const pivot = appearances[focusedIdx];
    if (!pivot) return;
    const key     = videoKey(pivot);
    const sameVid = appearances.filter((a) => videoKey(a) === key);
    for (const a of sameVid) {
      try { await handleAction(a.appearance_id, "confirm"); } catch { /* continue */ }
    }
  }, [appearances, focusedIdx, handleAction]);

  // Global keyboard shortcuts — disabled while correction input is open
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (correctingId !== null) return; // Correction input handles its own keys
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      const app = appearances[focusedIdx];
      if (!app) return;

      if (e.key === "Enter" && e.shiftKey) {
        e.preventDefault();
        handleConfirmVideo();
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleAction(app.appearance_id, "confirm");
      } else if (e.key === "s" || e.key === "S" || e.key === "ArrowRight") {
        e.preventDefault();
        handleSkip();
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        handleAction(app.appearance_id, "reject");
      } else if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        setCorrectingId(app.appearance_id);
      } else if (e.key === "j" || e.key === "J" || e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIdx((i) => Math.min(i + 1, appearances.length - 1));
      } else if (e.key === "k" || e.key === "K" || e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIdx((i) => Math.max(i - 1, 0));
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [appearances, focusedIdx, correctingId, handleAction, handleConfirmVideo, handleSkip]);

  const F = { fontFamily: "IBM Plex Sans, sans-serif" };

  return (
    <div className="min-h-screen pb-12" style={{ background: "#FAF6EE", ...F }}>
      <SiabNav />

      <main className="max-w-2xl mx-auto px-4 py-10 flex flex-col gap-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold font-title" style={{ color: "#221F1A" }}>
              Fila de Revisão
            </h1>
            <p className="text-sm mt-1" style={{ color: "#9A9080" }}>
              {PROJECT_ID} · aparições pendentes
            </p>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium"
            style={{ background: "#FAF6EE", border: "1.5px solid #E7DECF", color: "#6B6357", cursor: "pointer" }}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Atualizar
          </button>
        </div>

        {/* Count + position indicator */}
        {!loading && !error && appearances.length > 0 && (
          <p className="text-xs font-medium" style={{ color: "#9A9080" }}>
            {`${appearances.length} aparição${appearances.length !== 1 ? "s" : ""} aguardando revisão · revisando ${focusedIdx + 1} / ${appearances.length}`}
          </p>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center gap-2 py-12 justify-center" style={{ color: "#9A9080" }}>
            <Loader2 size={18} className="animate-spin" />
            <span className="text-sm">Carregando aparições…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl"
            style={{ background: "#FEF2EF", border: "1.5px solid #F5C7BB" }}>
            <AlertCircle size={16} style={{ color: "#C2503A", flexShrink: 0 }} />
            <div>
              <p className="text-sm font-medium" style={{ color: "#C2503A" }}>Erro ao carregar aparições</p>
              <p className="text-xs mt-0.5" style={{ color: "#C2503A" }}>{error}</p>
              <p className="text-xs mt-1" style={{ color: "#9A9080" }}>Verifique se a API está rodando em localhost:8000</p>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && appearances.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-16 rounded-2xl"
            style={{ background: "#fff", border: "1px solid #E7DECF" }}>
            <CheckCircle2 size={32} style={{ color: "#5FD08A" }} />
            <p className="text-sm font-medium" style={{ color: "#221F1A" }}>Fila vazia!</p>
            <p className="text-xs" style={{ color: "#9A9080" }}>Todas as aparições foram revisadas.</p>
          </div>
        )}

        {/* Card list */}
        {!loading && !error && appearances.length > 0 && (
          <div className="flex flex-col gap-3">
            {appearances.map((app, idx) => (
              <AppearanceCard
                key={app.appearance_id}
                app={app}
                focused={idx === focusedIdx}
                correcting={correctingId === app.appearance_id}
                onAction={handleAction}
                onSkip={handleSkip}
                onConfirmVideo={handleConfirmVideo}
                onOpenCorrect={() => setCorrectingId(app.appearance_id)}
                onCloseCorrect={() => setCorrectingId(null)}
                onFocus={() => setFocusedIdx(idx)}
                cardRef={(el) => {
                  if (el) cardRefs.current.set(app.appearance_id, el);
                  else cardRefs.current.delete(app.appearance_id);
                }}
              />
            ))}
          </div>
        )}
      </main>

      {!loading && !error && appearances.length > 0 && <ShortcutBar />}
    </div>
  );
}
