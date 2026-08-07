"use client";

import type { CSSProperties } from "react";
import type { Project, Client } from "../lib/projectTypes";
import { clientName } from "../lib/projectTypes";

interface ProjectSelectorProps {
  projects:     Project[];
  clients:      Client[];
  value:        string;
  onChange:     (projectId: string) => void;
  // Se definido, mostra uma opção vazia inicial — usado no upload (SIAB-222),
  // onde nenhum projeto deve vir pré-selecionado.
  placeholder?: string;
  disabled?:    boolean;
  style?:       CSSProperties;
}

const DEFAULT_STYLE: CSSProperties = {
  padding: "8px 12px", borderRadius: 10, fontSize: 13,
  border: "1.5px solid #E7DECF", background: "#FAF6EE",
  color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif",
};

// SIAB-221/222: dropdown de projeto compartilhado entre upload, vídeos,
// dashboard e export — substitui o PROJECT_ID hardcoded que cada uma tinha
// (temporário desde o hotfix de PROJECT_ID). Cada opção mostra nome do
// projeto + nome do cliente (via client_id), como especificado.
export function ProjectSelector({
  projects, clients, value, onChange, placeholder, disabled, style,
}: ProjectSelectorProps) {
  const sorted = [...projects].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));

  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      style={{ ...DEFAULT_STYLE, ...style }}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {sorted.map((p) => (
        <option key={p.project_id} value={p.project_id}>
          {p.nome} — {clientName(clients, p.client_id)}
        </option>
      ))}
    </select>
  );
}
