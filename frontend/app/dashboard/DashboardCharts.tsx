"use client";

// Carregado apenas no browser (dynamic + ssr:false).
// Recharts acessa ResizeObserver/document ao importar.

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell,
} from "recharts";

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

export interface StatsData {
  total_confirmed:          number;
  distinct_species:         number;
  active_cameras:           number;
  period_start:             string | null;
  period_end:               string | null;
  by_fauna_group_and_month: FaunaMonthRow[];
  by_camera:                CameraRow[];
  species_richness:         { species: string; group: string; count: number }[];
}

const PT_MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];

function formatMonth(ym: string): string {
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

export default function DashboardCharts({ stats }: { stats: StatsData | null }) {
  return (
    <>
      <FaunaBarChart data={stats?.by_fauna_group_and_month ?? []} />
      <CameraBarChart data={stats?.by_camera ?? []} />
    </>
  );
}
