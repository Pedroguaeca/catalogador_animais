"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2, XCircle, PencilLine, Loader2, AlertCircle, RefreshCw, X,
} from "lucide-react";
import { SiabNav } from "../../src/components/SiabNav";

const PROJECT_ID = "projeto-junho-2026";
const API_BASE   = `/api/v1`;

interface Appearance {
  appearance_id:   string;
  species:         string;
  species_score:   number;
  camera_id:       string | null;
  ts_start:        string | null;
  support_frames:  number;
  individual_count: number;
  review_status:   string;
  best_crop_s3_key: string | null;
  taxonomic_path:  string | null;
}

type ActionState = "idle" | "loading" | "done" | "error";

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

function ConfidenceDot({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 90 ? "#2F8F4E" : pct >= 70 ? "#E2A33C" : "#C2503A";
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
      style={{ background: `${color}18`, color }}
    >
      <span
        className="inline-block rounded-full"
        style={{ width: 6, height: 6, background: color }}
      />
      {pct}%
    </span>
  );
}

function AppearanceCard({
  app,
  onAction,
}: {
  app: Appearance;
  onAction: (id: string, action: "confirm" | "reject" | "correct", species?: string) => Promise<void>;
}) {
  const [state,          setState]          = useState<ActionState>("idle");
  const [correcting,     setCorrecting]     = useState(false);
  const [correction,     setCorrection]     = useState("");
  const [actionError,    setActionError]    = useState<string | null>(null);

  const { date, time } = formatTs(app.ts_start);

  const submit = async (action: "confirm" | "reject" | "correct", species?: string) => {
    setState("loading");
    setActionError(null);
    try {
      await onAction(app.appearance_id, action, species);
      setState("done");
    } catch (e) {
      setState("error");
      setActionError(String(e));
    }
  };

  const F = { fontFamily: "IBM Plex Sans, sans-serif" };

  if (state === "done") return null; // Remove card após ação

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-2xl bg-white"
      style={{ border: "1px solid #E7DECF", ...F, opacity: state === "loading" ? 0.6 : 1, transition: "opacity 0.2s" }}
    >
      {/* Linha superior */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold italic" style={{ color: "#221F1A" }}>
            {app.species}
          </p>
          {app.taxonomic_path && (
            <p className="text-xs mt-0.5 truncate" style={{ color: "#9A9080" }}>
              {app.taxonomic_path.split(";").join(" › ")}
            </p>
          )}
        </div>
        <ConfidenceDot score={app.species_score} />
      </div>

      {/* Meta */}
      <div className="flex flex-wrap gap-2">
        {app.camera_id && (
          <Chip label={`Câmera ${app.camera_id}`} />
        )}
        <Chip label={date} />
        {time !== "—" && <Chip label={time} />}
        <Chip label={`${app.support_frames} frame${app.support_frames !== 1 ? "s" : ""}`} />
        {app.individual_count > 1 && (
          <Chip label={`${app.individual_count} indivíduos`} accent />
        )}
      </div>

      {/* Correção inline */}
      {correcting && (
        <div className="flex items-center gap-2 mt-1">
          <input
            type="text"
            placeholder="Nome científico correto…"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && correction.trim()) submit("correct", correction.trim());
              if (e.key === "Escape") { setCorrecting(false); setCorrection(""); }
            }}
            autoFocus
            style={{
              flex: 1, padding: "6px 10px", borderRadius: 8, fontSize: 13,
              border: "1.5px solid #CDE3D6", fontStyle: "italic",
              fontFamily: "IBM Plex Sans, sans-serif", color: "#221F1A",
            }}
          />
          <button
            onClick={() => correction.trim() && submit("correct", correction.trim())}
            disabled={!correction.trim() || state === "loading"}
            style={{
              padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: "#2F6B4F", color: "#fff", border: "none", cursor: "pointer",
              fontFamily: "IBM Plex Sans, sans-serif",
            }}
          >
            Salvar
          </button>
          <button
            onClick={() => { setCorrecting(false); setCorrection(""); }}
            style={{
              padding: 6, borderRadius: 8, background: "transparent", border: "none",
              cursor: "pointer", color: "#9A9080",
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Erro de ação */}
      {actionError && (
        <p className="text-xs" style={{ color: "#C2503A" }}>{actionError}</p>
      )}

      {/* Botões */}
      {!correcting && state !== "loading" && (
        <div className="flex items-center gap-2 pt-1">
          <ActionBtn
            icon={<CheckCircle2 size={13} />}
            label="Confirmar"
            color="#2F8F4E"
            bg="#EEF5F0"
            onClick={() => submit("confirm")}
          />
          <ActionBtn
            icon={<XCircle size={13} />}
            label="Rejeitar"
            color="#C2503A"
            bg="#FEF2EF"
            onClick={() => submit("reject")}
          />
          <ActionBtn
            icon={<PencilLine size={13} />}
            label="Corrigir"
            color="#6B6357"
            bg="#FAF6EE"
            onClick={() => setCorrecting(true)}
          />
        </div>
      )}

      {state === "loading" && (
        <div className="flex items-center gap-2 pt-1" style={{ color: "#9A9080" }}>
          <Loader2 size={13} className="animate-spin" />
          <span className="text-xs">Salvando…</span>
        </div>
      )}
    </div>
  );
}

function Chip({ label, accent = false }: { label: string; accent?: boolean }) {
  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs"
      style={{
        background: accent ? "#FFF7E8" : "#FAF6EE",
        color:      accent ? "#E2A33C" : "#6B6357",
        border:     `1px solid ${accent ? "#F5DFA0" : "#E7DECF"}`,
        fontFamily: "IBM Plex Sans, sans-serif",
      }}
    >
      {label}
    </span>
  );
}

function ActionBtn({
  icon, label, color, bg, onClick,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  bg: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity hover:opacity-75"
      style={{
        background: bg, color, border: `1.5px solid ${color}30`,
        fontFamily: "IBM Plex Sans, sans-serif", cursor: "pointer",
      }}
    >
      {icon}
      {label}
    </button>
  );
}

export default function ReviewPage() {
  const [appearances, setAppearances] = useState<Appearance[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res  = await fetch(`${API_BASE}/projects/${PROJECT_ID}/appearances?review_status=pending`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAppearances(data.items ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (
    id: string,
    action: "confirm" | "reject" | "correct",
    species?: string,
  ) => {
    const res = await fetch(`${API_BASE}/appearances/${id}/review`, {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ action, corrected_species: species }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}${text ? ": " + text : ""}`);
    }
    setAppearances((prev) => prev.filter((a) => a.appearance_id !== id));
  };

  const F = { fontFamily: "IBM Plex Sans, sans-serif" };

  return (
    <div className="min-h-screen" style={{ background: "#FAF6EE", ...F }}>
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
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity"
            style={{
              background: "#FAF6EE", border: "1.5px solid #E7DECF",
              color: "#6B6357", cursor: "pointer",
            }}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Atualizar
          </button>
        </div>

        {/* Contagem */}
        {!loading && !error && (
          <p className="text-xs font-medium" style={{ color: "#9A9080" }}>
            {appearances.length === 0
              ? "Nenhuma aparição pendente."
              : `${appearances.length} aparição${appearances.length !== 1 ? "s" : ""} aguardando revisão`}
          </p>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center gap-2 py-12 justify-center" style={{ color: "#9A9080" }}>
            <Loader2 size={18} className="animate-spin" />
            <span className="text-sm">Carregando aparições…</span>
          </div>
        )}

        {/* Erro */}
        {error && (
          <div
            className="flex items-center gap-3 p-4 rounded-xl"
            style={{ background: "#FEF2EF", border: "1.5px solid #F5C7BB" }}
          >
            <AlertCircle size={16} style={{ color: "#C2503A", flexShrink: 0 }} />
            <div>
              <p className="text-sm font-medium" style={{ color: "#C2503A" }}>
                Erro ao carregar aparições
              </p>
              <p className="text-xs mt-0.5" style={{ color: "#C2503A" }}>{error}</p>
              <p className="text-xs mt-1" style={{ color: "#9A9080" }}>
                Verifique se a API está rodando em localhost:8000
              </p>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && appearances.length === 0 && (
          <div
            className="flex flex-col items-center gap-3 py-16 rounded-2xl"
            style={{ background: "#fff", border: "1px solid #E7DECF" }}
          >
            <CheckCircle2 size={32} style={{ color: "#5FD08A" }} />
            <p className="text-sm font-medium" style={{ color: "#221F1A" }}>Fila vazia!</p>
            <p className="text-xs" style={{ color: "#9A9080" }}>
              Todas as aparições foram revisadas.
            </p>
          </div>
        )}

        {/* Lista */}
        {!loading && !error && appearances.length > 0 && (
          <div className="flex flex-col gap-3">
            {appearances.map((app) => (
              <AppearanceCard key={app.appearance_id} app={app} onAction={handleAction} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
