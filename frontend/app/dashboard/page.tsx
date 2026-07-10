"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { API_BASE } from "../../src/lib/api";
import { Camera, AlignJustify, Leaf, CalendarDays, Loader2 } from "lucide-react";
import type { StatsData } from "./DashboardCharts";

const PROJECT_ID = "projeto-junho-2026";

const DashboardCharts = dynamic<{ stats: StatsData | null }>(
  () => import("./DashboardCharts"),
  {
    ssr:     false,
    loading: () => (
      <div className="flex items-center justify-center gap-2 py-20" style={{ color: "#9A9080" }}>
        <Loader2 size={16} className="animate-spin" />
        <span className="text-sm" style={{ fontFamily: "IBM Plex Sans, sans-serif" }}>
          Carregando gráficos…
        </span>
      </div>
    ),
  }
);

// ── Shared styles ──────────────────────────────────────────────────────────────

const F = { fontFamily: "IBM Plex Sans, sans-serif" };

const CARD_STYLE = {
  background:   "#fff",
  border:       "1px solid #E7DECF",
  borderRadius: 16,
  padding:      24,
  boxShadow:    "0 1px 2px rgba(34,31,26,.04), 0 4px 16px rgba(34,31,26,.04)",
};

const GROUP_ORDER  = ["mastofauna", "avifauna", "herpetofauna", "outros"];
const GROUP_LABELS: Record<string, string> = {
  mastofauna:   "Mastofauna",
  avifauna:     "Avifauna",
  herpetofauna: "Herpetofauna",
  outros:       "Outros",
};
const GROUP_COLORS: Record<string, string> = {
  mastofauna:   "#2F6B4F",
  avifauna:     "#4A90D9",
  herpetofauna: "#E2A33C",
  outros:       "#9A9080",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
  } catch {
    return iso;
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-semibold mb-4" style={{ color: "#221F1A", ...F }}>
      {children}
    </h2>
  );
}

function SummaryCard({
  icon, label, value, sub,
}: {
  icon:  React.ReactNode;
  label: string;
  value: string | number;
  sub?:  string;
}) {
  return (
    <div style={{ ...CARD_STYLE, display: "flex", flexDirection: "column", gap: 8 }}>
      <div className="flex items-center gap-2" style={{ color: "#9A9080" }}>
        {icon}
        <span className="text-xs font-medium" style={F}>{label}</span>
      </div>
      <p className="text-2xl font-semibold" style={{ color: "#221F1A", ...F, lineHeight: 1 }}>
        {value}
      </p>
      {sub && <p className="text-xs" style={{ color: "#9A9080", ...F }}>{sub}</p>}
    </div>
  );
}

function SpeciesTable({ richness }: { richness: StatsData["species_richness"] }) {
  if (richness.length === 0) {
    return (
      <p className="text-sm text-center py-10" style={{ color: "#C3BAA8", ...F }}>
        Sem espécies confirmadas ainda
      </p>
    );
  }

  const grouped: Record<string, typeof richness> = {};
  for (const grp of GROUP_ORDER) {
    grouped[grp] = richness.filter((r) => r.group === grp).sort((a, b) => b.count - a.count);
  }
  const total = richness.reduce((s, r) => s + r.count, 0);

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", ...F, fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1.5px solid #E7DECF" }}>
            {["Grupo de Fauna", "Nome Científico", "Nº Registros"].map((h) => (
              <th
                key={h}
                className="text-left pb-2 pr-4"
                style={{ color: "#6B6357", fontWeight: 600, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {GROUP_ORDER.flatMap((grp) =>
            grouped[grp].map((row, ri) => (
              <tr
                key={row.species}
                style={{
                  borderBottom: "1px solid #F5F0E8",
                  background: ri === 0 ? `${GROUP_COLORS[grp]}08` : "transparent",
                }}
              >
                <td className="py-2.5 pr-4" style={{ color: GROUP_COLORS[grp], fontWeight: ri === 0 ? 600 : 400 }}>
                  {ri === 0 ? (GROUP_LABELS[grp] ?? grp) : ""}
                </td>
                <td className="py-2.5 pr-4" style={{ color: "#6B6357", fontStyle: "italic" }}>
                  {row.species}
                </td>
                <td className="py-2.5 pr-4 text-right font-semibold" style={{ color: "#221F1A" }}>
                  {row.count}
                </td>
              </tr>
            ))
          )}
          <tr style={{ borderTop: "2px solid #E7DECF", background: "#FAF6EE" }}>
            <td colSpan={2} className="py-2.5 pr-4 font-semibold text-xs"
              style={{ color: "#6B6357", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Total geral
            </td>
            <td className="py-2.5 pr-4 text-right font-bold" style={{ color: "#221F1A" }}>{total}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data: session } = useSession();
  const [stats,   setStats]   = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;

    const idToken = (session as unknown as Record<string, unknown>).idToken as string | undefined;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (idToken) headers["Authorization"] = `Bearer ${idToken}`;

    fetch(`${API_BASE}/projects/${PROJECT_ID}/stats`, { headers })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<StatsData>;
      })
      .then((data) => { setStats(data); setLoading(false); })
      .catch((err) => { setError(String(err)); setLoading(false); });
  }, [session]);

  // ── Derived values ───────────────────────────────────────────────────────────
  const totalRecords   = stats?.total_confirmed   ?? 0;
  const totalSpecies   = stats?.distinct_species  ?? 0;
  const totalCameras   = stats?.active_cameras    ?? 0;
  const activeGroups   = new Set(stats?.species_richness.map((r) => r.group) ?? []).size;

  const periodDisplay = stats
    ? stats.period_start
      ? `${formatDate(stats.period_start)} → ${formatDate(stats.period_end)}`
      : "Sem registros"
    : "—";

  return (
    <div className="min-h-screen" style={{ background: "#FAF6EE", ...F }}>
      <SiabNav />

      <main className="max-w-5xl mx-auto px-4 py-8 flex flex-col gap-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold font-title" style={{ color: "#221F1A" }}>
              Dashboard
            </h1>
            <p className="text-sm mt-1" style={{ color: "#9A9080" }}>
              {PROJECT_ID} · monitoramento de fauna
            </p>
          </div>

          {loading && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs"
              style={{ background: "#F5F0E8", color: "#9A9080", ...F }}>
              <Loader2 size={12} className="animate-spin" /> Carregando dados…
            </div>
          )}
          {error && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs"
              style={{ background: "#FEF2EF", border: "1px solid #F5C7BB", color: "#C2503A", ...F }}>
              Erro ao carregar: {error}
            </div>
          )}
        </div>

        {/* Summary cards */}
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          <SummaryCard
            icon={<AlignJustify size={14} />}
            label="Total de registros"
            value={totalRecords.toLocaleString("pt-BR")}
            sub="aparições confirmadas"
          />
          <SummaryCard
            icon={<Leaf size={14} />}
            label="Espécies distintas"
            value={totalSpecies}
            sub={activeGroups > 0 ? `${activeGroups} grupo${activeGroups !== 1 ? "s" : ""} de fauna` : "sem dados"}
          />
          <SummaryCard
            icon={<Camera size={14} />}
            label="Câmeras ativas"
            value={totalCameras}
            sub="pontos de monitoramento"
          />
          <SummaryCard
            icon={<CalendarDays size={14} />}
            label="Período"
            value={periodDisplay}
            sub={stats?.period_start ? undefined : "aguardando dados"}
          />
        </div>

        {/* Gráficos — carregados apenas no browser via dynamic import */}
        <DashboardCharts stats={stats} />

        {/* Species richness table */}
        <div style={CARD_STYLE}>
          <SectionTitle>Riqueza de Espécies</SectionTitle>
          <SpeciesTable richness={stats?.species_richness ?? []} />
        </div>
      </main>
    </div>
  );
}
