"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { API_BASE, apiHeaders } from "../../src/lib/api";
import { ListChecks, Check, X, Loader2, AlertCircle, ShieldAlert } from "lucide-react";

interface PendingSpecies {
  species_id:           string;
  name:                 string;
  status:                string;
  created_by:           string;
  created_by_tenant_id: string;
  created_at:           string;
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

export default function EspeciesPendentesPage() {
  const { data: session, status: sessionStatus } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const role = (session as any)?.role as string | undefined;
  const canApprove = role === "approver" || role === "admin";

  const [items,   setItems]   = useState<PendingSpecies[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [busyId,  setBusyId]  = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!idToken || !canApprove) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/species/pending`, { headers: apiHeaders(idToken) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setItems(d.species ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  }, [idToken, canApprove]);

  useEffect(() => { load(); }, [load]);

  const review = useCallback(async (speciesId: string, decision: "approve" | "reject", reason?: string) => {
    setBusyId(speciesId);
    try {
      const r = await fetch(`${API_BASE}/species/${speciesId}/review`, {
        method:  "PATCH",
        headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
        body:    JSON.stringify({ decision, reason }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setItems((prev) => prev.filter((it) => it.species_id !== speciesId));
    } catch (e) {
      alert(`Erro ao ${decision === "approve" ? "aprovar" : "rejeitar"}: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusyId(null);
    }
  }, [idToken]);

  const handleReject = useCallback((item: PendingSpecies) => {
    const reason = window.prompt(`Rejeitar "${item.name}" — motivo (opcional):`);
    if (reason === null) return; // cancelado
    review(item.species_id, "reject", reason.trim() || undefined);
  }, [review]);

  if (sessionStatus === "loading") {
    return (
      <div className="flex flex-col min-h-screen" style={{ background: "#F7F3EE" }}>
        <SiabNav />
        <div className="flex-1 flex items-center justify-center" style={{ color: "#9A9080" }}>
          <Loader2 size={20} className="animate-spin" />
        </div>
      </div>
    );
  }

  if (!canApprove) {
    return (
      <div className="flex flex-col min-h-screen" style={{ background: "#F7F3EE" }}>
        <SiabNav />
        <div className="flex-1 flex flex-col items-center justify-center gap-2"
          style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
          <ShieldAlert size={32} style={{ opacity: 0.4 }} />
          <p style={{ fontSize: 14 }}>Acesso restrito a approver/admin.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#F7F3EE" }}>
      <SiabNav />

      <main className="flex flex-col flex-1 px-6 py-6 gap-4" style={{ maxWidth: 960, width: "100%", margin: "0 auto" }}>

        <div className="flex items-center gap-3">
          <ListChecks size={18} style={{ color: "#2F6B4F" }} />
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif" }}>
            Espécies Pendentes
          </h1>
          <span style={{
            fontSize: 12, color: "#9A9080", fontFamily: "IBM Plex Mono, monospace",
            background: "#EFE8DB", padding: "2px 8px", borderRadius: 6,
          }}>
            catálogo global
          </span>
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

        {!loading && !error && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-2"
            style={{ color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
            <ListChecks size={32} style={{ opacity: 0.3 }} />
            <p style={{ fontSize: 14 }}>Nenhuma categoria aguardando aprovação.</p>
          </div>
        )}

        {!loading && items.length > 0 && (
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
                    {["Nome", "Proposto por", "Tenant de origem", "Criado em", "Ações"].map((h) => (
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
                  {items.map((it, idx) => (
                    <tr key={it.species_id}
                      style={{ borderBottom: idx < items.length - 1 ? "1px solid #F5F0EA" : "none" }}
                    >
                      <td style={{ padding: "10px 14px", color: "#221F1A", fontWeight: 500 }}>
                        {it.name}
                      </td>
                      <td style={{ padding: "10px 14px", color: "#6B6357" }}>
                        {it.created_by}
                      </td>
                      <td style={{ padding: "10px 14px", color: "#6B6357", whiteSpace: "nowrap" }}>
                        {it.created_by_tenant_id}
                      </td>
                      <td style={{ padding: "10px 14px", whiteSpace: "nowrap", color: "#6B6357",
                        fontFamily: "IBM Plex Mono, monospace", fontSize: 12 }}>
                        {formatDate(it.created_at)}
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => review(it.species_id, "approve")}
                            disabled={busyId === it.species_id}
                            title="Aprovar"
                            style={{
                              display: "flex", alignItems: "center", gap: 4,
                              padding: "5px 10px", borderRadius: 8,
                              border: "1px solid #C9E4D4", background: "#EEF5F0",
                              fontSize: 12, color: "#2F6B4F", cursor: "pointer",
                              opacity: busyId === it.species_id ? 0.6 : 1,
                            }}
                          >
                            {busyId === it.species_id
                              ? <Loader2 size={12} className="animate-spin" />
                              : <Check size={12} />}
                            Aprovar
                          </button>
                          <button
                            onClick={() => handleReject(it)}
                            disabled={busyId === it.species_id}
                            title="Rejeitar"
                            style={{
                              display: "flex", alignItems: "center", gap: 4,
                              padding: "5px 10px", borderRadius: 8,
                              border: "1px solid #EBDADA", background: "#fff",
                              fontSize: 12, color: "#C0392B", cursor: "pointer",
                              opacity: busyId === it.species_id ? 0.6 : 1,
                            }}
                          >
                            <X size={12} />
                            Rejeitar
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && items.length > 0 && (
          <div style={{ fontSize: 12, color: "#9A9080", fontFamily: "IBM Plex Sans, sans-serif" }}>
            {items.length} categoria{items.length !== 1 ? "s" : ""} aguardando decisão
          </div>
        )}

      </main>
    </div>
  );
}
