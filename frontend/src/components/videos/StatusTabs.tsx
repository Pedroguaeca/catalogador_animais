"use client";

import { statusStyle } from "../../lib/statusColors";

export type TabKey = "aguardando" | "processando" | "revisado";

const TABS: { key: TabKey; label: string; statusForColor: string }[] = [
  { key: "aguardando", label: "Aguardando revisão", statusForColor: "Aguardando revisão" },
  { key: "processando", label: "Processando",        statusForColor: "Processando" },
  { key: "revisado",    label: "Revisado",           statusForColor: "Revisado" },
];

interface StatusTabsProps {
  active: TabKey;
  counts: Record<TabKey, number>;
  onChange: (tab: TabKey) => void;
}

export function StatusTabs({ active, counts, onChange }: StatusTabsProps) {
  return (
    <nav className="flex items-center gap-1" style={{ borderBottom: "1px solid #EFE8DB" }}>
      {TABS.map(({ key, label, statusForColor }) => {
        const isActive = active === key;
        const st = statusStyle(statusForColor);
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            className="flex items-center gap-2"
            style={{
              padding: "10px 14px", borderRadius: "10px 10px 0 0",
              border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: isActive ? 600 : 400,
              color:      isActive ? "#221F1A" : "#6B6357",
              background: isActive ? "#fff" : "transparent",
              borderBottom: isActive ? "2px solid #2F6B4F" : "2px solid transparent",
              marginBottom: -1,
              fontFamily: "IBM Plex Sans, sans-serif",
              transition: "background 0.15s, color 0.15s",
            }}
          >
            {label}
            <span style={{
              padding: "1px 7px", borderRadius: 999, fontSize: 11, fontWeight: 600,
              background: st.bg, color: st.color,
              fontFamily: "IBM Plex Mono, monospace",
            }}>
              {counts[key]}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
