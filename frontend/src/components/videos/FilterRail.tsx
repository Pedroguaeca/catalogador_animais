"use client";

import { ArrowDownAZ, ArrowUpAZ } from "lucide-react";

export interface ChipCount {
  value: string; // "__none__" para "Sem câmera"
  label: string;
  count: number;
}

export interface Filters {
  cameraId:           string | null;
  species:             string | null;
  minConfidence:       number;   // 0–100
  semDeteccaoOnly:      boolean;
}

interface FilterRailProps {
  cameras:              ChipCount[];
  species:              ChipCount[];
  filters:              Filters;
  onChange:              (next: Filters) => void;
  confidenceDisabled:    boolean;
  showSemDeteccaoToggle: boolean;
  sortOrder:             "asc" | "desc";
  onSortOrderChange:     (order: "asc" | "desc") => void;
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: "#9A9080",
  letterSpacing: "0.04em", textTransform: "uppercase",
  fontFamily: "IBM Plex Sans, sans-serif",
};

function Chip({ selected, onClick, children, count }: {
  selected: boolean; onClick: () => void; children: React.ReactNode; count: number;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-between gap-2 text-left"
      style={{
        width: "100%", padding: "7px 10px", borderRadius: 9,
        border: selected ? "1.5px solid #2F6B4F" : "1.5px solid #E7DECF",
        background: selected ? "#2F6B4F" : "#fff",
        color: selected ? "#fff" : "#221F1A",
        fontSize: 12.5, fontWeight: selected ? 600 : 500,
        fontFamily: "IBM Plex Sans, sans-serif",
        cursor: "pointer", transition: "background 0.15s",
      }}
    >
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {children}
      </span>
      <span style={{
        fontFamily: "IBM Plex Mono, monospace", fontSize: 11,
        color: selected ? "#D7EEE1" : "#9A9080", flexShrink: 0,
      }}>
        {count}
      </span>
    </button>
  );
}

export function FilterRail({
  cameras, species, filters, onChange,
  confidenceDisabled, showSemDeteccaoToggle,
  sortOrder, onSortOrderChange,
}: FilterRailProps) {
  return (
    <div className="flex flex-col gap-5" style={{ width: 220, flexShrink: 0 }}>

      {/* Ordenação */}
      <div className="flex flex-col gap-2">
        <span style={sectionLabel}>Ordenar por captura</span>
        <button
          onClick={() => onSortOrderChange(sortOrder === "asc" ? "desc" : "asc")}
          className="flex items-center gap-2"
          style={{
            padding: "7px 10px", borderRadius: 9,
            border: "1px solid #E7DECF", background: "#fff",
            fontSize: 12.5, color: "#6B6357", cursor: "pointer",
            fontFamily: "IBM Plex Sans, sans-serif",
          }}
        >
          {sortOrder === "asc" ? <ArrowUpAZ size={13} /> : <ArrowDownAZ size={13} />}
          {sortOrder === "asc" ? "Mais antigo primeiro" : "Mais recente primeiro"}
        </button>
      </div>

      {/* Câmera */}
      {cameras.length > 0 && (
        <div className="flex flex-col gap-2">
          <span style={sectionLabel}>Câmera</span>
          <div className="flex flex-col gap-1.5">
            <Chip
              selected={filters.cameraId === null}
              onClick={() => onChange({ ...filters, cameraId: null })}
              count={cameras.reduce((s, c) => s + c.count, 0)}
            >
              Todas
            </Chip>
            {cameras.map((c) => (
              <Chip
                key={c.value}
                selected={filters.cameraId === c.value}
                onClick={() => onChange({ ...filters, cameraId: c.value })}
                count={c.count}
              >
                {c.label}
              </Chip>
            ))}
          </div>
        </div>
      )}

      {/* Espécie */}
      {species.length > 0 && (
        <div className="flex flex-col gap-2">
          <span style={sectionLabel}>Espécie</span>
          <div className="flex flex-col gap-1.5">
            <Chip
              selected={filters.species === null}
              onClick={() => onChange({ ...filters, species: null })}
              count={species.reduce((s, c) => s + c.count, 0)}
            >
              Todas
            </Chip>
            {species.map((s) => (
              <Chip
                key={s.value}
                selected={filters.species === s.value}
                onClick={() => onChange({ ...filters, species: s.value })}
                count={s.count}
              >
                {s.label}
              </Chip>
            ))}
          </div>
        </div>
      )}

      {/* Confiança mínima */}
      <div className="flex flex-col gap-2" style={{ opacity: confidenceDisabled ? 0.4 : 1 }}>
        <span style={sectionLabel}>
          Confiança mínima {confidenceDisabled ? "(sem dado nesta aba)" : `— ${filters.minConfidence}%`}
        </span>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={filters.minConfidence}
          disabled={confidenceDisabled}
          onChange={(e) => onChange({ ...filters, minConfidence: Number(e.target.value) })}
          style={{ width: "100%", accentColor: "#2F6B4F", cursor: confidenceDisabled ? "not-allowed" : "pointer" }}
        />
      </div>

      {/* Somente sem identificação */}
      {showSemDeteccaoToggle && (
        <label
          className="flex items-center gap-2 cursor-pointer select-none"
          style={{ fontSize: 12.5, color: "#6B6357", fontFamily: "IBM Plex Sans, sans-serif" }}
        >
          <input
            type="checkbox"
            checked={filters.semDeteccaoOnly}
            onChange={(e) => onChange({ ...filters, semDeteccaoOnly: e.target.checked })}
            style={{ accentColor: "#2D8B5F", width: 14, height: 14 }}
          />
          Somente sem identificação
        </label>
      )}
    </div>
  );
}
