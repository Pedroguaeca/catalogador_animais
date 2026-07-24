"use client";

// Carregado apenas no browser (dynamic + ssr:false).
// Recharts acessa ResizeObserver/document ao importar.

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell,
  PieChart, Pie,
} from "recharts";
import { InfoTooltip } from "../../src/components/InfoTooltip";

export interface FaunaMonthRow {
  month:        string;
  mastofauna:   number;
  avifauna:     number;
  herpetofauna: number;
}

export interface CameraRow {
  camera_id:   string;
  total:       number;
  top_species: string[];
}

export interface SpeciesRichnessRow {
  species:           string;
  group:             string;
  taxonomic_level:   string;
  count:             number;
  individual_count:  number;
}

export interface StatsData {
  total_confirmed:          number;
  distinct_species:         number;
  unidentified_count:       number;
  total_individuals:        number;
  active_cameras:           number;
  period_start:             string | null;
  period_end:               string | null;
  by_fauna_group_and_month: FaunaMonthRow[];
  by_camera:                CameraRow[];
  species_richness:         SpeciesRichnessRow[];
}

const PT_MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];

function formatMonth(ym: string): string {
  // Bucket "Data desconhecida" (vídeo sem captured_at, ver /stats) não é
  // "YYYY-MM" — passa direto, sem tentar formatar como mês.
  if (!/^\d{4}-\d{2}$/.test(ym)) return ym;
  const [year, month] = ym.split("-");
  const m = parseInt(month, 10) - 1;
  return `${PT_MONTHS[m] ?? month}/${(year ?? "").slice(2)}`;
}

const GROUP_COLORS: Record<string, string> = {
  mastofauna:   "#2F6B4F",
  avifauna:     "#4A90D9",
  herpetofauna: "#E2A33C",
};

const GROUP_LABELS: Record<string, string> = {
  mastofauna:   "Mastofauna",
  avifauna:     "Avifauna",
  herpetofauna: "Herpetofauna",
};

const CAMERA_PALETTE = ["#2F8F4E", "#4A90D9", "#9B59B6", "#E2A33C", "#C2503A", "#1A8A8A"];

const F = { fontFamily: "IBM Plex Sans, sans-serif" };

const AXIS_STYLE = {
  fontSize:   11,
  fontFamily: "IBM Plex Sans, sans-serif",
  fill:       "#9A9080",
};

const CARD_STYLE = {
  background:  "#fff",
  border:      "1px solid #E7DECF",
  borderRadius: 16,
  padding:     24,
  boxShadow:   "0 1px 2px rgba(34,31,26,.04), 0 4px 16px rgba(34,31,26,.04)",
};

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-semibold mb-4" style={{ color: "#221F1A", ...F }}>
      {children}
    </h2>
  );
}

function ChartTooltip({ active, payload, label }: {
  active?:  boolean;
  payload?: { name: string; value: number; color: string }[];
  label?:   string;
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

function CameraTooltip({ active, payload, label }: {
  active?:  boolean;
  payload?: { value: number; payload: CameraRow }[];
  label?:   string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div style={{
      background: "#fff", border: "1px solid #E7DECF", borderRadius: 10,
      padding: "10px 14px", boxShadow: "0 4px 16px rgba(34,31,26,.10)", ...F, minWidth: 160,
    }}>
      <p className="text-xs font-semibold mb-2" style={{ color: "#6B6357" }}>{label}</p>
      <div className="flex justify-between text-xs mb-2">
        <span style={{ color: "#6B6357" }}>Total</span>
        <span className="font-bold" style={{ color: "#221F1A" }}>{row.total}</span>
      </div>
      {row.top_species.length > 0 && (
        <div className="text-xs" style={{ color: "#6B6357" }}>
          <p className="font-medium mb-1">Top espécies</p>
          {row.top_species.map((sp) => (
            <p key={sp} style={{ fontStyle: "italic" }}>{sp}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function FaunaBarChart({ data }: { data: FaunaMonthRow[] }) {
  const chartData = data.map((d) => ({ ...d, period: formatMonth(d.month) }));
  const groups = ["mastofauna", "avifauna", "herpetofauna"] as const;

  return (
    <div style={CARD_STYLE}>
      <SectionTitle>Registros por Grupo de Fauna</SectionTitle>
      {data.length === 0 ? (
        <p className="text-sm text-center py-14" style={{ color: "#C3BAA8", ...F }}>
          Sem aparições confirmadas ainda
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={chartData}
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
              formatter={(v) => (
                <span style={{ ...F, fontSize: 12, color: "#6B6357" }}>
                  {GROUP_LABELS[v] ?? v}
                </span>
              )}
            />
            {groups.map((grp) => (
              <Bar
                key={grp}
                dataKey={grp}
                name={grp}
                stackId="fauna"
                fill={GROUP_COLORS[grp]}
                radius={grp === "herpetofauna" ? [3, 3, 0, 0] : [0, 0, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function CameraBarChart({ data }: { data: CameraRow[] }) {
  return (
    <div style={CARD_STYLE}>
      <SectionTitle>Registros por Câmera</SectionTitle>
      {data.length === 0 ? (
        <p className="text-sm text-center py-14" style={{ color: "#C3BAA8", ...F }}>
          Sem aparições confirmadas ainda
        </p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={data}
              barCategoryGap="35%"
              margin={{ top: 4, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#F0EAE0" vertical={false} />
              <XAxis dataKey="camera_id" tick={AXIS_STYLE} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS_STYLE} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<CameraTooltip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
              <Bar dataKey="total" name="Total" radius={[3, 3, 0, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={CAMERA_PALETTE[i % CAMERA_PALETTE.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          <div className="flex flex-wrap gap-3 mt-3">
            {data.map((cam, i) => (
              <span key={cam.camera_id} className="flex items-center gap-1.5 text-xs" style={{ color: "#6B6357", ...F }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: CAMERA_PALETTE[i % CAMERA_PALETTE.length],
                  display: "inline-block",
                }} />
                {cam.camera_id}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// Verde-musgo/terracota/mel-âmbar em rotação pras fatias de espécie; "Não
// identificado" sempre no marrom-suave/cinza da paleta (não entra na rotação).
const SPECIES_PALETTE = ["#2F6B4F", "#C25E3E", "#E2A33C"];
const UNIDENTIFIED_COLOR = "#9A9080";
const UNIDENTIFIED_LABEL = "Não identificado";

function SpeciesPieChart({ richness }: { richness: SpeciesRichnessRow[] }) {
  const speciesRows      = richness.filter((r) => r.taxonomic_level === "species");
  const unidentifiedRows = richness.filter((r) => r.taxonomic_level !== "species");
  const unidentifiedTotal = unidentifiedRows.reduce((s, r) => s + r.individual_count, 0);
  // "blank" (SpeciesNet confirmou que não é fauna) é um subconjunto de
  // "não identificado" — mostrado à parte pra não confundir com espécie
  // genuína ainda não identificada.
  const blankTotal = richness.find((r) => r.species === "blank")?.individual_count ?? 0;

  const pieData = [
    ...speciesRows.map((r) => ({ name: r.species, value: r.individual_count })),
    ...(unidentifiedTotal > 0 ? [{ name: UNIDENTIFIED_LABEL, value: unidentifiedTotal }] : []),
  ];
  const total = pieData.reduce((s, d) => s + d.value, 0);

  const colorFor = (name: string, i: number) =>
    name === UNIDENTIFIED_LABEL ? UNIDENTIFIED_COLOR : SPECIES_PALETTE[i % SPECIES_PALETTE.length];

  return (
    <div style={CARD_STYLE}>
      <div className="flex items-center gap-1.5 mb-4">
        <SectionTitle>Indivíduos por Espécie</SectionTitle>
        <InfoTooltip text="Indivíduos somados por registro independente — um registro é contado por vídeo; a mesma espécie em vídeos diferentes conta como registros separados." />
      </div>
      {pieData.length === 0 ? (
        <p className="text-sm text-center py-14" style={{ color: "#C3BAA8", ...F }}>
          Sem indivíduos confirmados ainda
        </p>
      ) : (
        <div className="flex flex-col md:flex-row gap-5 items-center">
          <div style={{ width: 200, height: 200, flexShrink: 0 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
                  {pieData.map((d, i) => (
                    <Cell key={d.name} fill={colorFor(d.name, i)} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="flex-1 flex flex-col gap-1.5 min-w-0 w-full">
            {pieData.map((d, i) => (
              <div key={d.name} className="flex items-center justify-between gap-3 text-xs">
                <span className="flex items-center gap-1.5 min-w-0" style={{ color: "#6B6357" }}>
                  <span
                    style={{ width: 8, height: 8, borderRadius: "50%", background: colorFor(d.name, i), flexShrink: 0 }}
                  />
                  <span className="truncate" style={{ fontStyle: d.name === UNIDENTIFIED_LABEL ? "normal" : "italic" }}>
                    {d.name}
                    {d.name === UNIDENTIFIED_LABEL && blankTotal > 0 && ` (incl. ${blankTotal} sem fauna)`}
                  </span>
                </span>
                <span className="font-semibold shrink-0" style={{ color: "#221F1A" }}>{d.value}</span>
              </div>
            ))}
            <div className="flex justify-between text-xs mt-1 pt-1.5" style={{ borderTop: "1px solid #E7DECF", color: "#6B6357" }}>
              <span>Total</span>
              <span className="font-bold" style={{ color: "#221F1A" }}>{total}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardCharts({ stats }: { stats: StatsData | null }) {
  return (
    <>
      <FaunaBarChart data={stats?.by_fauna_group_and_month ?? []} />
      <CameraBarChart data={stats?.by_camera ?? []} />
      <SpeciesPieChart richness={stats?.species_richness ?? []} />
    </>
  );
}
