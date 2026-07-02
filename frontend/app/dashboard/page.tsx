"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell,
} from "recharts";
import { useState } from "react";
import { SiabNav } from "../../src/components/SiabNav";
import { Camera, AlignJustify, Leaf, CalendarDays } from "lucide-react";

// ── Mock data (estrutura real; valores ilustrativos) ───────────────────────────

const PERIODS = ["Jan/25", "Fev/25", "Mar/25", "Abr/25", "Mai/25", "Jun/25"] as const;

const FAUNA_BY_PERIOD = [
  { period: "Jan/25", Mastofauna: 42, Avifauna: 17, Herpetofauna:  8 },
  { period: "Fev/25", Mastofauna: 38, Avifauna: 22, Herpetofauna:  5 },
  { period: "Mar/25", Mastofauna: 55, Avifauna: 31, Herpetofauna: 12 },
  { period: "Abr/25", Mastofauna: 61, Avifauna: 28, Herpetofauna:  9 },
  { period: "Mai/25", Mastofauna: 49, Avifauna: 19, Herpetofauna:  7 },
  { period: "Jun/25", Mastofauna: 44, Avifauna: 25, Herpetofauna: 11 },
];

interface SpeciesRow {
  group:      string;
  popular:    string;
  scientific: string;
  count:      number;
}

const SPECIES_TABLE: SpeciesRow[] = [
  { group: "Mastofauna",   popular: "Cutia",           scientific: "Dasyprocta leporina",     count: 89 },
  { group: "Mastofauna",   popular: "Paca",             scientific: "Cuniculus paca",          count: 47 },
  { group: "Mastofauna",   popular: "Veado-mateiro",    scientific: "Mazama americana",        count: 32 },
  { group: "Mastofauna",   popular: "Tamanduá-mirim",   scientific: "Tamandua tetradactyla",   count: 18 },
  { group: "Mastofauna",   popular: "Onça-parda",       scientific: "Puma concolor",           count:  8 },
  { group: "Avifauna",     popular: "Jacamim",          scientific: "Psophia crepitans",       count: 41 },
  { group: "Avifauna",     popular: "Mutum-cavalo",     scientific: "Crax blumenbachii",       count: 28 },
  { group: "Avifauna",     popular: "Araçari-mulato",   scientific: "Pteroglossus aracari",    count: 17 },
  { group: "Avifauna",     popular: "Nambu-relógio",    scientific: "Crypturellus tataupa",    count:  9 },
  { group: "Herpetofauna", popular: "Jacaré-tinga",     scientific: "Caiman crocodilus",       count: 21 },
  { group: "Herpetofauna", popular: "Jabuti-piranga",   scientific: "Chelonoidis carbonaria",  count: 14 },
  { group: "Herpetofauna", popular: "Sucuri",           scientific: "Eunectes murinus",        count:  7 },
];

const CAMERAS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04"];

interface CameraRow {
  species: string;
  [cam: string]: number | string;
}

const CAMERA_BY_PERIOD: Record<string, CameraRow[]> = {
  "Todos": [
    { species: "D. leporina",    "CAM-01": 24, "CAM-02": 31, "CAM-03": 18, "CAM-04": 16 },
    { species: "C. paca",        "CAM-01": 12, "CAM-02":  8, "CAM-03": 14, "CAM-04": 13 },
    { species: "M. americana",   "CAM-01":  9, "CAM-02": 11, "CAM-03":  7, "CAM-04":  5 },
    { species: "P. crepitans",   "CAM-01": 15, "CAM-02": 10, "CAM-03":  6, "CAM-04": 10 },
    { species: "T. tetradactyla","CAM-01":  6, "CAM-02":  5, "CAM-03":  4, "CAM-04":  3 },
    { species: "P. concolor",    "CAM-01":  3, "CAM-02":  2, "CAM-03":  2, "CAM-04":  1 },
  ],
  "Jan/25": [
    { species: "D. leporina",    "CAM-01":  4, "CAM-02":  5, "CAM-03":  3, "CAM-04":  2 },
    { species: "C. paca",        "CAM-01":  2, "CAM-02":  1, "CAM-03":  2, "CAM-04":  2 },
    { species: "M. americana",   "CAM-01":  1, "CAM-02":  2, "CAM-03":  1, "CAM-04":  1 },
    { species: "P. crepitans",   "CAM-01":  2, "CAM-02":  2, "CAM-03":  1, "CAM-04":  1 },
    { species: "T. tetradactyla","CAM-01":  1, "CAM-02":  1, "CAM-03":  1, "CAM-04":  0 },
    { species: "P. concolor",    "CAM-01":  1, "CAM-02":  0, "CAM-03":  0, "CAM-04":  0 },
  ],
  "Fev/25": [
    { species: "D. leporina",    "CAM-01":  3, "CAM-02":  4, "CAM-03":  2, "CAM-04":  2 },
    { species: "C. paca",        "CAM-01":  1, "CAM-02":  2, "CAM-03":  3, "CAM-04":  1 },
    { species: "M. americana",   "CAM-01":  2, "CAM-02":  1, "CAM-03":  1, "CAM-04":  1 },
    { species: "P. crepitans",   "CAM-01":  3, "CAM-02":  1, "CAM-03":  1, "CAM-04":  2 },
    { species: "T. tetradactyla","CAM-01":  1, "CAM-02":  1, "CAM-03":  0, "CAM-04":  1 },
    { species: "P. concolor",    "CAM-01":  0, "CAM-02":  1, "CAM-03":  0, "CAM-04":  0 },
  ],
  "Mar/25": [
    { species: "D. leporina",    "CAM-01":  5, "CAM-02":  7, "CAM-03":  4, "CAM-04":  3 },
    { species: "C. paca",        "CAM-01":  3, "CAM-02":  2, "CAM-03":  3, "CAM-04":  3 },
    { species: "M. americana",   "CAM-01":  2, "CAM-02":  3, "CAM-03":  2, "CAM-04":  1 },
    { species: "P. crepitans",   "CAM-01":  4, "CAM-02":  3, "CAM-03":  2, "CAM-04":  3 },
    { species: "T. tetradactyla","CAM-01":  2, "CAM-02":  1, "CAM-03":  1, "CAM-04":  1 },
    { species: "P. concolor",    "CAM-01":  1, "CAM-02":  1, "CAM-03":  1, "CAM-04":  0 },
  ],
  "Abr/25": [
    { species: "D. leporina",    "CAM-01":  6, "CAM-02":  8, "CAM-03":  4, "CAM-04":  4 },
    { species: "C. paca",        "CAM-01":  3, "CAM-02":  2, "CAM-03":  3, "CAM-04":  4 },
    { species: "M. americana",   "CAM-01":  2, "CAM-02":  3, "CAM-03":  2, "CAM-04":  1 },
    { species: "P. crepitans",   "CAM-01":  3, "CAM-02":  2, "CAM-03":  1, "CAM-04":  2 },
    { species: "T. tetradactyla","CAM-01":  1, "CAM-02":  1, "CAM-03":  1, "CAM-04":  0 },
    { species: "P. concolor",    "CAM-01":  1, "CAM-02":  0, "CAM-03":  1, "CAM-04":  0 },
  ],
  "Mai/25": [
    { species: "D. leporina",    "CAM-01":  4, "CAM-02":  4, "CAM-03":  3, "CAM-04":  3 },
    { species: "C. paca",        "CAM-01":  2, "CAM-02":  1, "CAM-03":  2, "CAM-04":  2 },
    { species: "M. americana",   "CAM-01":  1, "CAM-02":  1, "CAM-03":  1, "CAM-04":  1 },
    { species: "P. crepitans",   "CAM-01":  2, "CAM-02":  1, "CAM-03":  1, "CAM-04":  2 },
    { species: "T. tetradactyla","CAM-01":  1, "CAM-02":  1, "CAM-03":  1, "CAM-04":  1 },
    { species: "P. concolor",    "CAM-01":  0, "CAM-02":  0, "CAM-03":  0, "CAM-04":  1 },
  ],
  "Jun/25": [
    { species: "D. leporina",    "CAM-01":  2, "CAM-02":  3, "CAM-03":  2, "CAM-04":  2 },
    { species: "C. paca",        "CAM-01":  1, "CAM-02":  0, "CAM-03":  1, "CAM-04":  1 },
    { species: "M. americana",   "CAM-01":  1, "CAM-02":  1, "CAM-03":  0, "CAM-04":  0 },
    { species: "P. crepitans",   "CAM-01":  1, "CAM-02":  1, "CAM-03":  0, "CAM-04":  0 },
    { species: "T. tetradactyla","CAM-01":  0, "CAM-02":  0, "CAM-03":  0, "CAM-04":  0 },
    { species: "P. concolor",    "CAM-01":  0, "CAM-02":  0, "CAM-03":  0, "CAM-04":  0 },
  ],
};

// ── Derived summary values ─────────────────────────────────────────────────────

const TOTAL_RECORDS  = SPECIES_TABLE.reduce((s, r) => s + r.count, 0);
const TOTAL_SPECIES  = SPECIES_TABLE.length;
const TOTAL_CAMERAS  = CAMERAS.length;
const PERIOD_RANGE   = `${PERIODS[0].replace("/", "/20")} → ${PERIODS[PERIODS.length - 1].replace("/", "/20")}`;

// ── Color tokens ───────────────────────────────────────────────────────────────

const GROUP_COLORS: Record<string, string> = {
  Mastofauna:   "#2F6B4F",
  Avifauna:     "#4A90D9",
  Herpetofauna: "#E2A33C",
};

const CAMERA_COLORS: Record<string, string> = {
  "CAM-01": "#2F8F4E",
  "CAM-02": "#4A90D9",
  "CAM-03": "#9B59B6",
  "CAM-04": "#E2A33C",
};

const GROUP_ORDER = ["Mastofauna", "Avifauna", "Herpetofauna"];

// ── Shared styles ──────────────────────────────────────────────────────────────

const F          = { fontFamily: "IBM Plex Sans, sans-serif" };
const CARD_STYLE = {
  background: "#fff",
  border:     "1px solid #E7DECF",
  borderRadius: 16,
  padding:    24,
  boxShadow:  "0 1px 2px rgba(34,31,26,.04), 0 4px 16px rgba(34,31,26,.04)",
};

const AXIS_STYLE = {
  fontSize: 11,
  fontFamily: "IBM Plex Sans, sans-serif",
  fill: "#9A9080",
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-semibold mb-4" style={{ color: "#221F1A", ...F }}>
      {children}
    </h2>
  );
}

function MockBanner() {
  return (
    <div
      className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs"
      style={{ background: "#FFF7E8", border: "1px solid #F5DFA0", color: "#B45309", ...F }}
    >
      ⚠ Dados de demonstração — backend de analytics em desenvolvimento
    </div>
  );
}

function SummaryCard({
  icon, label, value, sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div style={{ ...CARD_STYLE, display: "flex", flexDirection: "column", gap: 8 }}>
      <div className="flex items-center gap-2" style={{ color: "#9A9080" }}>
        {icon}
        <span className="text-xs font-medium" style={{ ...F }}>{label}</span>
      </div>
      <p className="text-2xl font-semibold" style={{ color: "#221F1A", ...F, lineHeight: 1 }}>
        {value}
      </p>
      {sub && <p className="text-xs" style={{ color: "#9A9080", ...F }}>{sub}</p>}
    </div>
  );
}

// Custom tooltip for recharts
function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + p.value, 0);
  return (
    <div style={{
      background: "#fff", border: "1px solid #E7DECF", borderRadius: 10,
      padding: "10px 14px", boxShadow: "0 4px 16px rgba(34,31,26,.10)", ...F,
    }}>
      <p className="text-xs font-semibold mb-2" style={{ color: "#6B6357" }}>{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-6 text-xs mb-1">
          <span className="flex items-center gap-1.5" style={{ color: "#6B6357" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.color, display: "inline-block" }} />
            {p.name}
          </span>
          <span className="font-semibold" style={{ color: "#221F1A" }}>{p.value}</span>
        </div>
      ))}
      {payload.length > 1 && (
        <div className="flex justify-between text-xs mt-2 pt-2" style={{ borderTop: "1px solid #E7DECF" }}>
          <span style={{ color: "#6B6357" }}>Total</span>
          <span className="font-bold" style={{ color: "#221F1A" }}>{total}</span>
        </div>
      )}
    </div>
  );
}

// ── Species Richness Table ─────────────────────────────────────────────────────

function SpeciesTable() {
  const grouped = GROUP_ORDER.reduce<Record<string, SpeciesRow[]>>((acc, g) => {
    acc[g] = SPECIES_TABLE.filter((r) => r.group === g)
                          .sort((a, b) => b.count - a.count);
    return acc;
  }, {});

  const total = TOTAL_RECORDS;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", ...F, fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1.5px solid #E7DECF" }}>
            {["Grupo de Fauna", "Nome Popular", "Nome Científico", "Nº Registros"].map((h) => (
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
          {GROUP_ORDER.map((group) =>
            grouped[group].map((row, ri) => (
              <tr
                key={row.scientific}
                style={{
                  borderBottom: "1px solid #F5F0E8",
                  background: ri === 0 ? `${GROUP_COLORS[group]}08` : "transparent",
                }}
              >
                <td className="py-2.5 pr-4" style={{ color: GROUP_COLORS[group], fontWeight: ri === 0 ? 600 : 400 }}>
                  {ri === 0 ? group : ""}
                </td>
                <td className="py-2.5 pr-4" style={{ color: "#221F1A" }}>{row.popular}</td>
                <td className="py-2.5 pr-4" style={{ color: "#6B6357", fontStyle: "italic" }}>{row.scientific}</td>
                <td className="py-2.5 pr-4 text-right font-semibold" style={{ color: "#221F1A" }}>{row.count}</td>
              </tr>
            ))
          )}
          <tr style={{ borderTop: "2px solid #E7DECF", background: "#FAF6EE" }}>
            <td colSpan={3} className="py-2.5 pr-4 font-semibold text-xs" style={{ color: "#6B6357", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Total geral
            </td>
            <td className="py-2.5 pr-4 text-right font-bold" style={{ color: "#221F1A" }}>{total}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ── Camera Chart with period filter ───────────────────────────────────────────

function CameraChart() {
  const [period, setPeriod] = useState<string>("Todos");
  const data = CAMERA_BY_PERIOD[period] ?? CAMERA_BY_PERIOD["Todos"];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <SectionTitle>Registros por Câmera</SectionTitle>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          style={{
            padding: "5px 10px", borderRadius: 8, fontSize: 12,
            border: "1.5px solid #E7DECF", background: "#FAF6EE",
            color: "#221F1A", ...F, cursor: "pointer",
          }}
        >
          <option value="Todos">Todos os períodos</option>
          {PERIODS.map((p) => <option key={p} value={p}>{p.replace("/", "/20")}</option>)}
        </select>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} barCategoryGap="30%" barGap={2} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F0EAE0" vertical={false} />
          <XAxis dataKey="species" tick={AXIS_STYLE} axisLine={false} tickLine={false} />
          <YAxis tick={AXIS_STYLE} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(v) => <span style={{ ...F, fontSize: 12, color: "#6B6357" }}>{v}</span>}
          />
          {CAMERAS.map((cam) => (
            <Bar key={cam} dataKey={cam} name={cam} fill={CAMERA_COLORS[cam]} radius={[3, 3, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>

      {/* Camera legend */}
      <div className="flex flex-wrap gap-3 mt-3">
        {CAMERAS.map((cam) => (
          <span key={cam} className="flex items-center gap-1.5 text-xs" style={{ color: "#6B6357", ...F }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: CAMERA_COLORS[cam], display: "inline-block" }} />
            {cam}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
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
              projeto-junho-2026 · monitoramento de fauna
            </p>
          </div>
          <MockBanner />
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-4" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          <SummaryCard
            icon={<AlignJustify size={14} />}
            label="Total de registros"
            value={TOTAL_RECORDS.toLocaleString("pt-BR")}
            sub="aparições confirmadas"
          />
          <SummaryCard
            icon={<Leaf size={14} />}
            label="Espécies distintas"
            value={TOTAL_SPECIES}
            sub={`${GROUP_ORDER.length} grupos de fauna`}
          />
          <SummaryCard
            icon={<Camera size={14} />}
            label="Câmeras ativas"
            value={TOTAL_CAMERAS}
            sub="pontos de monitoramento"
          />
          <SummaryCard
            icon={<CalendarDays size={14} />}
            label="Período"
            value={PERIOD_RANGE}
            sub={`${PERIODS.length} meses`}
          />
        </div>

        {/* Stacked bar: fauna group by period */}
        <div style={CARD_STYLE}>
          <SectionTitle>Registros por Grupo de Fauna</SectionTitle>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={FAUNA_BY_PERIOD}
              barCategoryGap="35%"
              margin={{ top: 4, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#F0EAE0" vertical={false} />
              <XAxis dataKey="period" tick={AXIS_STYLE} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS_STYLE} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
              <Legend
                iconType="circle"
                iconSize={8}
                formatter={(v) => <span style={{ ...F, fontSize: 12, color: "#6B6357" }}>{v}</span>}
              />
              {GROUP_ORDER.map((group) => (
                <Bar
                  key={group}
                  dataKey={group}
                  name={group}
                  stackId="fauna"
                  fill={GROUP_COLORS[group]}
                  radius={group === "Herpetofauna" ? [3, 3, 0, 0] : [0, 0, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Camera chart */}
        <div style={CARD_STYLE}>
          <CameraChart />
        </div>

        {/* Species richness table */}
        <div style={CARD_STYLE}>
          <SectionTitle>Riqueza de Espécies</SectionTitle>
          <SpeciesTable />
        </div>
      </main>
    </div>
  );
}
